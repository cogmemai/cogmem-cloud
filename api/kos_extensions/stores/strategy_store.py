"""SurrealDB implementation of StrategyStore for cloud offering."""

from kos.core.contracts.stores.strategy_store import StrategyStore
from kos.core.models.ids import KosId
from kos.core.models.strategy import MemoryStrategy, StrategyScopeType, StrategyStatus
from kos.providers.surrealdb.client import SurrealDBClient


class SurrealDBStrategyStore(StrategyStore):
    """SurrealDB-backed StrategyStore for the cloud offering."""

    TABLE = "memory_strategies"

    def __init__(self, client: SurrealDBClient) -> None:
        self._client = client

    async def save_strategy(self, strategy: MemoryStrategy) -> MemoryStrategy:
        data = strategy.model_dump(mode="json")
        kos_id = str(strategy.kos_id)

        # Upsert: delete existing then create
        await self._client.query(
            f"DELETE FROM {self.TABLE} WHERE kos_id = $kos_id",
            {"kos_id": kos_id},
        )
        await self._client.query(
            f"CREATE {self.TABLE} CONTENT $data",
            {"data": data},
        )
        return strategy

    async def get_strategy(self, kos_id: KosId) -> MemoryStrategy | None:
        results = await self._client.query(
            f"SELECT * FROM {self.TABLE} WHERE kos_id = $kos_id LIMIT 1",
            {"kos_id": str(kos_id)},
        )
        if not results:
            return None
        return MemoryStrategy.model_validate(self._client.strip_surreal_id(results[0]))

    async def get_active_strategy(
        self,
        scope_type: StrategyScopeType,
        scope_id: str,
    ) -> MemoryStrategy | None:
        results = await self._client.query(
            f"SELECT * FROM {self.TABLE} WHERE scope_type = $scope_type "
            f"AND scope_id = $scope_id AND status = $status "
            f"ORDER BY version DESC LIMIT 1",
            {
                "scope_type": scope_type.value,
                "scope_id": scope_id,
                "status": StrategyStatus.ACTIVE.value,
            },
        )
        if not results:
            return None
        return MemoryStrategy.model_validate(self._client.strip_surreal_id(results[0]))

    async def list_strategies(
        self,
        scope_type: StrategyScopeType | None = None,
        scope_id: str | None = None,
        include_deprecated: bool = False,
    ) -> list[MemoryStrategy]:
        conditions = []
        params: dict = {}

        if scope_type is not None:
            conditions.append("scope_type = $scope_type")
            params["scope_type"] = scope_type.value

        if scope_id is not None:
            conditions.append("scope_id = $scope_id")
            params["scope_id"] = scope_id

        if not include_deprecated:
            conditions.append("status != $deprecated_status")
            params["deprecated_status"] = StrategyStatus.DEPRECATED.value

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        results = await self._client.query(
            f"SELECT * FROM {self.TABLE}{where_clause} ORDER BY version DESC",
            params,
        )
        return [MemoryStrategy.model_validate(self._client.strip_surreal_id(r)) for r in results]

    async def deprecate_strategy(self, kos_id: KosId) -> bool:
        results = await self._client.query(
            f"UPDATE {self.TABLE} SET status = $status WHERE kos_id = $kos_id",
            {"kos_id": str(kos_id), "status": StrategyStatus.DEPRECATED.value},
        )
        return bool(results)
