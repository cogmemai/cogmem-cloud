"""Chat endpoint for Evening Draft.

OpenAI-compatible proxy to OpenRouter with KOS context injection
and background ingestion of chat turns.

Uses the blocking ``surrealdb.Surreal`` library (same as tenant.py).
All SurrealDB calls are wrapped in ``run_in_executor`` to avoid
blocking the event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from openai import AsyncOpenAI

from app.eveningdraft.deps import CurrentEDUser, EDSessionDep
from app.core.config import settings
from app.eveningdraft.kos.muse import build_system_prompt
from app.eveningdraft.tenant import provision_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["eveningdraft-chat"])

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str = DEFAULT_MODEL
    stream: bool = False
    session_id: str | None = None


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


def _surreal_search_sync(tenant_id: str, query: str) -> str:
    """Run KOS context search synchronously (for run_in_executor)."""
    from surrealdb import Surreal
    from app.eveningdraft.kos.search import search_passages_sync

    db = Surreal(settings.SURREALDB_URL)
    try:
        db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
        db.use("eveningdraft", tenant_id)
        return search_passages_sync(db, query, tenant_id)
    except Exception as e:
        logger.warning("KOS context search failed: %s", e)
        return ""
    finally:
        db.close()


def _surreal_ingest_sync(
    tenant_id: str, user_id: str, session_id: str,
    user_msg: str, assistant_msg: str,
) -> None:
    """Run KOS ingestion synchronously (for run_in_executor)."""
    from surrealdb import Surreal
    from app.eveningdraft.kos.ingest import ingest_chat_turn_sync

    db = Surreal(settings.SURREALDB_URL)
    try:
        db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
        db.use("eveningdraft", tenant_id)
        ingest_chat_turn_sync(
            db=db, tenant_id=tenant_id, user_id=user_id,
            session_id=session_id,
            user_message=user_msg, assistant_message=assistant_msg,
        )
        logger.info("ED KOS ingested chat turn for tenant %s", tenant_id)
    except Exception as e:
        logger.error("ED KOS ingestion failed for tenant %s: %s", tenant_id, e)
    finally:
        db.close()


async def _ingest_chat_turn_bg(
    user_id: str, tenant_id: str, session_id: str,
    user_msg: str, assistant_msg: str,
):
    """Background task: ingest a chat turn into the ED KOS pipeline."""
    if not tenant_id or tenant_id.startswith("pending_"):
        logger.warning("Skipping ED KOS ingestion — tenant %s not provisioned", tenant_id)
        return

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _surreal_ingest_sync,
        tenant_id, user_id, session_id, user_msg, assistant_msg,
    )


@router.post("/completions")
async def chat_completions(
    body: ChatRequest, current_user: CurrentEDUser, session: EDSessionDep,
):
    """OpenAI-compatible chat completions endpoint for Evening Draft."""
    client = _get_client()
    tenant_id = current_user.tenant_id or ""
    user_id = str(current_user.id)
    session_id = body.session_id or str(uuid.uuid4())

    # Auto-provision tenant if missing or stale
    if not tenant_id or tenant_id.startswith("pending_"):
        try:
            tenant_id = await provision_tenant(current_user.id)
            current_user.tenant_id = tenant_id
            session.add(current_user)
            session.commit()
            session.refresh(current_user)
            logger.info("Auto-provisioned ED tenant %s for user %s", tenant_id, current_user.email)
        except Exception:
            logger.exception("Auto-provision failed for user %s", current_user.email)
            tenant_id = ""

    # Build messages with Muse system prompt
    messages = []

    # Try to get KOS context for the latest user message
    journal_context = ""
    if tenant_id and not tenant_id.startswith("pending_"):
        last_user_msg = ""
        for m in reversed(body.messages):
            if m.role == "user":
                last_user_msg = m.content
                break

        if last_user_msg:
            loop = asyncio.get_event_loop()
            journal_context = await loop.run_in_executor(
                None, _surreal_search_sync, tenant_id, last_user_msg,
            )

    # Inject Muse system prompt
    system_prompt = build_system_prompt(journal_context=journal_context)
    messages.append({"role": "system", "content": system_prompt})

    # Add user conversation messages
    for m in body.messages:
        messages.append({"role": m.role, "content": m.content})

    # Get the last user message for ingestion
    last_user_content = ""
    for m in reversed(body.messages):
        if m.role == "user":
            last_user_content = m.content
            break

    if body.stream:
        # Streaming response
        async def stream_generator():
            full_response = ""
            try:
                stream = await client.chat.completions.create(
                    model=body.model,
                    messages=messages,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        full_response += delta.content
                        data = {
                            "id": chunk.id,
                            "object": "chat.completion.chunk",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": delta.content},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(data)}\n\n"

                # Final chunk
                yield "data: [DONE]\n\n"

            except Exception as e:
                logger.error("Stream error: %s", e)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

            # Background ingest
            if full_response and last_user_content:
                asyncio.create_task(
                    _ingest_chat_turn_bg(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        user_msg=last_user_content,
                        assistant_msg=full_response,
                    )
                )

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    else:
        # Non-streaming response
        try:
            completion = await client.chat.completions.create(
                model=body.model,
                messages=messages,
                stream=False,
            )
        except Exception as e:
            logger.error("Chat completion error: %s", e)
            raise HTTPException(status_code=502, detail=f"LLM provider error: {e}")

        assistant_content = completion.choices[0].message.content or ""

        # Background ingest
        if assistant_content and last_user_content:
            asyncio.create_task(
                _ingest_chat_turn_bg(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    user_msg=last_user_content,
                    assistant_msg=assistant_content,
                )
            )

        return {
            "id": completion.id,
            "object": "chat.completion",
            "model": completion.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": completion.usage.prompt_tokens if completion.usage else 0,
                "completion_tokens": completion.usage.completion_tokens if completion.usage else 0,
                "total_tokens": completion.usage.total_tokens if completion.usage else 0,
            },
        }
