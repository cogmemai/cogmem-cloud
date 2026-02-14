import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
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
    if not tenant_id or tenant_id.startswith("pending_"):
        logger.warning("Skipping KOS ingestion — tenant %s not provisioned", tenant_id)
        return

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


def _extract_last_user_msg(messages: list) -> str:
    """Extract the last user message content from a messages list."""
    for m in reversed(messages):
        if isinstance(m, dict):
            if m.get("role") == "user":
                return m.get("content", "")
        elif hasattr(m, "role") and m.role == "user":
            return m.content
    return ""


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

    last_user_msg = _extract_last_user_msg(body.messages)
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
async def chat_completions_stream(body: ChatRequest, current_user: CurrentUser):
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
        assistant_msg = "".join(collected_content)
        last_user_msg = _extract_last_user_msg(body.messages)
        if current_user.tenant_id and last_user_msg:
            asyncio.create_task(
                _ingest_chat_turn_bg(
                    user_id=str(current_user.id),
                    tenant_id=current_user.tenant_id,
                    user_msg=last_user_msg,
                    assistant_msg=assistant_msg,
                )
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/v1/chat/completions")
async def openai_compatible_chat(request: Request, current_user: CurrentUser):
    """OpenAI-compatible /v1/chat/completions endpoint.

    Proxies the request to OpenRouter and passes through the raw SSE stream
    so the AI SDK can consume it directly. Triggers KOS ingestion after
    the stream completes.
    """
    import httpx

    body = await request.json()
    messages = body.get("messages", [])
    model = body.get("model", DEFAULT_MODEL)
    stream = body.get("stream", False)

    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured")

    if not stream:
        # Non-streaming: proxy and ingest
        client = _get_client()
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
        )
        assistant_content = response.choices[0].message.content or ""

        last_user_msg = _extract_last_user_msg(messages)
        if current_user.tenant_id and last_user_msg:
            asyncio.create_task(
                _ingest_chat_turn_bg(
                    user_id=str(current_user.id),
                    tenant_id=current_user.tenant_id,
                    user_msg=last_user_msg,
                    assistant_msg=assistant_content,
                )
            )

        return response.model_dump()

    # Streaming: proxy the raw OpenRouter SSE stream and collect content for ingestion
    collected_content: list[str] = []

    async def proxy_stream():
        async with httpx.AsyncClient() as http_client:
            async with http_client.stream(
                "POST",
                f"{OPENROUTER_BASE_URL}/chat/completions",
                json={**body, "stream": True},
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            ) as upstream:
                async for line in upstream.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            yield f"data: [DONE]\n\n"
                        else:
                            try:
                                chunk = json.loads(data)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    collected_content.append(content)
                            except (json.JSONDecodeError, IndexError, KeyError):
                                pass
                            yield f"{line}\n\n"

        # After stream completes, trigger KOS ingestion
        assistant_msg = "".join(collected_content)
        last_user_msg = _extract_last_user_msg(messages)
        if current_user.tenant_id and last_user_msg and assistant_msg:
            asyncio.create_task(
                _ingest_chat_turn_bg(
                    user_id=str(current_user.id),
                    tenant_id=current_user.tenant_id,
                    user_msg=last_user_msg,
                    assistant_msg=assistant_msg,
                )
            )

    return StreamingResponse(proxy_stream(), media_type="text/event-stream")
