"""Journal CRUD endpoints for Evening Draft.

Stores journal entries in the user's SurrealDB tenant (ed_journal_entries)
and optionally ingests them into the KOS pipeline for Muse context.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.eveningdraft.deps import CurrentEDUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journal", tags=["journal"])


# ── Request / Response models ────────────────────────────────────────────────

class JournalEntryCreate(BaseModel):
    title: str = ""
    content: str = ""


class JournalEntryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class JournalEntryOut(BaseModel):
    kos_id: str
    tenant_id: str
    user_id: str
    title: str
    content: str
    word_count: int
    is_indexed: bool
    created_at: str
    updated_at: str


class JournalIndexRequest(BaseModel):
    kos_id: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _word_count(text: str) -> int:
    return len([w for w in text.split() if w])


def _surreal_journal_sync(tenant_id: str, operation: str, **kwargs) -> Any:
    """Run a synchronous SurrealDB operation for journal entries."""
    from surrealdb import Surreal

    db = Surreal(settings.SURREALDB_URL)
    try:
        db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
        db.use("eveningdraft", tenant_id)

        if operation == "create":
            return db.create("ed_journal_entries", kwargs["data"])

        elif operation == "list":
            user_id = kwargs["user_id"]
            result = db.query(
                "SELECT * FROM ed_journal_entries WHERE user_id = $uid ORDER BY updated_at DESC LIMIT 50",
                {"uid": user_id},
            )
            rows = result[0] if result and isinstance(result, list) else []
            if isinstance(rows, dict) and "result" in rows:
                rows = rows["result"]
            return rows or []

        elif operation == "get":
            kos_id = kwargs["kos_id"]
            user_id = kwargs["user_id"]
            result = db.query(
                "SELECT * FROM ed_journal_entries WHERE kos_id = $kid AND user_id = $uid LIMIT 1",
                {"kid": kos_id, "uid": user_id},
            )
            rows = result[0] if result and isinstance(result, list) else []
            if isinstance(rows, dict) and "result" in rows:
                rows = rows["result"]
            return rows[0] if rows else None

        elif operation == "update":
            kos_id = kwargs["kos_id"]
            user_id = kwargs["user_id"]
            updates = kwargs["updates"]
            # Build SET clause
            set_parts = []
            params = {"kid": kos_id, "uid": user_id}
            for k, v in updates.items():
                set_parts.append(f"{k} = ${k}")
                params[k] = v
            set_clause = ", ".join(set_parts)
            result = db.query(
                f"UPDATE ed_journal_entries SET {set_clause} WHERE kos_id = $kid AND user_id = $uid RETURN AFTER",
                params,
            )
            rows = result[0] if result and isinstance(result, list) else []
            if isinstance(rows, dict) and "result" in rows:
                rows = rows["result"]
            return rows[0] if rows else None

        elif operation == "delete":
            kos_id = kwargs["kos_id"]
            user_id = kwargs["user_id"]
            db.query(
                "DELETE FROM ed_journal_entries WHERE kos_id = $kid AND user_id = $uid",
                {"kid": kos_id, "uid": user_id},
            )
            return True

    finally:
        db.close()


def _surreal_ingest_journal_sync(tenant_id: str, user_id: str, entry_kos_id: str, title: str, content: str) -> str:
    """Ingest a journal entry into the KOS pipeline."""
    from surrealdb import Surreal
    from app.eveningdraft.kos.ingest import _ingest_content_sync

    db = Surreal(settings.SURREALDB_URL)
    try:
        db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
        db.use("eveningdraft", tenant_id)

        item_id = _ingest_content_sync(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            title=title or f"Journal — {datetime.utcnow().strftime('%b %d, %Y')}",
            content=content,
            source="note",
            content_type="journal/entry",
            external_id=entry_kos_id,
            metadata={
                "type": "journal",
                "entry_id": entry_kos_id,
                "word_count": str(_word_count(content)),
            },
        )

        # Mark entry as indexed
        db.query(
            "UPDATE ed_journal_entries SET is_indexed = true WHERE kos_id = $kid",
            {"kid": entry_kos_id},
        )

        return item_id
    finally:
        db.close()


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/entries")
async def list_entries(current_user: CurrentEDUser) -> list[JournalEntryOut]:
    """List all journal entries for the current user."""
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        return []

    user_id = str(current_user.id)
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(
        None, _surreal_journal_sync, tenant_id, "list", **{"user_id": user_id},
    )

    return [
        JournalEntryOut(
            kos_id=r.get("kos_id", ""),
            tenant_id=r.get("tenant_id", ""),
            user_id=r.get("user_id", ""),
            title=r.get("title", ""),
            content=r.get("content", ""),
            word_count=r.get("word_count", 0),
            is_indexed=r.get("is_indexed", False),
            created_at=r.get("created_at", ""),
            updated_at=r.get("updated_at", ""),
        )
        for r in rows
    ]


@router.post("/entries")
async def create_entry(body: JournalEntryCreate, current_user: CurrentEDUser) -> JournalEntryOut:
    """Create a new journal entry."""
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        raise HTTPException(status_code=400, detail="No tenant database provisioned")

    user_id = str(current_user.id)
    now = datetime.utcnow().isoformat()
    kos_id = str(uuid.uuid4())

    data = {
        "kos_id": kos_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "title": body.title,
        "content": body.content,
        "word_count": _word_count(body.content),
        "is_indexed": False,
        "created_at": now,
        "updated_at": now,
    }

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _surreal_journal_sync, tenant_id, "create", **{"data": data},
    )

    return JournalEntryOut(**data)


@router.put("/entries/{kos_id}")
async def update_entry(kos_id: str, body: JournalEntryUpdate, current_user: CurrentEDUser) -> JournalEntryOut:
    """Update an existing journal entry (autosave)."""
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        raise HTTPException(status_code=400, detail="No tenant database provisioned")

    user_id = str(current_user.id)
    now = datetime.utcnow().isoformat()

    updates: dict[str, Any] = {"updated_at": now}
    if body.title is not None:
        updates["title"] = body.title
    if body.content is not None:
        updates["content"] = body.content
        updates["word_count"] = _word_count(body.content)
        updates["is_indexed"] = False  # needs re-index after content change

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _surreal_journal_sync, tenant_id, "update",
        **{"kos_id": kos_id, "user_id": user_id, "updates": updates},
    )

    if not result:
        raise HTTPException(status_code=404, detail="Entry not found")

    return JournalEntryOut(
        kos_id=result.get("kos_id", kos_id),
        tenant_id=result.get("tenant_id", tenant_id),
        user_id=result.get("user_id", user_id),
        title=result.get("title", ""),
        content=result.get("content", ""),
        word_count=result.get("word_count", 0),
        is_indexed=result.get("is_indexed", False),
        created_at=result.get("created_at", ""),
        updated_at=result.get("updated_at", now),
    )


@router.delete("/entries/{kos_id}")
async def delete_entry(kos_id: str, current_user: CurrentEDUser) -> dict:
    """Delete a journal entry."""
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        raise HTTPException(status_code=400, detail="No tenant database provisioned")

    user_id = str(current_user.id)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _surreal_journal_sync, tenant_id, "delete",
        **{"kos_id": kos_id, "user_id": user_id},
    )

    return {"status": "ok", "deleted": kos_id}


@router.post("/entries/{kos_id}/index")
async def index_entry(kos_id: str, current_user: CurrentEDUser) -> dict:
    """Index a journal entry into the KOS pipeline for Muse context."""
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        raise HTTPException(status_code=400, detail="No tenant database provisioned")

    user_id = str(current_user.id)

    # Fetch the entry first
    loop = asyncio.get_event_loop()
    entry = await loop.run_in_executor(
        None, _surreal_journal_sync, tenant_id, "get",
        **{"kos_id": kos_id, "user_id": user_id},
    )

    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    content = entry.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Cannot index empty entry")

    item_id = await loop.run_in_executor(
        None, _surreal_ingest_journal_sync,
        tenant_id, user_id, kos_id, entry.get("title", ""), content,
    )

    return {"status": "ok", "kos_id": kos_id, "item_id": item_id, "is_indexed": True}
