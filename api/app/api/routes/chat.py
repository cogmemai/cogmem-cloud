from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from openai import AsyncOpenAI

from app.api.deps import CurrentUser
from app.core.config import settings

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


@router.post("/completions", response_model=ChatResponse)
async def chat_completions(body: ChatRequest, current_user: CurrentUser):
    """Send a chat completion request to OpenRouter. Requires authentication."""
    client = _get_client()

    response = await client.chat.completions.create(
        model=body.model,
        messages=[{"role": m.role, "content": m.content} for m in body.messages],
        stream=False,
    )

    choice = response.choices[0]
    return ChatResponse(
        id=response.id,
        model=response.model or body.model,
        message=ChatMessage(
            role=choice.message.role or "assistant",
            content=choice.message.content or "",
        ),
        usage=response.usage.model_dump() if response.usage else None,
    )


@router.post("/completions/stream")
async def chat_completions_stream(body: ChatRequest, current_user: CurrentUser):
    """Stream a chat completion response from OpenRouter. Requires authentication."""
    client = _get_client()

    async def event_generator():
        stream = await client.chat.completions.create(
            model=body.model,
            messages=[{"role": m.role, "content": m.content} for m in body.messages],
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield f"data: {chunk.choices[0].delta.content}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
