"""Cloud SurrealDB store implementations for contracts not covered by providers/surrealdb."""

from kos_extensions.stores.admin_store import SurrealDBAdminStore
from kos_extensions.stores.strategy_store import SurrealDBStrategyStore
from kos_extensions.stores.outcome_store import SurrealDBOutcomeStore
from kos_extensions.stores.proposal_store import SurrealDBProposalStore

__all__ = [
    "SurrealDBAdminStore",
    "SurrealDBStrategyStore",
    "SurrealDBOutcomeStore",
    "SurrealDBProposalStore",
]
