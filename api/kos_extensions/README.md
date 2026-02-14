# cogmem-kos-acs Cloud

Enterprise cloud offering — a self-contained deployment using **SurrealDB** as the unified backing store for all KOS contracts.

## Architecture

```
┌─────────────────────────────────────────────┐
│              FastAPI (cloud/app.py)          │
├─────────────────────────────────────────────┤
│         CloudProviderRegistry               │
│  (binds all contracts → SurrealDB)          │
├──────────────┬──────────────────────────────┤
│  Core Stores │  Retrieval      │  ACP       │
│  ObjectStore │  TextSearch     │  Strategy  │
│  OutboxStore │  VectorSearch   │  Outcome   │
│  AdminStore  │  GraphSearch    │  Proposal  │
├──────────────┴──────────────────────────────┤
│              SurrealDB Client               │
└─────────────────────────────────────────────┘
```

## Quick Start

```bash
# Start SurrealDB
docker run -d --name kos-surrealdb \
  -p 8000:8000 \
  surrealdb/surrealdb:latest \
  start --user root --pass root memory

# Configure
cp backend/src/kos/cloud/.env.example backend/.env

# Run the cloud API
cd backend
uvicorn kos.cloud.app:app --host 0.0.0.0 --port 8001 --reload
```

## Contracts Fulfilled

| Contract | Implementation | Module |
|----------|---------------|--------|
| ObjectStore | SurrealDBObjectStore | `providers.surrealdb.object_store` |
| OutboxStore | SurrealDBOutboxStore | `providers.surrealdb.outbox_store` |
| AdminStore | SurrealDBAdminStore | `cloud.stores.admin_store` |
| TextSearchProvider | SurrealDBTextSearchProvider | `providers.surrealdb.text_search` |
| VectorSearchProvider | SurrealDBVectorSearchProvider | `providers.surrealdb.vector_search` |
| GraphSearchProvider | SurrealDBGraphSearchProvider | `providers.surrealdb.graph_search` |
| StrategyStore | SurrealDBStrategyStore | `cloud.stores.strategy_store` |
| OutcomeStore | SurrealDBOutcomeStore | `cloud.stores.outcome_store` |
| ProposalStore | SurrealDBProposalStore | `cloud.stores.proposal_store` |
