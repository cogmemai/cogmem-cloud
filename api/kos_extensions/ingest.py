"""KOS ingestion pipeline for the cloud offering.

Runs the ChunkAgent and EntityExtractAgent inline (no outbox polling)
to process content into searchable knowledge within a tenant's SurrealDB.

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
import uuid
from datetime import datetime

from kos.core.events.event_types import EventType
from kos.core.events.envelope import EventEnvelope
from kos.core.models.ids import KosId, TenantId, UserId, Source
from kos.core.models.item import Item
from kos.core.contracts.stores.outbox_store import OutboxEvent
from kos.agents.ingest.chunk_agent import ChunkAgent
from kos.agents.extract.entity_extract_agent import EntityExtractAgent

from kos_extensions.registry import CloudProviderRegistry
from kos_extensions.kos_logging import KosLogger

logger = logging.getLogger(__name__)


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
    2. Runs ChunkAgent to split into Passages
    3. Runs EntityExtractAgent to extract entities from passages

    Returns the item's kos_id.
    """
    if not content or not content.strip():
        return ""

    item_id = KosId(str(uuid.uuid4()))
    kl = kos_logger or KosLogger(registry.client)

    try:
        source_enum = Source(source)
    except ValueError:
        source_enum = Source.OTHER

    item = Item(
        kos_id=item_id,
        tenant_id=TenantId(tenant_id),
        user_id=UserId(user_id),
        source=source_enum,
        title=title,
        content_text=content,
        content_type=content_type,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata=metadata or {},
    )

    # Step 1: Save the item
    async with kl.timed("cloud_ingest", "save_item", f"Saving item {item_id}", item_id=str(item_id),
                         metadata={"title": title, "content_len": len(content), "source": source}):
        await registry.object_store.save_item(item)
    logger.info("Ingested item %s for tenant %s", item_id, tenant_id)

    # Step 2: Run ChunkAgent
    chunk_agent = ChunkAgent(
        object_store=registry.object_store,
        outbox_store=registry.outbox_store,
        chunk_size=500,
        chunk_overlap=50,
    )

    item_event = EventEnvelope.item_upserted(
        tenant_id=tenant_id,
        user_id=user_id,
        item_id=item_id,
        source_agent="cloud_ingest",
    )

    async with kl.timed("chunk_agent", "chunk_item", f"Chunking item {item_id}", item_id=str(item_id)):
        chunk_events = await chunk_agent.process_event(item_event)

    passage_ids: list[str] = []
    for evt in chunk_events:
        passage_ids.extend(evt.payload.get("passage_ids", []))

    await kl.log("chunk_agent", "chunk_result", f"Produced {len(chunk_events)} events, {len(passage_ids)} passages",
                 item_id=str(item_id), passage_ids=passage_ids,
                 metadata={"event_count": len(chunk_events), "passage_count": len(passage_ids)})
    logger.info("ChunkAgent produced %d events for item %s", len(chunk_events), item_id)

    # Step 3: Run EntityExtractAgent on each PASSAGES_CREATED event
    entity_agent = EntityExtractAgent(
        object_store=registry.object_store,
        outbox_store=registry.outbox_store,
        graph_search=registry.graph_search,
        use_llm=False,  # Use regex extraction (fast, no API calls)
    )

    all_entity_ids: list[str] = []
    for event in chunk_events:
        if event.event_type == EventType.PASSAGES_CREATED:
            async with kl.timed("entity_extract_agent", "extract_entities",
                                f"Extracting entities for item {item_id}", item_id=str(item_id)):
                entity_events = await entity_agent.process_event(event)

            for e_evt in entity_events:
                all_entity_ids.extend(e_evt.payload.get("entity_ids", []))

            await kl.log("entity_extract_agent", "extract_result",
                         f"Extracted {len(entity_events)} events, {len(all_entity_ids)} entities",
                         item_id=str(item_id), entity_ids=all_entity_ids,
                         metadata={"event_count": len(entity_events), "entity_count": len(all_entity_ids)})
            logger.info("EntityExtractAgent produced %d events from passages", len(entity_events))

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
