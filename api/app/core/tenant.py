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
-- KOS core tables
DEFINE TABLE IF NOT EXISTS items SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS kos_id      ON items TYPE string;
DEFINE FIELD IF NOT EXISTS tenant_id   ON items TYPE string;
DEFINE FIELD IF NOT EXISTS source      ON items TYPE string;
DEFINE FIELD IF NOT EXISTS content     ON items TYPE string;
DEFINE FIELD IF NOT EXISTS metadata    ON items TYPE object;
DEFINE FIELD IF NOT EXISTS created_at  ON items TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS idx_items_tenant ON items FIELDS tenant_id;

DEFINE TABLE IF NOT EXISTS passages SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS kos_id      ON passages TYPE string;
DEFINE FIELD IF NOT EXISTS item_id     ON passages TYPE string;
DEFINE FIELD IF NOT EXISTS tenant_id   ON passages TYPE string;
DEFINE FIELD IF NOT EXISTS text        ON passages TYPE string;
DEFINE FIELD IF NOT EXISTS embedding   ON passages TYPE option<array>;
DEFINE FIELD IF NOT EXISTS position    ON passages TYPE int;
DEFINE FIELD IF NOT EXISTS created_at  ON passages TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS idx_passages_item ON passages FIELDS item_id;

DEFINE TABLE IF NOT EXISTS entities SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS kos_id      ON entities TYPE string;
DEFINE FIELD IF NOT EXISTS tenant_id   ON entities TYPE string;
DEFINE FIELD IF NOT EXISTS name        ON entities TYPE string;
DEFINE FIELD IF NOT EXISTS entity_type ON entities TYPE string;
DEFINE FIELD IF NOT EXISTS properties  ON entities TYPE object;
DEFINE FIELD IF NOT EXISTS created_at  ON entities TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS idx_entities_name ON entities FIELDS name;

DEFINE TABLE IF NOT EXISTS claims SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS kos_id      ON claims TYPE string;
DEFINE FIELD IF NOT EXISTS tenant_id   ON claims TYPE string;
DEFINE FIELD IF NOT EXISTS subject     ON claims TYPE string;
DEFINE FIELD IF NOT EXISTS predicate   ON claims TYPE string;
DEFINE FIELD IF NOT EXISTS object      ON claims TYPE string;
DEFINE FIELD IF NOT EXISTS confidence  ON claims TYPE float;
DEFINE FIELD IF NOT EXISTS status      ON claims TYPE string;
DEFINE FIELD IF NOT EXISTS created_at  ON claims TYPE datetime DEFAULT time::now();

-- ACP tables
DEFINE TABLE IF NOT EXISTS memory_strategies SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS kos_id      ON memory_strategies TYPE string;
DEFINE FIELD IF NOT EXISTS scope_type  ON memory_strategies TYPE string;
DEFINE FIELD IF NOT EXISTS scope_id    ON memory_strategies TYPE string;
DEFINE FIELD IF NOT EXISTS version     ON memory_strategies TYPE int;
DEFINE FIELD IF NOT EXISTS status      ON memory_strategies TYPE string;
DEFINE FIELD IF NOT EXISTS created_by  ON memory_strategies TYPE string;
DEFINE FIELD IF NOT EXISTS rationale   ON memory_strategies TYPE string;
DEFINE FIELD IF NOT EXISTS retrieval_policy ON memory_strategies TYPE object;
DEFINE FIELD IF NOT EXISTS document_policy  ON memory_strategies TYPE object;
DEFINE FIELD IF NOT EXISTS vector_policy    ON memory_strategies TYPE object;
DEFINE FIELD IF NOT EXISTS graph_policy     ON memory_strategies TYPE object;
DEFINE FIELD IF NOT EXISTS claim_policy     ON memory_strategies TYPE object;
DEFINE FIELD IF NOT EXISTS created_at  ON memory_strategies TYPE datetime DEFAULT time::now();

DEFINE TABLE IF NOT EXISTS outcome_events SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS kos_id       ON outcome_events TYPE string;
DEFINE FIELD IF NOT EXISTS tenant_id    ON outcome_events TYPE string;
DEFINE FIELD IF NOT EXISTS strategy_id  ON outcome_events TYPE string;
DEFINE FIELD IF NOT EXISTS outcome_type ON outcome_events TYPE string;
DEFINE FIELD IF NOT EXISTS source       ON outcome_events TYPE string;
DEFINE FIELD IF NOT EXISTS metrics      ON outcome_events TYPE object;
DEFINE FIELD IF NOT EXISTS context      ON outcome_events TYPE object;
DEFINE FIELD IF NOT EXISTS created_at   ON outcome_events TYPE datetime DEFAULT time::now();

DEFINE TABLE IF NOT EXISTS strategy_proposals SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS kos_id              ON strategy_proposals TYPE string;
DEFINE FIELD IF NOT EXISTS base_strategy_id    ON strategy_proposals TYPE string;
DEFINE FIELD IF NOT EXISTS proposed_strategy_id ON strategy_proposals TYPE string;
DEFINE FIELD IF NOT EXISTS change_summary      ON strategy_proposals TYPE string;
DEFINE FIELD IF NOT EXISTS status              ON strategy_proposals TYPE string;
DEFINE FIELD IF NOT EXISTS created_at          ON strategy_proposals TYPE datetime DEFAULT time::now();
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
