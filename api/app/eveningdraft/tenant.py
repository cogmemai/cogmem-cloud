"""Tenant provisioning for Evening Draft users.

Same SurrealDB instance as CogMem but under the 'eveningdraft' namespace
to keep data fully isolated.
"""

from __future__ import annotations

import logging
import uuid

from surrealdb import Surreal

from app.core.config import settings

logger = logging.getLogger(__name__)

ED_NAMESPACE = "eveningdraft"

# Evening Draft KOS schema — standalone, no cogmem-kos dependency
ED_TENANT_SCHEMA = """
-- Evening Draft KOS tables (SCHEMALESS)

DEFINE TABLE IF NOT EXISTS ed_items SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_ed_items_kos_id ON ed_items FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ed_items_tenant ON ed_items FIELDS tenant_id;
DEFINE INDEX IF NOT EXISTS idx_ed_items_user ON ed_items FIELDS user_id;

DEFINE TABLE IF NOT EXISTS ed_passages SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_ed_passages_kos_id ON ed_passages FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ed_passages_item ON ed_passages FIELDS item_id;
DEFINE INDEX IF NOT EXISTS idx_ed_passages_tenant ON ed_passages FIELDS tenant_id;

DEFINE TABLE IF NOT EXISTS ed_entities SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_ed_entities_kos_id ON ed_entities FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ed_entities_tenant ON ed_entities FIELDS tenant_id;
DEFINE INDEX IF NOT EXISTS idx_ed_entities_name ON ed_entities FIELDS tenant_id, name;

DEFINE TABLE IF NOT EXISTS ed_chat_messages SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_ed_chat_kos_id ON ed_chat_messages FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ed_chat_session ON ed_chat_messages FIELDS session_id;
DEFINE INDEX IF NOT EXISTS idx_ed_chat_user ON ed_chat_messages FIELDS user_id;
DEFINE INDEX IF NOT EXISTS idx_ed_chat_created ON ed_chat_messages FIELDS created_at;

DEFINE TABLE IF NOT EXISTS ed_journal_entries SCHEMALESS;
DEFINE INDEX IF NOT EXISTS idx_ed_journal_kos_id ON ed_journal_entries FIELDS kos_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ed_journal_user ON ed_journal_entries FIELDS user_id;
DEFINE INDEX IF NOT EXISTS idx_ed_journal_updated ON ed_journal_entries FIELDS updated_at;
"""


def make_tenant_id(user_id: uuid.UUID) -> str:
    """Derive a SurrealDB-safe database name from a user UUID."""
    return f"ed_tenant_{user_id.hex}"


async def provision_tenant(user_id: uuid.UUID) -> str:
    """Create an isolated SurrealDB database for a new Evening Draft tenant.

    Returns the tenant_id (database name).
    Uses the 'eveningdraft' namespace instead of 'cogmem'.
    """
    import asyncio

    tenant_id = make_tenant_id(user_id)
    logger.info("Provisioning Evening Draft tenant database: %s", tenant_id)

    def _provision_sync() -> str:
        db = Surreal(settings.SURREALDB_URL)
        try:
            db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
            db.use(ED_NAMESPACE, tenant_id)
            db.query(ED_TENANT_SCHEMA)
            logger.info("Evening Draft tenant %s provisioned successfully", tenant_id)
        finally:
            db.close()
        return tenant_id

    return await asyncio.get_event_loop().run_in_executor(None, _provision_sync)
