"""Tenant provisioning for Evening Draft users.

Same SurrealDB instance as CogMem but under the 'eveningdraft' namespace
to keep data fully isolated.
"""

from __future__ import annotations

import logging
import uuid

from surrealdb import Surreal

from app.core.config import settings
from app.core.tenant import TENANT_SCHEMA  # reuse the same table schema

logger = logging.getLogger(__name__)

ED_NAMESPACE = "eveningdraft"


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
            db.query(TENANT_SCHEMA)
            logger.info("Evening Draft tenant %s provisioned successfully", tenant_id)
        finally:
            db.close()
        return tenant_id

    return await asyncio.get_event_loop().run_in_executor(None, _provision_sync)
