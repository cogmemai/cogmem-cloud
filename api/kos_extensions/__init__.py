"""CogMem KOS Cloud — Enterprise cloud offering.

This package provides the self-contained cloud deployment of cogmem-kos-acs,
using SurrealDB as the unified backing store for all contracts:

- ObjectStore (Items, Passages, Entities, Artifacts, AgentActions)
- OutboxStore (event queue)
- AdminStore (tenants, users, connectors, run logs)
- TextSearchProvider (full-text search with highlights + facets)
- VectorSearchProvider (semantic/embedding search)
- GraphSearchProvider (entity graph traversal + entity pages)
- StrategyStore (ACP memory strategies)
- OutcomeStore (ACP outcome events — append-only)
- ProposalStore (ACP strategy change proposals)
- EmbedderBase (embedding generation via LiteLLM)
- LLMGateway (LLM generation via LiteLLM)
"""
