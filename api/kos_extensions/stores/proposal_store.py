"""SurrealDB implementation of ProposalStore for cloud offering."""

from kos.core.contracts.stores.proposal_store import ProposalStore
from kos.core.models.ids import KosId
from kos.core.models.strategy_change_proposal import (
    ProposalStatus,
    StrategyChangeProposal,
)
from kos.providers.surrealdb.client import SurrealDBClient


class SurrealDBProposalStore(ProposalStore):
    """SurrealDB-backed ProposalStore for the cloud offering."""

    TABLE = "strategy_change_proposals"

    def __init__(self, client: SurrealDBClient) -> None:
        self._client = client

    async def save_proposal(
        self, proposal: StrategyChangeProposal
    ) -> StrategyChangeProposal:
        data = proposal.model_dump(mode="json")
        kos_id = str(proposal.kos_id)

        # Upsert: delete existing then create
        await self._client.query(
            f"DELETE FROM {self.TABLE} WHERE kos_id = $kos_id",
            {"kos_id": kos_id},
        )
        await self._client.query(
            f"CREATE {self.TABLE} CONTENT $data",
            {"data": data},
        )
        return proposal

    async def get_proposal(self, kos_id: KosId) -> StrategyChangeProposal | None:
        results = await self._client.query(
            f"SELECT * FROM {self.TABLE} WHERE kos_id = $kos_id LIMIT 1",
            {"kos_id": str(kos_id)},
        )
        if not results:
            return None
        return StrategyChangeProposal.model_validate(self._client.strip_surreal_id(results[0]))

    async def list_proposals(
        self,
        status: ProposalStatus | None = None,
        base_strategy_id: KosId | None = None,
        limit: int = 50,
    ) -> list[StrategyChangeProposal]:
        conditions: list[str] = []
        params: dict = {"limit": limit}

        if status is not None:
            conditions.append("status = $status")
            params["status"] = status.value

        if base_strategy_id is not None:
            conditions.append("base_strategy_id = $base_strategy_id")
            params["base_strategy_id"] = str(base_strategy_id)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        results = await self._client.query(
            f"SELECT * FROM {self.TABLE}{where_clause} ORDER BY created_at DESC LIMIT $limit",
            params,
        )
        return [StrategyChangeProposal.model_validate(self._client.strip_surreal_id(r)) for r in results]

    async def update_status(
        self, kos_id: KosId, status: ProposalStatus
    ) -> bool:
        results = await self._client.query(
            f"UPDATE {self.TABLE} SET status = $status WHERE kos_id = $kos_id",
            {"kos_id": str(kos_id), "status": status.value},
        )
        return bool(results)
