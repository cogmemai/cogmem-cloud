"""KOS ingestion pipeline for Evening Draft.

Standalone pipeline — no cogmem-kos dependency.
Stores items, passages, and entities in the user's SurrealDB tenant database.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from surrealdb import SurrealDB

from app.eveningdraft.kos.models import Item, Passage, Entity, TextSpan, Source, EntityType
from app.eveningdraft.kos.chunking import chunk_text
from app.eveningdraft.kos.entities import extract_entities

logger = logging.getLogger(__name__)


async def ingest_content(
    db: SurrealDB,
    tenant_id: str,
    user_id: str,
    title: str,
    content: str,
    source: str = "chat",
    content_type: str = "text/plain",
    metadata: dict | None = None,
) -> str:
    """Ingest content into the Evening Draft KOS pipeline.

    1. Creates an Item
    2. Chunks the text into Passages
    3. Extracts entities via regex
    4. Stores everything in SurrealDB

    Returns the item's kos_id.
    """
    if not content or not content.strip():
        return ""

    item_id = str(uuid.uuid4())

    try:
        source_enum = Source(source)
    except ValueError:
        source_enum = Source.OTHER

    now = datetime.utcnow().isoformat()

    # Step 1: Save item
    item_data = {
        "kos_id": item_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "source": source_enum.value,
        "title": title,
        "content_text": content,
        "content_type": content_type,
        "created_at": now,
        "updated_at": now,
        "metadata": metadata or {},
    }
    try:
        await db.create("ed_items", item_data)
        logger.info("Ingested item %s for tenant %s", item_id, tenant_id)
    except Exception as e:
        logger.error("Failed to save item %s: %s", item_id, e)
        return ""

    # Step 2: Chunk text
    chunks = chunk_text(content)
    passage_ids: list[str] = []

    for i, (chunk_text_str, start, end) in enumerate(chunks):
        p_id = str(uuid.uuid4())
        passage_data = {
            "kos_id": p_id,
            "item_id": item_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "text": chunk_text_str,
            "span_start": start,
            "span_end": end,
            "sequence": i,
            "metadata": {"source_title": title},
        }
        try:
            await db.create("ed_passages", passage_data)
            passage_ids.append(p_id)
        except Exception as e:
            logger.warning("Failed to save passage %s: %s", p_id, e)

    logger.info("Created %d passages for item %s", len(passage_ids), item_id)

    # Step 3: Extract entities
    all_entity_ids: list[str] = []
    for i, (chunk_text_str, _, _) in enumerate(chunks):
        extracted = extract_entities(chunk_text_str)
        for name, entity_type in extracted:
            entity_id = str(uuid.uuid4())
            entity_data = {
                "kos_id": entity_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "name": name,
                "entity_type": entity_type.value,
                "aliases": [],
                "metadata": {},
            }
            try:
                await db.create("ed_entities", entity_data)
                all_entity_ids.append(entity_id)
            except Exception as e:
                logger.warning("Failed to save entity %s: %s", entity_id, e)

    logger.info("Extracted %d entities for item %s", len(all_entity_ids), item_id)

    return item_id


async def ingest_chat_turn(
    db: SurrealDB,
    tenant_id: str,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
) -> tuple[str, str]:
    """Ingest a full chat turn (user + assistant messages).

    Also stores the messages in ed_chat_messages for conversation history.
    Returns (user_item_id, assistant_item_id).
    """
    now = datetime.utcnow().isoformat()

    # Store chat messages
    for role, content in [("user", user_message), ("assistant", assistant_message)]:
        msg_data = {
            "kos_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
            "metadata": {},
        }
        try:
            await db.create("ed_chat_messages", msg_data)
        except Exception as e:
            logger.warning("Failed to save chat message: %s", e)

    # Ingest into KOS pipeline
    user_item_id = await ingest_content(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        title=f"Chat: {user_message[:50]}",
        content=user_message,
        source="chat",
        content_type="text/plain",
        metadata={"role": "user", "session_id": session_id},
    )

    assistant_item_id = await ingest_content(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        title=f"Muse: {assistant_message[:50]}",
        content=assistant_message,
        source="chat",
        content_type="text/plain",
        metadata={"role": "assistant", "session_id": session_id},
    )

    return user_item_id, assistant_item_id
