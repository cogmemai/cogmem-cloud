"""KOS kernel routes with tenant-scoped SurrealDB providers.

Wraps the open-source KOS kernel HTTP routes (search, items, entities)
and overrides their dependency injection to use per-tenant SurrealDB
connections. This ensures each user's data is fully isolated.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import CurrentUser
from kos_extensions.tenant_deps import get_tenant_registry, TenantRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kos", tags=["kos"])


@router.get("/health")
async def kos_health(reg: TenantRegistry = Depends(get_tenant_registry)):
    """Check SurrealDB connectivity for the current tenant."""
    healthy = await reg.client.health_check()
    return {
        "status": "healthy" if healthy else "unhealthy",
        "mode": "cloud-tenant",
        "providers": {
            "surrealdb": "healthy" if healthy else "unhealthy",
        },
        "contracts": {
            "object_store": "surrealdb",
            "outbox_store": "surrealdb",
            "text_search": "surrealdb",
            "vector_search": "surrealdb",
            "graph_search": "surrealdb",
            "strategy_store": "surrealdb",
            "outcome_store": "surrealdb",
            "proposal_store": "surrealdb",
        },
    }


# --- Items ---

@router.get("/items/{item_id}")
async def get_item(item_id: str, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Get an item with its passages."""
    from kos.core.models.ids import KosId

    item = await reg.object_store.get_item(KosId(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    passages = await reg.object_store.get_passages_for_item(KosId(item_id))

    return {
        "kos_id": str(item.kos_id),
        "tenant_id": str(item.tenant_id) if item.tenant_id else None,
        "source": item.source.value if item.source else None,
        "title": item.title,
        "content_text": item.content_text,
        "content_type": item.content_type,
        "created_at": str(item.created_at) if item.created_at else None,
        "metadata": item.metadata,
        "passages": [
            {
                "kos_id": str(p.kos_id),
                "text": p.text,
                "sequence": p.sequence,
                "metadata": p.metadata,
            }
            for p in passages
        ],
    }


@router.post("/items", status_code=201)
async def create_item(request: Request, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Create a new item and trigger processing."""
    import uuid
    from datetime import datetime
    from kos.core.models.ids import KosId, TenantId, UserId, Source
    from kos.core.models.item import Item
    from kos.core.events.envelope import EventEnvelope
    from kos.core.contracts.stores.outbox_store import OutboxEvent

    body = await request.json()
    kos_id = KosId(str(uuid.uuid4()))

    try:
        source = Source(body.get("source", "other"))
    except ValueError:
        source = Source.OTHER

    item = Item(
        kos_id=kos_id,
        tenant_id=TenantId(body.get("tenant_id", "")),
        user_id=UserId(body.get("user_id", "")),
        source=source,
        external_id=body.get("external_id"),
        title=body.get("title", ""),
        content_text=body.get("content_text", ""),
        content_type=body.get("content_type", "text/plain"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata=body.get("metadata", {}),
    )

    saved_item = await reg.object_store.save_item(item)

    event = EventEnvelope.item_upserted(
        tenant_id=body.get("tenant_id", ""),
        user_id=body.get("user_id", ""),
        item_id=kos_id,
        source_agent="api",
    )

    outbox_event = OutboxEvent(
        event_id=event.event_id,
        event_type=event.event_type.value,
        tenant_id=event.tenant_id,
        payload=event.payload,
        created_at=event.created_at,
    )
    await reg.outbox_store.enqueue_event(outbox_event)

    return {
        "kos_id": str(saved_item.kos_id),
        "tenant_id": str(saved_item.tenant_id) if saved_item.tenant_id else None,
        "title": saved_item.title,
        "content_type": saved_item.content_type,
        "created_at": str(saved_item.created_at) if saved_item.created_at else None,
    }


# --- Search ---

@router.post("/search")
async def search(request: Request, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Execute a search query against the tenant's knowledge base."""
    from kos.core.planning.search_first import SearchFirstPlan, SearchFirstRequest

    body = await request.json()

    plan = SearchFirstPlan(
        text_search=reg.text_search,
        object_store=reg.object_store,
        graph_search=reg.graph_search,
    )

    plan_request = SearchFirstRequest(
        query=body.get("query", ""),
        tenant_id=body.get("tenant_id"),
        user_id=body.get("user_id"),
        filters=body.get("filters"),
        facets_requested=body.get("facets_requested"),
        limit=body.get("limit", 10),
        offset=body.get("offset", 0),
    )

    result = await plan.execute(plan_request)

    return {
        "hits": [
            {
                "kos_id": str(hit.kos_id),
                "title": hit.title,
                "snippet": hit.snippet,
                "highlights": hit.highlights,
                "score": hit.score,
                "source": hit.source,
                "content_type": hit.content_type,
            }
            for hit in result.hits
        ],
        "total": result.total,
        "took_ms": result.took_ms,
    }


# --- Entities ---

@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Get an entity by ID."""
    from kos.core.models.ids import KosId

    # Use graph_search if available, otherwise return 404
    if reg.graph_search is None:
        raise HTTPException(status_code=501, detail="Graph search not available")

    entity = await reg.graph_search.get_entity(KosId(entity_id))
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return {
        "kos_id": str(entity.kos_id),
        "name": entity.name,
        "entity_type": entity.entity_type,
        "properties": entity.properties,
    }


# --- Ingestion ---

class LogsQuery(BaseModel):
    limit: int = 100
    offset: int = 0
    level: str | None = None
    agent: str | None = None
    event_type: str | None = None
    correlation_id: str | None = None


@router.get("/logs")
async def get_kos_logs(
    current_user: CurrentUser,
    reg: TenantRegistry = Depends(get_tenant_registry),
    limit: int = 100,
    offset: int = 0,
    level: str | None = None,
    agent: str | None = None,
    event_type: str | None = None,
    correlation_id: str | None = None,
):
    """Query the kos_logs table (application-level pipeline logs)."""
    where_clauses = []
    params: dict = {"limit": limit, "offset": offset}

    if level:
        where_clauses.append("level = $level")
        params["level"] = level
    if agent:
        where_clauses.append("agent = $agent")
        params["agent"] = agent
    if event_type:
        where_clauses.append("event_type CONTAINS $event_type")
        params["event_type"] = event_type
    if correlation_id:
        where_clauses.append("correlation_id = $correlation_id")
        params["correlation_id"] = correlation_id

    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    query = f"SELECT * FROM kos_logs {where} ORDER BY created_at DESC LIMIT $limit START $offset;"
    results = await reg.client.query(query, params)

    count_query = f"SELECT count() FROM kos_logs {where} GROUP ALL;"
    count_result = await reg.client.query(count_query, params)
    total = count_result[0].get("count", 0) if count_result else 0

    return {"data": results, "total": total, "limit": limit, "offset": offset}


@router.get("/audit-log")
async def get_audit_log(
    current_user: CurrentUser,
    reg: TenantRegistry = Depends(get_tenant_registry),
    limit: int = 100,
    offset: int = 0,
    table_name: str | None = None,
    action: str | None = None,
):
    """Query the audit_log table (DB-level event triggers)."""
    where_clauses = []
    params: dict = {"limit": limit, "offset": offset}

    if table_name:
        where_clauses.append("table_name = $table_name")
        params["table_name"] = table_name
    if action:
        where_clauses.append("action = $action")
        params["action"] = action

    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    query = f"SELECT * FROM audit_log {where} ORDER BY created_at DESC LIMIT $limit START $offset;"
    results = await reg.client.query(query, params)

    count_query = f"SELECT count() FROM audit_log {where} GROUP ALL;"
    count_result = await reg.client.query(count_query, params)
    total = count_result[0].get("count", 0) if count_result else 0

    return {"data": results, "total": total, "limit": limit, "offset": offset}


@router.get("/logs/stats")
async def get_log_stats(
    current_user: CurrentUser,
    reg: TenantRegistry = Depends(get_tenant_registry),
):
    """Aggregate stats for the logging dashboard."""
    kos_count = await reg.client.query("SELECT count() FROM kos_logs GROUP ALL;")
    audit_count = await reg.client.query("SELECT count() FROM audit_log GROUP ALL;")
    items_count = await reg.client.query("SELECT count() FROM items GROUP ALL;")
    passages_count = await reg.client.query("SELECT count() FROM passages GROUP ALL;")
    entities_count = await reg.client.query("SELECT count() FROM entities GROUP ALL;")

    agents = await reg.client.query("SELECT agent, count() FROM kos_logs GROUP BY agent;")
    levels = await reg.client.query("SELECT level, count() FROM kos_logs GROUP BY level;")
    tables = await reg.client.query("SELECT table_name, action, count() FROM audit_log GROUP BY table_name, action;")

    return {
        "kos_logs_total": kos_count[0].get("count", 0) if kos_count else 0,
        "audit_log_total": audit_count[0].get("count", 0) if audit_count else 0,
        "items_total": items_count[0].get("count", 0) if items_count else 0,
        "passages_total": passages_count[0].get("count", 0) if passages_count else 0,
        "entities_total": entities_count[0].get("count", 0) if entities_count else 0,
        "agents": agents,
        "levels": levels,
        "audit_by_table": tables,
    }


# --- Ingestion ---

class IngestChatRequest(BaseModel):
    user_message: str
    assistant_message: str


@router.post("/ingest")
async def ingest_chat(
    body: IngestChatRequest,
    current_user: CurrentUser,
    reg: TenantRegistry = Depends(get_tenant_registry),
):
    """Ingest a chat turn (user + assistant messages) into the KOS pipeline.

    Runs ChunkAgent + EntityExtractAgent inline to create Items, Passages,
    and Entities in the tenant's SurrealDB database.
    """
    from kos_extensions.ingest import ingest_chat_turn

    user_item_id, asst_item_id = await ingest_chat_turn(
        registry=reg,
        tenant_id=current_user.tenant_id,
        user_id=str(current_user.id),
        user_message=body.user_message,
        assistant_message=body.assistant_message,
    )

    logger.info(
        "KOS ingested chat turn for tenant %s: user=%s assistant=%s",
        current_user.tenant_id, user_item_id, asst_item_id,
    )

    return {
        "status": "ingested",
        "user_item_id": user_item_id,
        "assistant_item_id": asst_item_id,
    }
