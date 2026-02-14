import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from openai import AsyncOpenAI

from app.api.deps import CurrentUser
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"


class ChatMessage(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str = DEFAULT_MODEL
    stream: bool = False


class ChatResponse(BaseModel):
    id: str
    model: str
    message: ChatMessage
    usage: dict | None = None


def _get_client() -> AsyncOpenAI:
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY is not configured",
        )
    return AsyncOpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
    )


async def _ingest_chat_turn_bg(user_id: str, tenant_id: str, user_msg: str, assistant_msg: str):
    """Background task: ingest a chat turn into the KOS pipeline."""
    from kos.providers.surrealdb.client import SurrealDBClient
    from kos_extensions.registry import CloudProviderRegistry
    from kos_extensions.ingest import ingest_chat_turn

    client = SurrealDBClient(
        url=settings.SURREALDB_URL,
        namespace=settings.SURREALDB_NAMESPACE,
        database=tenant_id,
        user=settings.SURREALDB_USER,
        password=settings.SURREALDB_PASSWORD,
    )
    try:
        await client.connect()
        registry = CloudProviderRegistry(client)
        user_item_id, asst_item_id = await ingest_chat_turn(
            registry=registry,
            tenant_id=tenant_id,
            user_id=user_id,
            user_message=user_msg,
            assistant_message=assistant_msg,
        )
        logger.info(
            "KOS ingested chat turn for tenant %s: user=%s assistant=%s",
            tenant_id, user_item_id, asst_item_id,
        )
    except Exception:
        logger.exception("KOS ingestion failed for tenant %s", tenant_id)
    finally:
        await client.close()


@router.post("/completions", response_model=ChatResponse)
async def chat_completions(body: ChatRequest, current_user: CurrentUser, background_tasks: BackgroundTasks):
    """Send a chat completion request to OpenRouter. Requires authentication."""
    client = _get_client()

    response = await client.chat.completions.create(
        model=body.model,
        messages=[{"role": m.role, "content": m.content} for m in body.messages],
        stream=False,
    )

    choice = response.choices[0]
    assistant_content = choice.message.content or ""

    # Ingest the last user message + assistant response into KOS
    last_user_msg = ""
    for m in reversed(body.messages):
        if m.role == "user":
            last_user_msg = m.content
            break

    if current_user.tenant_id and last_user_msg:
        background_tasks.add_task(
            _ingest_chat_turn_bg,
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
            user_msg=last_user_msg,
            assistant_msg=assistant_content,
        )

    return ChatResponse(
        id=response.id,
        model=response.model or body.model,
        message=ChatMessage(
            role=choice.message.role or "assistant",
            content=assistant_content,
        ),
        usage=response.usage.model_dump() if response.usage else None,
    )


@router.post("/completions/stream")
async def chat_completions_stream(body: ChatRequest, current_user: CurrentUser, background_tasks: BackgroundTasks):
    """Stream a chat completion response from OpenRouter. Requires authentication."""
    client = _get_client()

    collected_content: list[str] = []

    async def event_generator():
        stream = await client.chat.completions.create(
            model=body.model,
            messages=[{"role": m.role, "content": m.content} for m in body.messages],
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                collected_content.append(text)
                yield f"data: {text}\n\n"
        yield "data: [DONE]\n\n"

        # Schedule KOS ingestion after stream completes
        last_user_msg = ""
        for m in reversed(body.messages):
            if m.role == "user":
                last_user_msg = m.content
                break

        assistant_msg = "".join(collected_content)
        if current_user.tenant_id and last_user_msg:
            # Can't use background_tasks inside generator, so fire-and-forget
            asyncio.create_task(
                _ingest_chat_turn_bg(
                    user_id=str(current_user.id),
                    tenant_id=current_user.tenant_id,
                    user_msg=last_user_msg,
                    assistant_msg=assistant_msg,
                )
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")
