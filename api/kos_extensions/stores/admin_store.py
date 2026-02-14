"""SurrealDB implementation of AdminStore for cloud offering."""

from datetime import datetime
from typing import Any

from kos.core.contracts.stores.admin_store import (
    AdminStore,
    ConnectorConfig,
    RunLog,
    Tenant,
    User,
)
from kos.providers.surrealdb.client import SurrealDBClient


class SurrealDBAdminStore(AdminStore):
    """SurrealDB-backed AdminStore for the cloud offering."""

    def __init__(self, client: SurrealDBClient) -> None:
        self._client = client

    async def create_tenant(self, tenant: Tenant) -> Tenant:
        data = tenant.model_dump(mode="json")
        data["id"] = f"tenants:{tenant.tenant_id}"
        await self._client.query(
            "CREATE tenants SET tenant_id = $tenant_id, name = $name, "
            "created_at = $created_at, metadata = $metadata",
            {
                "tenant_id": tenant.tenant_id,
                "name": tenant.name,
                "created_at": tenant.created_at.isoformat(),
                "metadata": tenant.metadata,
            },
        )
        return tenant

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        results = await self._client.query(
            "SELECT * FROM tenants WHERE tenant_id = $tenant_id LIMIT 1",
            {"tenant_id": tenant_id},
        )
        if not results:
            return None
        return Tenant.model_validate(self._client.strip_surreal_id(results[0]))

    async def list_tenants(self) -> list[Tenant]:
        results = await self._client.query("SELECT * FROM tenants ORDER BY created_at DESC")
        return [Tenant.model_validate(self._client.strip_surreal_id(r)) for r in results]

    async def create_user(self, user: User) -> User:
        await self._client.query(
            "CREATE users SET user_id = $user_id, tenant_id = $tenant_id, "
            "email = $email, name = $name, created_at = $created_at, metadata = $metadata",
            {
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat(),
                "metadata": user.metadata,
            },
        )
        return user

    async def get_user(self, tenant_id: str, user_id: str) -> User | None:
        results = await self._client.query(
            "SELECT * FROM users WHERE tenant_id = $tenant_id AND user_id = $user_id LIMIT 1",
            {"tenant_id": tenant_id, "user_id": user_id},
        )
        if not results:
            return None
        return User.model_validate(self._client.strip_surreal_id(results[0]))

    async def list_users(self, tenant_id: str) -> list[User]:
        results = await self._client.query(
            "SELECT * FROM users WHERE tenant_id = $tenant_id ORDER BY created_at DESC",
            {"tenant_id": tenant_id},
        )
        return [User.model_validate(self._client.strip_surreal_id(r)) for r in results]

    async def save_connector_config(self, config: ConnectorConfig) -> ConnectorConfig:
        await self._client.query(
            "DELETE FROM connector_configs WHERE config_id = $config_id",
            {"config_id": config.config_id},
        )
        await self._client.query(
            "CREATE connector_configs SET config_id = $config_id, tenant_id = $tenant_id, "
            "connector_type = $connector_type, name = $name, credentials = $credentials, "
            "settings = $settings, enabled = $enabled, created_at = $created_at, "
            "updated_at = $updated_at",
            {
                "config_id": config.config_id,
                "tenant_id": config.tenant_id,
                "connector_type": config.connector_type,
                "name": config.name,
                "credentials": config.credentials,
                "settings": config.settings,
                "enabled": config.enabled,
                "created_at": config.created_at.isoformat(),
                "updated_at": config.updated_at.isoformat(),
            },
        )
        return config

    async def get_connector_config(self, config_id: str) -> ConnectorConfig | None:
        results = await self._client.query(
            "SELECT * FROM connector_configs WHERE config_id = $config_id LIMIT 1",
            {"config_id": config_id},
        )
        if not results:
            return None
        return ConnectorConfig.model_validate(self._client.strip_surreal_id(results[0]))

    async def list_connector_configs(self, tenant_id: str) -> list[ConnectorConfig]:
        results = await self._client.query(
            "SELECT * FROM connector_configs WHERE tenant_id = $tenant_id ORDER BY created_at DESC",
            {"tenant_id": tenant_id},
        )
        return [ConnectorConfig.model_validate(self._client.strip_surreal_id(r)) for r in results]

    async def create_run_log(self, run_log: RunLog) -> RunLog:
        await self._client.query(
            "CREATE run_logs SET run_id = $run_id, tenant_id = $tenant_id, "
            "job_type = $job_type, status = $status, started_at = $started_at, "
            "completed_at = $completed_at, error = $error, metadata = $metadata",
            {
                "run_id": run_log.run_id,
                "tenant_id": run_log.tenant_id,
                "job_type": run_log.job_type,
                "status": run_log.status,
                "started_at": run_log.started_at.isoformat(),
                "completed_at": run_log.completed_at.isoformat() if run_log.completed_at else None,
                "error": run_log.error,
                "metadata": run_log.metadata,
            },
        )
        return run_log

    async def update_run_log(self, run_log: RunLog) -> RunLog:
        await self._client.query(
            "UPDATE run_logs SET status = $status, completed_at = $completed_at, "
            "error = $error, metadata = $metadata WHERE run_id = $run_id",
            {
                "run_id": run_log.run_id,
                "status": run_log.status,
                "completed_at": run_log.completed_at.isoformat() if run_log.completed_at else None,
                "error": run_log.error,
                "metadata": run_log.metadata,
            },
        )
        return run_log

    async def get_run_log(self, run_id: str) -> RunLog | None:
        results = await self._client.query(
            "SELECT * FROM run_logs WHERE run_id = $run_id LIMIT 1",
            {"run_id": run_id},
        )
        if not results:
            return None
        return RunLog.model_validate(self._client.strip_surreal_id(results[0]))

    async def list_run_logs(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RunLog]:
        results = await self._client.query(
            "SELECT * FROM run_logs WHERE tenant_id = $tenant_id "
            "ORDER BY started_at DESC LIMIT $limit START $offset",
            {"tenant_id": tenant_id, "limit": limit, "offset": offset},
        )
        return [RunLog.model_validate(self._client.strip_surreal_id(r)) for r in results]
