# cogmem-cloud

Agentic Knowledge Operating System — the cloud infrastructure and backend for CogMem's hosted, multi-tenant KOS platform.

## Structure

```
cogmem-cloud/
├── api/                          # FastAPI backend
│   ├── app/                      # Core: auth, JWT, users, tenant provisioning
│   │   └── eveningdraft/         # Evening Draft app suite
│   │       ├── chat.py           # Muse AI writing assistant (OpenRouter/Gemini)
│   │       ├── journal.py        # Journal CRUD + KOS ingestion
│   │       ├── desk.py           # Document context (PDF/DOCX upload)
│   │       ├── workshop.py       # Writer's Workshop (SSE multi-agent review)
│   │       ├── inspire.py        # Literary guide (Gemini tool-calling, Gutenberg index)
│   │       └── kos/              # Standalone KOS: chunking, entities, ingest, search
│   ├── kos_extensions/           # Enterprise KOS modules
│   │   ├── routes/               # ACP, KOS CRUD, workbench API routes
│   │   ├── stores/               # SurrealDB item/passage/entity stores
│   │   ├── workbench/            # AI workbench (experiments, runs)
│   │   └── registry.py           # Per-tenant SurrealDB client registry
│   ├── Dockerfile
│   └── pyproject.toml
│
├── k8s/                          # Kubernetes manifests (RKE2 bare metal)
│   ├── base/                     # Namespace, ConfigMap, secrets template, PVCs, StorageClass
│   ├── services/                 # Deployments: backend, cockpit, frontend, ollama, llama-server
│   ├── databases/                # StatefulSets: Postgres, SurrealDB, Neo4j, Qdrant, OpenSearch
│   ├── ingress/                  # Ingress rules for *.cogmem.ai
│   ├── deploy.sh                 # Full cluster deploy script
│   ├── update.sh                 # Rolling update script
│   └── generate-secrets.sh       # K8s secret generation helper
│
├── scripts/                      # Dev/deploy utility scripts
└── docker-login.sh               # GHCR authentication
```

## Dependencies

- **cogmem-kos** (MIT, open-source) — core KOS engine, installed as a pip package
- **PostgreSQL** — user accounts and authentication
- **SurrealDB** — per-tenant knowledge storage (items, passages, entities, chat)
- **Neo4j** — knowledge graph
- **Qdrant** — vector search
- **OpenSearch** — full-text search and dashboards
- **Ollama / llama-server** — local LLM inference (CPU)
- **Kubernetes (RKE2)** — orchestration on bare-metal OVH server

## Deployment

- **api** → `ghcr.io/cogmemai/cogmem-backend:latest` → `api.cogmem.ai`
- **cockpit** → `ghcr.io/cogmemai/cogmem-cockpit:latest` → `dashboard.cogmem.ai`
- **eveningdraft** → Vercel (separate repo: `eveningdraft-website`) → `eveningdraft.com`
