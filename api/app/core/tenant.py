"""Tenant provisioning for CogMem Cloud SaaS.

On signup, creates an isolated SurrealDB database for the new tenant
under the shared `cogmem` namespace.  The database name is derived from
the user's UUID: ``tenant_{user_id_hex}``.
"""

from __future__ import annotations

import logging
import uuid

from surrealdb import Surreal

from app.core.config import settings

logger = logging.getLogger(__name__)

# Base schema applied to every new tenant database.
# This mirrors backend/src/kos/cloud/schema.py so each tenant
# gets the same table structure the cloud API expects.
TENANT_SCHEMA = """
-- KOS core tables (SCHEMALESS to match KOS object store expectations)
DEFINE TABLE IF NOT EXISTS items SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_items_kos_id ON items FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_items_tenant ON items FIELDS tenant_id;

DEFINE TABLE IF NOT EXISTS passages SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_passages_kos_id ON passages FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_passages_item ON passages FIELDS item_id;
DEFINE INDEX IF NOT EXISTS idx_passages_tenant ON passages FIELDS tenant_id;

DEFINE TABLE IF NOT EXISTS entities SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_entities_kos_id ON entities FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_entities_tenant ON entities FIELDS tenant_id;
DEFINE INDEX IF NOT EXISTS idx_entities_name ON entities FIELDS tenant_id, name;

DEFINE TABLE IF NOT EXISTS claims SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_claims_kos_id ON claims FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_claims_tenant ON claims FIELDS tenant_id;

DEFINE TABLE IF NOT EXISTS artifacts SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_artifacts_kos_id ON artifacts FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_artifacts_tenant ON artifacts FIELDS tenant_id;

DEFINE TABLE IF NOT EXISTS agent_actions SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_agent_actions_kos_id ON agent_actions FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_agent_actions_tenant ON agent_actions FIELDS tenant_id;

DEFINE TABLE IF NOT EXISTS outbox_events SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_outbox_event_id ON outbox_events FIELDS event_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_outbox_status ON outbox_events FIELDS status, event_type;

-- Graph edge tables
DEFINE TABLE IF NOT EXISTS mentions SCHEMALESS;
DEFINE TABLE IF NOT EXISTS has_passage SCHEMALESS;
DEFINE TABLE IF NOT EXISTS related_to SCHEMALESS;

-- ACP tables
DEFINE TABLE IF NOT EXISTS memory_strategies SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_strategies_kos_id ON memory_strategies FIELDS kos_id UNIQUE;

DEFINE TABLE IF NOT EXISTS outcome_events SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_outcomes_kos_id ON outcome_events FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_outcomes_tenant ON outcome_events FIELDS tenant_id;

DEFINE TABLE IF NOT EXISTS strategy_proposals SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_proposals_kos_id ON strategy_proposals FIELDS kos_id UNIQUE;
"""


def make_tenant_id(user_id: uuid.UUID) -> str:
    """Derive a SurrealDB-safe database name from a user UUID."""
    return f"tenant_{user_id.hex}"


async def provision_tenant(user_id: uuid.UUID) -> str:
    """Create an isolated SurrealDB database for a new tenant.

    Returns the tenant_id (database name).

    Note: The surrealdb Python library uses a blocking WebSocket connection.
    The Surreal() constructor auto-connects; there is no separate .connect().
    We run the blocking calls in a thread to avoid blocking the event loop.
    """
    import asyncio
    import functools

    tenant_id = make_tenant_id(user_id)
    logger.info("Provisioning tenant database: %s", tenant_id)

    def _provision_sync() -> str:
        db = Surreal(settings.SURREALDB_URL)
        try:
            db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
            db.use(settings.SURREALDB_NAMESPACE, tenant_id)
            db.query(TENANT_SCHEMA)
            logger.info("Tenant %s provisioned successfully", tenant_id)
        finally:
            db.close()
        return tenant_id

    return await asyncio.get_event_loop().run_in_executor(None, _provision_sync)
