"""Cloud provider registry — wires all contracts to SurrealDB implementations.

This is the single place where every contract is bound to its SurrealDB
provider for the cloud offering. No Postgres, OpenSearch, Neo4j, or Qdrant.
"""

from __future__ import annotations

from typing import Any

from kos.providers.surrealdb.client import SurrealDBClient

from kos.core.contracts.stores.object_store import ObjectStore
from kos.core.contracts.stores.outbox_store import OutboxStore
from kos.core.contracts.stores.admin_store import AdminStore
from kos.core.contracts.stores.strategy_store import StrategyStore
from kos.core.contracts.stores.outcome_store import OutcomeStore
from kos.core.contracts.stores.proposal_store import ProposalStore
from kos.core.contracts.stores.retrieval.text_search import TextSearchProvider
from kos.core.contracts.stores.retrieval.vector_search import VectorSearchProvider
from kos.core.contracts.stores.retrieval.graph_search import GraphSearchProvider


class CloudProviderRegistry:
    """Holds all provider instances for the cloud offering.

    All providers share a single SurrealDBClient connection.
    """

    def __init__(self, client: SurrealDBClient) -> None:
        self._client = client

        # Lazy-init caches
        self._object_store: ObjectStore | None = None
        self._outbox_store: OutboxStore | None = None
        self._admin_store: AdminStore | None = None
        self._strategy_store: StrategyStore | None = None
        self._outcome_store: OutcomeStore | None = None
        self._proposal_store: ProposalStore | None = None
        self._text_search: TextSearchProvider | None = None
        self._vector_search: VectorSearchProvider | None = None
        self._graph_search: GraphSearchProvider | None = None

    @property
    def client(self) -> SurrealDBClient:
        return self._client

    # --- Store contracts ---

    @property
    def object_store(self) -> ObjectStore:
        if self._object_store is None:
            from kos.providers.surrealdb.object_store import SurrealDBObjectStore
            self._object_store = SurrealDBObjectStore(self._client)
        return self._object_store

    @property
    def outbox_store(self) -> OutboxStore:
        if self._outbox_store is None:
            from kos.providers.surrealdb.outbox_store import SurrealDBOutboxStore
            self._outbox_store = SurrealDBOutboxStore(self._client)
        return self._outbox_store

    @property
    def admin_store(self) -> AdminStore:
        if self._admin_store is None:
            from kos.cloud.stores.admin_store import SurrealDBAdminStore
            self._admin_store = SurrealDBAdminStore(self._client)
        return self._admin_store

    @property
    def strategy_store(self) -> StrategyStore:
        if self._strategy_store is None:
            from kos.cloud.stores.strategy_store import SurrealDBStrategyStore
            self._strategy_store = SurrealDBStrategyStore(self._client)
        return self._strategy_store

    @property
    def outcome_store(self) -> OutcomeStore:
        if self._outcome_store is None:
            from kos.cloud.stores.outcome_store import SurrealDBOutcomeStore
            self._outcome_store = SurrealDBOutcomeStore(self._client)
        return self._outcome_store

    @property
    def proposal_store(self) -> ProposalStore:
        if self._proposal_store is None:
            from kos.cloud.stores.proposal_store import SurrealDBProposalStore
            self._proposal_store = SurrealDBProposalStore(self._client)
        return self._proposal_store

    # --- Retrieval contracts ---

    @property
    def text_search(self) -> TextSearchProvider:
        if self._text_search is None:
            from kos.providers.surrealdb.text_search import SurrealDBTextSearchProvider
            self._text_search = SurrealDBTextSearchProvider(self._client)
        return self._text_search

    @property
    def vector_search(self) -> VectorSearchProvider:
        if self._vector_search is None:
            from kos.providers.surrealdb.vector_search import SurrealDBVectorSearchProvider
            self._vector_search = SurrealDBVectorSearchProvider(self._client)
        return self._vector_search

    @property
    def graph_search(self) -> GraphSearchProvider:
        if self._graph_search is None:
            from kos.providers.surrealdb.graph_search import SurrealDBGraphSearchProvider
            self._graph_search = SurrealDBGraphSearchProvider(self._client)
        return self._graph_search

    async def close(self) -> None:
        """Close the underlying SurrealDB connection."""
        await self._client.close()
