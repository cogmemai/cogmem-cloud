"""SurrealDB schema initialization for the cloud offering.

Extends the base solo-mode schema with tables for:
- AdminStore (tenants, users, connector_configs, run_logs)
- ACP stores (memory_strategies, outcome_events, strategy_change_proposals)
"""

from kos.providers.surrealdb.client import SurrealDBClient


async def create_cloud_schema(client: SurrealDBClient) -> None:
    """Create the full cloud schema in SurrealDB.

    Calls the base solo-mode schema first, then adds cloud-specific tables.
    """
    # Base schema from the solo-mode provider (items, passages, entities, etc.)
    await client.create_schema()

    # Cloud-specific tables
    cloud_statements = [
        # Admin: tenants
        "DEFINE TABLE tenants SCHEMALESS;",
        "DEFINE INDEX idx_tenants_id ON tenants FIELDS tenant_id UNIQUE;",

        # Admin: users
        "DEFINE TABLE users SCHEMALESS;",
        "DEFINE INDEX idx_users_tenant_user ON users FIELDS tenant_id, user_id UNIQUE;",

        # Admin: connector configs
        "DEFINE TABLE connector_configs SCHEMALESS;",
        "DEFINE INDEX idx_connector_configs_id ON connector_configs FIELDS config_id UNIQUE;",
        "DEFINE INDEX idx_connector_configs_tenant ON connector_configs FIELDS tenant_id;",

        # Admin: run logs
        "DEFINE TABLE run_logs SCHEMALESS;",
        "DEFINE INDEX idx_run_logs_id ON run_logs FIELDS run_id UNIQUE;",
        "DEFINE INDEX idx_run_logs_tenant ON run_logs FIELDS tenant_id;",

        # ACP: memory strategies
        "DEFINE TABLE memory_strategies SCHEMALESS;",
        "DEFINE INDEX idx_strategies_kos_id ON memory_strategies FIELDS kos_id UNIQUE;",
        "DEFINE INDEX idx_strategies_scope ON memory_strategies FIELDS scope_type, scope_id;",
        "DEFINE INDEX idx_strategies_status ON memory_strategies FIELDS status;",

        # ACP: outcome events (append-only)
        "DEFINE TABLE outcome_events SCHEMALESS;",
        "DEFINE INDEX idx_outcomes_kos_id ON outcome_events FIELDS kos_id UNIQUE;",
        "DEFINE INDEX idx_outcomes_strategy ON outcome_events FIELDS strategy_id;",
        "DEFINE INDEX idx_outcomes_type ON outcome_events FIELDS outcome_type;",
        "DEFINE INDEX idx_outcomes_created ON outcome_events FIELDS created_at;",

        # ACP: strategy change proposals
        "DEFINE TABLE strategy_change_proposals SCHEMALESS;",
        "DEFINE INDEX idx_proposals_kos_id ON strategy_change_proposals FIELDS kos_id UNIQUE;",
        "DEFINE INDEX idx_proposals_status ON strategy_change_proposals FIELDS status;",
        "DEFINE INDEX idx_proposals_base ON strategy_change_proposals FIELDS base_strategy_id;",
    ]

    for stmt in cloud_statements:
        try:
            await client.query(stmt)
        except Exception:
            pass
