"""KOS ingestion pipeline for the cloud offering.

Runs the ChunkAgent and EntityExtractAgent inline (no outbox polling)
to process content into searchable knowledge within a tenant's SurrealDB.

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

    chunk_events = await chunk_agent.process_event(item_event)
    logger.info("ChunkAgent produced %d events for item %s", len(chunk_events), item_id)

    # Step 3: Run EntityExtractAgent on each PASSAGES_CREATED event
    entity_agent = EntityExtractAgent(
        object_store=registry.object_store,
        outbox_store=registry.outbox_store,
        graph_search=registry.graph_search,
        use_llm=False,  # Use regex extraction (fast, no API calls)
    )

    for event in chunk_events:
        if event.event_type == EventType.PASSAGES_CREATED:
            entity_events = await entity_agent.process_event(event)
            logger.info(
                "EntityExtractAgent produced %d events from passages",
                len(entity_events),
            )

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
    user_item_id = await ingest_content(
        registry=registry,
        tenant_id=tenant_id,
        user_id=user_id,
        title="User message",
        content=user_message,
        source="chat",
        content_type="text/plain",
        metadata={"role": "user"},
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
    )

    return user_item_id, assistant_item_id
