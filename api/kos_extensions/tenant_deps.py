"""Per-request tenant-scoped SurrealDB dependencies.

Each authenticated request gets a SurrealDBClient connected to the user's
isolated tenant database (tenant_{user_id_hex}) within the shared `cogmem`
namespace. This ensures complete data fencing between users.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import Depends

from app.api.deps import CurrentUser
from app.core.config import settings
from kos_extensions.registry import CloudProviderRegistry
from kos.providers.surrealdb.client import SurrealDBClient

logger = logging.getLogger(__name__)


async def get_tenant_registry(
    current_user: CurrentUser,
) -> AsyncGenerator[CloudProviderRegistry, None]:
    """Create a tenant-scoped CloudProviderRegistry for the current user.

    Connects to the user's isolated SurrealDB database and yields a registry
    with all KOS providers wired to that database. The connection is closed
    after the request completes.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id or tenant_id.startswith("pending_"):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Tenant database not yet provisioned. Please try again later.",
        )

    client = SurrealDBClient(
        url=settings.SURREALDB_URL,
        namespace=settings.SURREALDB_NAMESPACE,
        database=tenant_id,
        user=settings.SURREALDB_USER,
        password=settings.SURREALDB_PASSWORD,
    )
    await client.connect()

    registry = CloudProviderRegistry(client)
    try:
        yield registry
    finally:
        await registry.close()


TenantRegistry = CloudProviderRegistry
