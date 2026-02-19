"""Context Desk API for Evening Draft.

Upload documents (PDF, DOCX, TXT, MD) to the Muse's "desk" so they
are available as ground-truth context during chat.

Extracted text is stored in the ``ed_desk_sources`` SurrealDB table.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import uuid
from datetime import datetime
from functools import partial
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from app.eveningdraft.deps import CurrentEDUser
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/desk", tags=["eveningdraft-desk"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf"}


# ── Models ────────────────────────────────────────────────────────────────

class DeskSourceOut(BaseModel):
    kos_id: str
    display_name: str
    kind: str = "file_document"
    is_enabled: bool = True
    character_count: int = 0
    content_hash: str | None = None
    kos_item_id: str | None = None
    created_at: str | None = None


class DeskToggleRequest(BaseModel):
    is_enabled: bool


# ── Text extraction ───────────────────────────────────────────────────────

def _extract_text_from_bytes(filename: str, data: bytes) -> str:
    """Extract plain text from a file's raw bytes."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == ".pdf":
        import pymupdf
        doc = pymupdf.open(stream=data, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text())
        doc.close()
        return "\n\n".join(parts).strip()

    if ext in (".docx", ".doc"):
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if ext in (".txt", ".md", ".rtf"):
        return data.decode("utf-8", errors="replace").strip()

    raise ValueError(f"Unsupported file type: {ext}")


# ── SurrealDB sync helpers ────────────────────────────────────────────────

def _extract_rows(result: Any) -> list[dict]:
    """Normalise SurrealDB query result to a flat list of dicts."""
    if not result:
        return []
    first = result[0] if isinstance(result, list) else result
    if isinstance(first, dict) and "result" in first:
        first = first["result"]
    if isinstance(first, list):
        return [r for r in first if isinstance(r, dict)]
    if isinstance(first, dict):
        return [first]
    if isinstance(result, list) and all(isinstance(r, dict) for r in result):
        return result
    return []


def _surreal_desk_sync(tenant_id: str, operation: str, **kwargs: Any) -> Any:
    """Run a synchronous SurrealDB operation for desk sources."""
    from surrealdb import Surreal

    db = Surreal(settings.SURREALDB_URL)
    try:
        db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
        db.use("eveningdraft", tenant_id)

        if operation == "create":
            data = kwargs["data"]
            db.create("ed_desk_sources", data)
            return data

        elif operation == "list":
            user_id = kwargs["user_id"]
            result = db.query(
                "SELECT * FROM ed_desk_sources WHERE user_id = $uid ORDER BY created_at DESC",
                {"uid": user_id},
            )
            return _extract_rows(result)

        elif operation == "get":
            kos_id = kwargs["kos_id"]
            user_id = kwargs["user_id"]
            result = db.query(
                "SELECT * FROM ed_desk_sources WHERE kos_id = $kid AND user_id = $uid LIMIT 1",
                {"kid": kos_id, "uid": user_id},
            )
            rows = _extract_rows(result)
            return rows[0] if rows else None

        elif operation == "get_by_hash":
            content_hash = kwargs["content_hash"]
            user_id = kwargs["user_id"]
            result = db.query(
                "SELECT * FROM ed_desk_sources WHERE content_hash = $hash AND user_id = $uid LIMIT 1",
                {"hash": content_hash, "uid": user_id},
            )
            rows = _extract_rows(result)
            return rows[0] if rows else None

        elif operation == "update":
            kos_id = kwargs["kos_id"]
            user_id = kwargs["user_id"]
            updates = kwargs["updates"]
            set_parts = []
            params: dict[str, Any] = {"kid": kos_id, "uid": user_id}
            for k, v in updates.items():
                set_parts.append(f"{k} = ${k}")
                params[k] = v
            set_clause = ", ".join(set_parts)
            result = db.query(
                f"UPDATE ed_desk_sources SET {set_clause} WHERE kos_id = $kid AND user_id = $uid RETURN AFTER",
                params,
            )
            rows = _extract_rows(result)
            return rows[0] if rows else None

        elif operation == "delete":
            kos_id = kwargs["kos_id"]
            user_id = kwargs["user_id"]
            db.query(
                "DELETE FROM ed_desk_sources WHERE kos_id = $kid AND user_id = $uid",
                {"kid": kos_id, "uid": user_id},
            )
            return True

        elif operation == "get_enabled_context":
            user_id = kwargs["user_id"]
            result = db.query(
                "SELECT kos_id, display_name, extracted_text, created_at FROM ed_desk_sources "
                "WHERE user_id = $uid AND is_enabled = true ORDER BY created_at DESC",
                {"uid": user_id},
            )
            return _extract_rows(result)

        else:
            raise ValueError(f"Unknown desk operation: {operation}")
    finally:
        db.close()


