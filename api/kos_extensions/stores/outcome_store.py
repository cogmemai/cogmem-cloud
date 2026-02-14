"""SurrealDB implementation of OutcomeStore for cloud offering.

OutcomeEvents are append-only — they are never updated or deleted.
"""

from datetime import datetime

from kos.core.contracts.stores.outcome_store import OutcomeStore
from kos.core.models.ids import KosId
from kos.core.models.outcome_event import OutcomeEvent, OutcomeType
from kos.providers.surrealdb.client import SurrealDBClient


class SurrealDBOutcomeStore(OutcomeStore):
    """SurrealDB-backed OutcomeStore for the cloud offering.

    Enforces append-only semantics: save_outcome only creates,
    never updates. No delete method is exposed.
    """

    TABLE = "outcome_events"

    def __init__(self, client: SurrealDBClient) -> None:
        self._client = client

    async def save_outcome(self, outcome: OutcomeEvent) -> OutcomeEvent:
        data = outcome.model_dump(mode="json")
        await self._client.query(
            f"CREATE {self.TABLE} CONTENT $data",
            {"data": data},
        )
        return outcome

    async def get_outcome(self, kos_id: KosId) -> OutcomeEvent | None:
        results = await self._client.query(
            f"SELECT * FROM {self.TABLE} WHERE kos_id = $kos_id LIMIT 1",
            {"kos_id": str(kos_id)},
        )
        if not results:
            return None
        return OutcomeEvent.model_validate(self._client.strip_surreal_id(results[0]))

    async def query_outcomes(
        self,
        strategy_id: KosId | None = None,
        outcome_type: OutcomeType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[OutcomeEvent]:
        conditions: list[str] = []
        params: dict = {"limit": limit}

        if strategy_id is not None:
            conditions.append("strategy_id = $strategy_id")
            params["strategy_id"] = str(strategy_id)

        if outcome_type is not None:
            conditions.append("outcome_type = $outcome_type")
            params["outcome_type"] = outcome_type.value

        if since is not None:
            conditions.append("created_at >= $since")
            params["since"] = since.isoformat()

        if until is not None:
            conditions.append("created_at <= $until")
            params["until"] = until.isoformat()

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        results = await self._client.query(
            f"SELECT * FROM {self.TABLE}{where_clause} ORDER BY created_at DESC LIMIT $limit",
            params,
        )
        return [OutcomeEvent.model_validate(self._client.strip_surreal_id(r)) for r in results]

    async def count_outcomes(
        self,
        strategy_id: KosId,
        outcome_type: OutcomeType | None = None,
        since: datetime | None = None,
    ) -> int:
        conditions = ["strategy_id = $strategy_id"]
        params: dict = {"strategy_id": str(strategy_id)}

        if outcome_type is not None:
            conditions.append("outcome_type = $outcome_type")
            params["outcome_type"] = outcome_type.value

        if since is not None:
            conditions.append("created_at >= $since")
            params["since"] = since.isoformat()

        where_clause = f" WHERE {' AND '.join(conditions)}"
        results = await self._client.query(
            f"SELECT count() AS total FROM {self.TABLE}{where_clause} GROUP ALL",
            params,
        )
        if results and isinstance(results[0], dict):
            return results[0].get("total", 0)
        return 0
