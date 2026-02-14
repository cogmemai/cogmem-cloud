"""KOS ingestion pipeline for the cloud offering.

Performs chunking and entity extraction **inline** — we already have the
item content in memory so there is no need to round-trip through
``object_store.get_item()`` (which can fail due to SurrealDB SDK param
binding quirks).

Every step is logged to the ``kos_logs`` table via :class:`KosLogger` so
the full pipeline execution is observable in Surrealist / the cockpit.

Usage:
    from kos_extensions.ingest import ingest_content

    await ingest_content(
        registry=tenant_registry,
        tenant_id="tenant_abc123",
        user_id="user-uuid",
        title="Chat message",
        content="The actual text content...",
        source="chat",
        content_type="text/plain",
    )
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from kos.core.models.ids import KosId, TenantId, UserId, Source
from kos.core.models.item import Item
from kos.core.models.passage import Passage, TextSpan
from kos.core.models.entity import Entity, EntityType

from kos_extensions.registry import CloudProviderRegistry
from kos_extensions.kos_logging import KosLogger

logger = logging.getLogger(__name__)

# ── Inline chunking ──────────────────────────────────────────────────────────

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def _chunk_text(text: str) -> list[tuple[str, int, int]]:
    """Split *text* into overlapping chunks.

    Always produces at least one chunk for non-empty text.
    Returns list of ``(chunk_text, start_offset, end_offset)``.
    """
    if not text or not text.strip():
        return []

    # Short text → single chunk
    if len(text) <= CHUNK_SIZE:
        return [(text.strip(), 0, len(text))]

    chunks: list[tuple[str, int, int]] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        # Try to break at a natural boundary
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", " "]:
                last_sep = text.rfind(sep, start, end)
                if last_sep > start:
                    end = last_sep + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, start, end))
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


# ── Inline entity extraction (regex) ─────────────────────────────────────────

ENTITY_PATTERNS: dict[EntityType, list[str]] = {
    EntityType.PERSON: [
        r"\b(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+",
        r"\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?=\s+(?:said|says|told|wrote|is|was|has|had))",
    ],
    EntityType.ORGANIZATION: [
        r"\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\s+(?:Inc\.|Corp\.|LLC|Ltd\.|Company|Corporation|Foundation|Institute|University|College)\b",
        r"\b(?:The\s+)?[A-Z][A-Za-z]+\s+(?:Group|Team|Department|Division|Board)\b",
    ],
    EntityType.LOCATION: [
        r"\b(?:New\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s+[A-Z]{2}\b",
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:City|County|State|Country|Province|Region)\b",
    ],
    EntityType.DATE: [
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    ],
}


def _extract_entities_regex(text: str) -> list[tuple[str, EntityType]]:
    """Extract named entities from *text* using regex patterns."""
    entities: list[tuple[str, EntityType]] = []
    seen: set[str] = set()
    for entity_type, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            for match in re.findall(pattern, text):
                name = match.strip()
                if name and name not in seen and len(name) > 2:
                    seen.add(name)
                    entities.append((name, entity_type))
    return entities


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def ingest_content(
    registry: CloudProviderRegistry,
    tenant_id: str,
    user_id: str,
    title: str,
    content: str,
    source: str = "chat",
    content_type: str = "text/plain",
    metadata: dict | None = None,
    kos_logger: KosLogger | None = None,
) -> str:
    """Ingest content into the KOS pipeline.

    1. Creates an Item in the tenant's SurrealDB
    2. Chunks the text inline into Passages (no get_item round-trip)
    3. Extracts entities from each passage via regex
    4. Creates graph nodes + MENTIONS edges

    Returns the item's kos_id.
    """
    if not content or not content.strip():
        return ""

    item_id = KosId(str(uuid.uuid4()))
    kl = kos_logger or KosLogger(registry.client)
    tid = TenantId(tenant_id)
    uid = UserId(user_id)

    try:
        source_enum = Source(source)
    except ValueError:
        source_enum = Source.OTHER

    item = Item(
        kos_id=item_id,
        tenant_id=tid,
        user_id=uid,
        source=source_enum,
        title=title,
        content_text=content,
        content_type=content_type,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata=metadata or {},
    )

    # ── Step 1: Save the item ────────────────────────────────────────────
    async with kl.timed("cloud_ingest", "save_item", f"Saving item {item_id}", item_id=str(item_id),
                         metadata={"title": title, "content_len": len(content), "source": source}):
        await registry.object_store.save_item(item)
    logger.info("Ingested item %s for tenant %s", item_id, tenant_id)

    # ── Step 2: Chunk text inline ────────────────────────────────────────
    async with kl.timed("cloud_ingest", "chunk_text", f"Chunking item {item_id}", item_id=str(item_id)):
        chunks = _chunk_text(content)

    passage_ids: list[str] = []
    passages: list[Passage] = []
    for i, (chunk_text, start, end) in enumerate(chunks):
        p_id = str(uuid.uuid4())
        passage = Passage(
            kos_id=KosId(p_id),
            item_id=item_id,
            tenant_id=tid,
            user_id=uid,
            text=chunk_text,
            span=TextSpan(start=start, end=end),
            sequence=i,
            metadata={"source_title": title},
        )
        await registry.object_store.save_passage(passage)
        passage_ids.append(p_id)
        passages.append(passage)

    await kl.log("cloud_ingest", "chunk_result",
                 f"Created {len(passages)} passage(s) for item {item_id}",
                 item_id=str(item_id), passage_ids=passage_ids,
                 metadata={"chunk_count": len(chunks), "passage_count": len(passages)})
    logger.info("Created %d passages for item %s", len(passages), item_id)

    # ── Step 3: Extract entities from each passage ───────────────────────
    all_entity_ids: list[str] = []
    for passage in passages:
        async with kl.timed("cloud_ingest", "extract_entities",
                            f"Extracting entities from passage {passage.kos_id}",
                            item_id=str(item_id)):
            extracted = _extract_entities_regex(passage.text)

        for name, entity_type in extracted:
            # Check for existing entity with same name
            existing = await registry.object_store.find_entity_by_name(tid, name)
            if existing:
                entity_id = existing.kos_id
            else:
                entity_id = KosId(str(uuid.uuid4()))
                entity = Entity(
                    kos_id=entity_id,
                    tenant_id=tid,
                    user_id=uid,
                    name=name,
                    type=entity_type,
                    aliases=[],
                    metadata={},
                )
                await registry.object_store.save_entity(entity)

                # Create graph node
                try:
                    await registry.graph_search.create_entity_node(
                        kos_id=entity_id,
                        tenant_id=tid,
                        user_id=uid,
                        name=name,
                        entity_type=entity_type.value,
                    )
                except Exception as e:
                    logger.warning("Failed to create entity node: %s", e)

            # Create MENTIONS edge (passage → entity)
            try:
                await registry.graph_search.create_mentions_edge(
                    passage_id=passage.kos_id,
                    entity_id=entity_id,
                )
            except Exception as e:
                logger.warning("Failed to create mentions edge: %s", e)

            if str(entity_id) not in all_entity_ids:
                all_entity_ids.append(str(entity_id))

    await kl.log("cloud_ingest", "extract_result",
                 f"Extracted {len(all_entity_ids)} entity(ies) from {len(passages)} passage(s)",
                 item_id=str(item_id), entity_ids=all_entity_ids,
                 metadata={"entity_count": len(all_entity_ids)})
    logger.info("Extracted %d entities for item %s", len(all_entity_ids), item_id)

    return str(item_id)


async def ingest_chat_turn(
    registry: CloudProviderRegistry,
    tenant_id: str,
    user_id: str,
    user_message: str,
    assistant_message: str,
) -> tuple[str, str]:
    """Ingest a full chat turn (user message + assistant response).

    Returns (user_item_id, assistant_item_id).
    """
    kl = KosLogger(registry.client)

    await kl.log("cloud_ingest", "pipeline_start", "Starting chat turn ingestion",
                 metadata={"tenant_id": tenant_id, "user_id": user_id,
                           "user_msg_len": len(user_message),
                           "assistant_msg_len": len(assistant_message)})

    user_item_id = await ingest_content(
        registry=registry,
        tenant_id=tenant_id,
        user_id=user_id,
        title="User message",
        content=user_message,
        source="chat",
        content_type="text/plain",
        metadata={"role": "user"},
        kos_logger=kl,
    )

    assistant_item_id = await ingest_content(
        registry=registry,
        tenant_id=tenant_id,
        user_id=user_id,
        title="Assistant response",
        content=assistant_message,
        source="chat",
        content_type="text/plain",
        metadata={"role": "assistant"},
        kos_logger=kl,
    )

    await kl.log("cloud_ingest", "pipeline_end", "Chat turn ingestion complete",
                 metadata={"user_item_id": user_item_id, "assistant_item_id": assistant_item_id})

    return user_item_id, assistant_item_id