def _surreal_ingest_desk_sync(
    tenant_id: str, user_id: str, source_kos_id: str, title: str, content: str,
) -> str:
    """Ingest a desk document into the KOS pipeline."""
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
            title=title,
            content=content,
            source="note",
            content_type="desk/document",
            external_id=source_kos_id,
            metadata={
                "type": "desk",
                "source_id": source_kos_id,
            },
        )
        # Update the desk source with the KOS item ID
        db.query(
            "UPDATE ed_desk_sources SET kos_item_id = $iid WHERE kos_id = $kid",
            {"iid": item_id, "kid": source_kos_id},
        )
        return item_id
    finally:
        db.close()


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/sources/upload", response_model=DeskSourceOut)
async def upload_desk_source(
    current_user: CurrentEDUser,
    file: UploadFile = File(...),
) -> Any:
    """Upload a document to the desk. Extracts text and stores it."""
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        raise HTTPException(status_code=400, detail="Tenant not provisioned")

    user_id = str(current_user.id)
    filename = file.filename or "unknown.txt"

    # Validate extension
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read file
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    # Extract text in executor (blocking I/O)
    loop = asyncio.get_event_loop()
    try:
        extracted_text = await loop.run_in_executor(
            None, _extract_text_from_bytes, filename, data,
        )
    except Exception as e:
        logger.error("Text extraction failed for %s: %s", filename, e)
        raise HTTPException(status_code=400, detail=f"Could not extract text: {e}")

    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the file")

    content_hash = hashlib.sha256(extracted_text.encode()).hexdigest()[:16]

    # Check if this exact content is already on the desk
    existing = await loop.run_in_executor(
        None,
        partial(_surreal_desk_sync, tenant_id, "get_by_hash", content_hash=content_hash, user_id=user_id),
    )
    if existing:
        # Re-enable if disabled
        if not existing.get("is_enabled"):
            await loop.run_in_executor(
                None,
                partial(_surreal_desk_sync, tenant_id, "update",
                        kos_id=existing["kos_id"], user_id=user_id,
                        updates={"is_enabled": True}),
            )
        return DeskSourceOut(
            kos_id=existing["kos_id"],
            display_name=existing.get("display_name", filename),
            is_enabled=True,
            character_count=existing.get("character_count", len(extracted_text)),
            content_hash=content_hash,
            kos_item_id=existing.get("kos_item_id"),
            created_at=existing.get("created_at"),
        )

    # Create new desk source
    kos_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    source_data = {
        "kos_id": kos_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "display_name": filename,
        "kind": "file_document",
        "is_enabled": True,
        "extracted_text": extracted_text,
        "character_count": len(extracted_text),
        "content_hash": content_hash,
        "kos_item_id": None,
        "created_at": now,
        "updated_at": now,
    }

    await loop.run_in_executor(
        None,
        partial(_surreal_desk_sync, tenant_id, "create", data=source_data),
    )

    # Index into KOS in background
    async def _index_bg():
        try:
            await loop.run_in_executor(
                None,
                partial(_surreal_ingest_desk_sync,
                        tenant_id, user_id, kos_id, filename, extracted_text),
            )
            logger.info("Desk source %s indexed for tenant %s", kos_id, tenant_id)
        except Exception as e:
            logger.error("Desk source indexing failed: %s", e)

    asyncio.create_task(_index_bg())

    return DeskSourceOut(
        kos_id=kos_id,
        display_name=filename,
        is_enabled=True,
        character_count=len(extracted_text),
        content_hash=content_hash,
        created_at=now,
    )


@router.get("/sources", response_model=list[DeskSourceOut])
async def list_desk_sources(current_user: CurrentEDUser) -> Any:
    """List all desk sources for the current user."""
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        return []

    user_id = str(current_user.id)
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(
        None,
        partial(_surreal_desk_sync, tenant_id, "list", user_id=user_id),
    )

    return [
        DeskSourceOut(
            kos_id=r.get("kos_id", ""),
            display_name=r.get("display_name", "Unknown"),
            kind=r.get("kind", "file_document"),
            is_enabled=r.get("is_enabled", True),
            character_count=r.get("character_count", 0),
            content_hash=r.get("content_hash"),
            kos_item_id=r.get("kos_item_id"),
            created_at=r.get("created_at"),
        )
        for r in rows
    ]


@router.patch("/sources/{kos_id}", response_model=DeskSourceOut)
async def toggle_desk_source(
    kos_id: str,
    body: DeskToggleRequest,
    current_user: CurrentEDUser,
) -> Any:
    """Toggle a desk source's enabled state."""
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        raise HTTPException(status_code=400, detail="Tenant not provisioned")

    user_id = str(current_user.id)
    loop = asyncio.get_event_loop()
    updated = await loop.run_in_executor(
        None,
        partial(_surreal_desk_sync, tenant_id, "update",
                kos_id=kos_id, user_id=user_id,
                updates={"is_enabled": body.is_enabled, "updated_at": datetime.utcnow().isoformat()}),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Desk source not found")

    return DeskSourceOut(
        kos_id=updated.get("kos_id", kos_id),
        display_name=updated.get("display_name", "Unknown"),
        kind=updated.get("kind", "file_document"),
        is_enabled=updated.get("is_enabled", body.is_enabled),
        character_count=updated.get("character_count", 0),
        content_hash=updated.get("content_hash"),
        kos_item_id=updated.get("kos_item_id"),
        created_at=updated.get("created_at"),
    )


@router.delete("/sources/{kos_id}")
async def remove_desk_source(kos_id: str, current_user: CurrentEDUser) -> Any:
    """Remove a desk source."""
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        raise HTTPException(status_code=400, detail="Tenant not provisioned")

    user_id = str(current_user.id)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        partial(_surreal_desk_sync, tenant_id, "delete", kos_id=kos_id, user_id=user_id),
    )
    return {"status": "ok"}
