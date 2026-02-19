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
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"


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


def _surreal_desk_context_sync(tenant_id: str, user_id: str) -> str:
    """Fetch enabled desk source texts and format as desk context string."""
    from surrealdb import Surreal

    db = Surreal(settings.SURREALDB_URL)
    try:
        db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
        db.use("eveningdraft", tenant_id)
        result = db.query(
            "SELECT display_name, extracted_text FROM ed_desk_sources "
            "WHERE user_id = $uid AND is_enabled = true ORDER BY created_at DESC",
            {"uid": user_id},
        )
        rows = result if isinstance(result, list) and result and isinstance(result[0], dict) else []
        if isinstance(result, list) and result and isinstance(result[0], dict) and "result" in result[0]:
            rows = result[0]["result"]

        if not rows:
            return ""

        # Budget: ~7200 chars (~1800 tokens)
        budget = 7200
        parts: list[str] = []
        total = 0
        for row in rows:
            name = row.get("display_name", "Document")
            text = row.get("extracted_text", "")
            if not text:
                continue
            remaining = budget - total
            if remaining <= 0:
                break
            snippet = text[:remaining]
            parts.append(f"\U0001f4c4 {name}:\n{snippet}")
            total += len(snippet)

        return "\n\n".join(parts)
    except Exception as e:
        logger.warning("Desk context fetch failed: %s", e)
        return ""
    finally:
        db.close()


def _surreal_search_sync(tenant_id: str, query: str) -> str:
    """Run KOS journal context search synchronously (for run_in_executor).

    Excludes chat/user and chat/assistant content types — matches Swift
    KOSSearchService.searchJournalPassages.
    """
    from surrealdb import Surreal
    from app.eveningdraft.kos.search import search_journal_passages_sync

    db = Surreal(settings.SURREALDB_URL)
    try:
        db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
        db.use("eveningdraft", tenant_id)
        return search_journal_passages_sync(db, query, tenant_id)
    except Exception as e:
        logger.warning("KOS context search failed: %s", e)
        return ""
    finally:
        db.close()


def _surreal_ingest_sync(
    tenant_id: str, user_id: str, session_id: str,
    user_msg: str, assistant_msg: str,
    llm_prompt: str | None = None,
) -> None:
    """Run KOS ingestion synchronously (for run_in_executor).

    Passes llm_prompt to assistant item — matches Swift ChatAPIService flow.
    """
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
            llm_prompt=llm_prompt,
        )
        logger.info("ED KOS ingested chat turn for tenant %s", tenant_id)
    except Exception as e:
        logger.error("ED KOS ingestion failed for tenant %s: %s", tenant_id, e)
    finally:
        db.close()


async def _ingest_chat_turn_bg(
    user_id: str, tenant_id: str, session_id: str,
    user_msg: str, assistant_msg: str,
    llm_prompt: str | None = None,
):
    """Background task: ingest a chat turn into the ED KOS pipeline."""
    if not tenant_id or tenant_id.startswith("pending_"):
        logger.warning("Skipping ED KOS ingestion — tenant %s not provisioned", tenant_id)
        return

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _surreal_ingest_sync,
        tenant_id, user_id, session_id, user_msg, assistant_msg, llm_prompt,
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

    # 3-tier context retrieval (matches Swift ChatAPIService)
    desk_context = ""
    journal_context = ""
    if tenant_id and not tenant_id.startswith("pending_"):
        loop = asyncio.get_event_loop()

        # Tier 1: Desk context (enabled documents — ground truth)
        desk_context = await loop.run_in_executor(
            None, _surreal_desk_context_sync, tenant_id, user_id,
        )

        # Tier 3: Journal context (FTS from journal, excluding chat)
        last_user_msg = ""
        for m in reversed(body.messages):
            if m.role == "user":
                last_user_msg = m.content
                break

        if last_user_msg:
            journal_context = await loop.run_in_executor(
                None, _surreal_search_sync, tenant_id, last_user_msg,
            )

    # Inject Muse system prompt (3-tier context — matches Swift MusePersonality)
    system_prompt = build_system_prompt(
        desk_context=desk_context,
        journal_context=journal_context,
    )
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

    # Build full LLM prompt for logging/auditability (matches Swift buildFullPrompt)
    full_llm_prompt = f"SYSTEM PROMPT:\n{system_prompt}\n\n"
    if len(body.messages) > 1:
        full_llm_prompt += "CONVERSATION HISTORY:\n"
        for m in body.messages[:-1]:
            role_label = "Writer" if m.role == "user" else "Muse"
            full_llm_prompt += f"{role_label}: {m.content}\n"
        full_llm_prompt += "\n"
    if last_user_content:
        full_llm_prompt += f"WRITER:\n{last_user_content}"

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

            # Background ingest (with llm_prompt — matches Swift)
            if full_response and last_user_content:
                asyncio.create_task(
                    _ingest_chat_turn_bg(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        user_msg=last_user_content,
                        assistant_msg=full_response,
                        llm_prompt=full_llm_prompt,
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

        # Background ingest (with llm_prompt — matches Swift)
        if assistant_content and last_user_content:
            asyncio.create_task(
                _ingest_chat_turn_bg(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    user_msg=last_user_content,
                    assistant_msg=assistant_content,
                    llm_prompt=full_llm_prompt,
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
