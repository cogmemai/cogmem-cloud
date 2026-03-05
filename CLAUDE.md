# CLAUDE.md — CogMem Cloud

This file documents the codebase structure, development conventions, and workflows for AI assistants working on this repository.

---

## Repository Overview

**cogmem-cloud** is the cloud backend for CogMem's hosted, multi-tenant Knowledge Operating System (KOS) platform. It is a Python monorepo managed with **uv workspaces**, consisting of:

- `api/` — FastAPI backend (the primary workspace member)
- `k8s/` — Kubernetes manifests for bare-metal RKE2 deployment

The backend serves two distinct product surfaces:
1. **CogMem Cloud** — multi-tenant KOS platform with per-tenant SurrealDB isolation
2. **Evening Draft** — a suite of AI writing-assistant features (Muse chat, journal, desk, workshop, inspire)

---

## Repository Structure

```
cogmem-cloud/
├── api/                          # FastAPI backend (uv workspace member)
│   ├── app/                      # Core application
│   │   ├── main.py               # FastAPI app factory (CORS, Sentry, router mount)
│   │   ├── models.py             # Shared SQLModel/Pydantic models (User, Item, Token)
│   │   ├── crud.py               # Core CRUD helpers (users, items)
│   │   ├── utils.py              # Email, token utilities
│   │   ├── backend_pre_start.py  # DB readiness check (run before server)
│   │   ├── initial_data.py       # Seed first superuser
│   │   ├── alembic/              # Postgres migration scripts
│   │   ├── api/
│   │   │   ├── main.py           # APIRouter wiring (all routers assembled here)
│   │   │   ├── deps.py           # FastAPI deps: CurrentUser, SessionDep
│   │   │   └── routes/           # login, users, items, chat, utils, private
│   │   ├── core/
│   │   │   ├── config.py         # Settings (pydantic-settings, reads ../.env)
│   │   │   ├── db.py             # SQLModel engine + init_db
│   │   │   └── security.py       # JWT encode/decode, password hashing (argon2/bcrypt)
│   │   └── eveningdraft/         # Evening Draft app suite
│   │       ├── routes.py         # ED router (signup, login, user management)
│   │       ├── deps.py           # ED-specific auth deps (CurrentEDUser, EDSessionDep)
│   │       ├── models.py         # EveningDraftUser, EDUserCreate, etc.
│   │       ├── crud.py           # ED user CRUD
│   │       ├── tenant.py         # SurrealDB tenant provisioning (eveningdraft namespace)
│   │       ├── chat.py           # Muse AI writing assistant (OpenRouter SSE streaming)
│   │       ├── journal.py        # Journal CRUD + KOS ingestion
│   │       ├── desk.py           # Document context (PDF/DOCX upload → SurrealDB)
│   │       ├── workshop.py       # Writer's Workshop (SSE multi-agent review panel)
│   │       ├── inspire.py        # Literary guide (Gemini tool-calling + Gutenberg index)
│   │       └── kos/              # Standalone ED KOS (chunking, entities, ingest, search)
│   │           ├── chunking.py
│   │           ├── entities.py
│   │           ├── ingest.py
│   │           ├── muse.py       # Builds Muse system prompt with KOS context
│   │           ├── models.py
│   │           └── search.py
│   ├── kos/                      # KOS engine (MIT, inlined from cogmem-kos)
│   │   ├── core/
│   │   │   ├── contracts/        # Abstract base classes (ObjectStore, TextSearch, etc.)
│   │   │   │   ├── llm.py
│   │   │   │   ├── embeddings.py
│   │   │   │   └── stores/       # object_store, outbox_store, admin_store, strategy_store, etc.
│   │   │   └── models/           # Domain models: Item, Passage, Entity, Artifact, etc.
│   │   ├── agents/               # Chunking, extraction, enrichment, indexing, ingestion agents
│   │   ├── providers/            # Concrete implementations: SurrealDB, Neo4j, Qdrant, OpenSearch, Postgres, SQLite
│   │   └── kernel/               # HTTP API, config, registry, runtime
│   ├── kos_extensions/           # Enterprise cloud layer (proprietary, built on kos/)
│   │   ├── registry.py           # CloudProviderRegistry: binds all contracts to SurrealDB
│   │   ├── tenant_deps.py        # Per-request tenant-scoped SurrealDB dependency injection
│   │   ├── config.py
│   │   ├── auth.py
│   │   ├── schema.py
│   │   ├── ingest.py
│   │   ├── document_parser.py    # PDF/DOCX parsing (pymupdf, python-docx)
│   │   ├── kos_logging.py
│   │   ├── routes/
│   │   │   ├── kos.py            # KOS CRUD + search routes (tenant-scoped)
│   │   │   ├── acp.py            # ACP routes (strategies, proposals, outcomes)
│   │   │   └── workbench.py      # AI workbench (experiments, runs)
│   │   ├── stores/               # SurrealDB store implementations
│   │   └── workbench/            # Experiment runner, data analyzer, search scorer
│   ├── tests/                    # Pytest test suite
│   │   ├── conftest.py           # Session-scoped DB fixture, TestClient, superuser token
│   │   ├── api/                  # HTTP endpoint tests
│   │   ├── crud/                 # CRUD unit tests
│   │   ├── scripts/
│   │   └── utils/                # Test helpers (create user, get headers)
│   ├── scripts/
│   │   ├── prestart.sh           # DB readiness + migrations + seed data
│   │   ├── test.sh               # Run coverage + pytest
│   │   ├── lint.sh               # mypy + ruff check + ruff format --check
│   │   └── format.sh             # ruff check --fix + ruff format
│   ├── Dockerfile                # Multi-stage uv build (python:3.12)
│   ├── alembic.ini
│   └── pyproject.toml            # api/ package metadata + tool config
├── k8s/
│   ├── base/                     # Namespace, ConfigMap, secrets template, PVCs, StorageClass
│   ├── services/                 # Deployments: backend, cockpit, frontend, ollama, llama-server
│   ├── databases/                # StatefulSets: Postgres, SurrealDB, Neo4j, Qdrant, OpenSearch
│   ├── ingress/                  # Ingress + cert-manager (Let's Encrypt)
│   ├── deploy.sh                 # Full cluster deploy script
│   ├── update.sh                 # Rolling update (backend only)
│   ├── destroy.sh                # Tear-down script
│   └── generate-secrets.sh       # K8s secret generation helper
├── scripts/
│   ├── deploy.sh                 # Top-level deploy helper
│   ├── test.sh                   # Run tests (docker-compose based)
│   └── test-local.sh             # Local test runner
├── pyproject.toml                # uv workspace root (members: ["api"])
├── uv.lock                       # Locked dependencies
├── docker-login.sh               # GHCR authentication
├── README.md
├── deployment.md
├── SERVER_SETUP.md
└── OPEN_KUBECTL_PORT.md
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ (3.12 in Docker) |
| Web framework | FastAPI + Uvicorn |
| Auth | JWT (PyJWT), argon2/bcrypt via pwdlib |
| Primary DB | PostgreSQL via SQLModel + psycopg3 + Alembic |
| KOS store | SurrealDB (per-tenant databases) |
| LLM inference | OpenRouter (OpenAI-compatible), Gemini 2.5 Flash Lite default |
| Local LLM | Ollama / llama-server (K8s pods) |
| Dependency management | uv (workspace) |
| Linting | ruff |
| Type checking | mypy (strict) |
| Testing | pytest + pytest-asyncio + httpx |
| Coverage | coverage.py |
| Containerization | Docker (python:3.12 + uv) |
| Orchestration | Kubernetes RKE2 (bare-metal OVH) |
| CI/CD | Manual (docker push to GHCR, kubectl apply) |
| Monitoring | Sentry SDK |
| Frontend | Separate repo (Vercel) |

---

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- PostgreSQL running locally
- SurrealDB running locally (for KOS/tenant features)

### Install Dependencies

```bash
# From repo root — installs all workspace members
uv sync

# Or just the api package
cd api
uv sync
```

### Environment Variables

The app reads from a `.env` file at the **repo root** (one level above `api/`). Configuration is defined in `api/app/core/config.py`.

Required variables:

```ini
PROJECT_NAME=CogMem
SECRET_KEY=<random-urlsafe-string>
POSTGRES_SERVER=localhost
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<password>
POSTGRES_DB=cogmem
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=<password>

# SurrealDB (for KOS/tenant features)
SURREALDB_URL=ws://localhost:8080
SURREALDB_NAMESPACE=cogmem
SURREALDB_USER=admin
SURREALDB_PASSWORD=<password>

# LLM (for Evening Draft chat features)
OPENROUTER_API_KEY=<key>

# Optional
ENVIRONMENT=local          # local | staging | production
SENTRY_DSN=
CLOUD_COCKPIT_URL=https://cloud.cogmem.ai
FRONTEND_HOST=http://localhost:5173
```

### Database Initialization

```bash
cd api
# Wait for DB + run Alembic migrations + seed superuser
bash scripts/prestart.sh
```

### Running the Server

```bash
cd api
uv run fastapi dev app/main.py
# or
uv run uvicorn app.main:app --reload
```

API is available at `http://localhost:8000`. OpenAPI docs at `http://localhost:8000/api/v1/openapi.json`.

---

## Development Workflows

### Linting and Type Checking

```bash
cd api
bash scripts/lint.sh        # mypy + ruff check + ruff format --check
bash scripts/format.sh      # ruff check --fix + ruff format (auto-fix)
```

Lint rules configured in `api/pyproject.toml`:
- **ruff** — pycodestyle (E/W), pyflakes (F), isort (I), flake8-bugbear (B), comprehensions (C4), pyupgrade (UP), unused args (ARG001), print statements (T201)
- **mypy** — strict mode; exclude `venv`, `.venv`, `alembic`

Key rules: no `print()` statements (use `logging`), no unused function arguments, enforce modern Python type syntax.

### Running Tests

```bash
cd api
bash scripts/test.sh        # coverage run -m pytest tests/ + coverage report + HTML report
# or just
uv run pytest tests/
```

Tests require a live PostgreSQL connection. The `conftest.py` session fixture initializes the DB and cleans up `User`/`Item` rows after the session.

### Database Migrations

```bash
cd api
# Create a new migration
uv run alembic revision --autogenerate -m "description"
# Apply migrations
uv run alembic upgrade head
# Rollback
uv run alembic downgrade -1
```

Migrations live in `api/app/alembic/versions/`. The Alembic config (`alembic.ini`) points `script_location = app/alembic`.

---

## Architecture Patterns

### Multi-Tenancy

Every authenticated CogMem user gets an isolated SurrealDB database named `tenant_{user_id_hex}` within the `cogmem` namespace. The `get_tenant_registry` dependency in `kos_extensions/tenant_deps.py` creates a fresh `SurrealDBClient` connection per request, scoped to that user's database, and closes it in a `finally` block.

Evening Draft users get a separate database named `ed_tenant_{user_id_hex}` within the `eveningdraft` SurrealDB namespace — fully isolated from CogMem tenant data.

### Two Auth Systems

1. **CogMem users** — `app/api/deps.py` → `CurrentUser` → uses `OAuth2PasswordBearer` at `/api/v1/login/access-token`
2. **Evening Draft users** — `app/eveningdraft/deps.py` → `CurrentEDUser` → uses `OAuth2PasswordBearer` at `/api/v1/eveningdraft/login/access-token`

Both use the same JWT/secret-key infrastructure but query different SQLModel tables (`User` vs `EveningDraftUser`).

### KOS Contract/Provider Pattern

`kos/core/contracts/` defines abstract base classes for all data access (e.g., `ObjectStore`, `TextSearchProvider`, `VectorSearchProvider`). Concrete implementations live in `kos/providers/` (SurrealDB, Neo4j, Qdrant, etc.).

For the cloud offering, `kos_extensions/registry.py` wires **all** contracts to SurrealDB implementations via `CloudProviderRegistry`. No Neo4j, Qdrant, or OpenSearch is used in the cloud path — only SurrealDB.

### Async / Blocking SurrealDB

The `surrealdb` Python library has two clients:
- `surrealdb.Surreal` — synchronous/blocking (used in Evening Draft tenant provisioning)
- `kos/providers/surrealdb/client.py` `SurrealDBClient` — async (used in `kos_extensions`)

When using the **blocking** client inside an async FastAPI route, always wrap calls in `asyncio.get_event_loop().run_in_executor(None, ...)` or `asyncio.to_thread(...)` to avoid blocking the event loop.

### LLM Integration

All LLM calls go through **OpenRouter** using the `openai` SDK pointed at `https://openrouter.ai/api/v1`. Default model: `google/gemini-2.5-flash-lite`.

SSE streaming responses use FastAPI's `StreamingResponse` with an async generator that yields `data: ...\n\n` chunks.

The `inspire.py` endpoint uses **tool-calling** (Gemini via OpenRouter): the LLM is given tools to search the Gutenberg catalog in SurrealDB, with a `MAX_TOOL_ROUNDS = 5` safety limit.

---

## API Structure

All routes are prefixed `/api/v1/` and defined in `api/app/api/main.py`:

| Prefix | Module | Description |
|---|---|---|
| `/login` | `app/api/routes/login.py` | OAuth2 token issuance |
| `/users` | `app/api/routes/users.py` | User CRUD (superuser-only management) |
| `/utils` | `app/api/routes/utils.py` | Email test, health check |
| `/items` | `app/api/routes/items.py` | Item CRUD (example resource) |
| `/chat` | `app/api/routes/chat.py` | Basic LLM chat |
| `/eveningdraft` | `app/eveningdraft/routes.py` | ED signup, login, user management |
| `/eveningdraft/chat` | `app/eveningdraft/chat.py` | Muse AI writing assistant (SSE) |
| `/eveningdraft/journal` | `app/eveningdraft/journal.py` | Journal CRUD + KOS ingest |
| `/eveningdraft/desk` | `app/eveningdraft/desk.py` | Document upload (PDF/DOCX) |
| `/eveningdraft/workshop` | `app/eveningdraft/workshop.py` | Multi-agent review (SSE) |
| `/eveningdraft/inspire` | `app/eveningdraft/inspire.py` | Literary guide (tool-calling) |
| `/kos` | `kos_extensions/routes/kos.py` | KOS search/items/entities (tenant-scoped) |
| `/acp` | `kos_extensions/routes/acp.py` | ACP strategies, proposals, outcomes |
| `/workbench` | `kos_extensions/routes/workbench.py` | AI workbench experiments |
| `/private` | `app/api/routes/private.py` | Local-only dev routes |

---

## Key Files Reference

| File | Purpose |
|---|---|
| `api/app/core/config.py` | All configuration via `Settings` (pydantic-settings) — add new env vars here |
| `api/app/api/main.py` | Router assembly — add new routers here |
| `api/app/main.py` | FastAPI app factory — CORS, Sentry, middleware |
| `api/kos_extensions/registry.py` | CloudProviderRegistry — binds contracts to SurrealDB |
| `api/kos_extensions/tenant_deps.py` | `get_tenant_registry` — per-request tenant isolation |
| `api/app/eveningdraft/deps.py` | `CurrentEDUser` dependency |
| `api/app/eveningdraft/tenant.py` | ED SurrealDB schema + tenant provisioning |
| `api/Dockerfile` | Container build (uv, python:3.12, 4 uvicorn workers) |
| `k8s/deploy.sh` | Full K8s cluster deployment |
| `k8s/update.sh` | Rolling update (backend image only) |

---

## Deployment

### Docker Image

```bash
# Build from repo root (Dockerfile at api/Dockerfile)
docker build -f api/Dockerfile -t ghcr.io/cogmemai/cogmem-backend:latest .
docker push ghcr.io/cogmemai/cogmem-backend:latest
```

The Dockerfile:
1. Copies `uv` from the official uv image
2. Installs workspace dependencies (layer-cached)
3. Copies `api/app`, `api/kos`, `api/kos_extensions`
4. Runs `fastapi run --workers 4 app/main.py`

### Kubernetes (RKE2)

```bash
# Full deploy (all resources)
./k8s/deploy.sh

# Rolling update (backend only)
./k8s/update.sh

# Tear down everything
./k8s/destroy.sh
```

**Secrets:** Copy `k8s/base/secrets.yaml.template` to `k8s/base/secrets.yaml`, fill base64-encoded values. Never commit `secrets.yaml`.

**Namespace:** All resources deploy into the `cogmem` namespace.

**Ingress:** Nginx Ingress + cert-manager (Let's Encrypt). Routes:
- `api.cogmem.ai` → backend service
- `dashboard.cogmem.ai` → cockpit service

---

## Coding Conventions

### Python Style

- Python 3.11+ syntax; `from __future__ import annotations` at top of files where needed
- Type annotations everywhere; mypy strict mode must pass
- No `print()` — use `logging.getLogger(__name__)` and `logger.info/debug/warning/error`
- No unused function arguments (ruff ARG001 enforced)
- Pydantic v2 models for request/response schemas; SQLModel for DB models
- `async def` for FastAPI route handlers; wrap blocking calls in `run_in_executor`

### Route Handlers

- Use `APIRouter` with `prefix` and `tags` for each module
- Always use FastAPI `Depends()` for auth and DB dependencies — never access `settings` or DB directly in route bodies without a dependency
- Use `HTTPException` for API errors with appropriate status codes
- Document non-obvious logic with module-level docstrings

### Adding a New Feature

1. Create route file in `app/eveningdraft/` or `kos_extensions/routes/`
2. Add router import + `api_router.include_router(...)` in `app/api/main.py`
3. Add any new env vars to `Settings` in `app/core/config.py`
4. If adding new Postgres tables: create SQLModel, add `alembic revision --autogenerate`
5. If adding new SurrealDB tables: add `DEFINE TABLE` statements to the appropriate tenant schema function

### Testing

- Tests live in `api/tests/`; mirrors the `app/` structure
- Use `TestClient` from `httpx` + `fastapi.testclient`
- Fixtures in `conftest.py`: `db`, `client`, `superuser_token_headers`, `normal_user_token_headers`
- Test files should be named `test_<module>.py`

---

## Common Gotchas

1. **SurrealDB blocking client** — `surrealdb.Surreal` is sync. Always use `run_in_executor` when calling it from async routes (see `chat.py`, `journal.py` for examples).

2. **`.env` location** — `pydantic-settings` reads from `../.env` relative to the `api/` directory (i.e., the repo root). Make sure `.env` is at `/home/user/cogmem-cloud/.env`, not inside `api/`.

3. **Tenant ID format** — CogMem: `tenant_{user_id.hex}`. Evening Draft: `ed_tenant_{user_id.hex}`. Never use raw UUIDs as SurrealDB database names (hyphens are not valid).

4. **Two user systems** — `app/models.py::User` (CogMem) and `app/eveningdraft/models.py::EveningDraftUser` (Evening Draft) are separate SQLModel tables with separate auth flows. Do not mix them.

5. **Alembic working directory** — Run `alembic` commands from inside `api/` where `alembic.ini` lives.

6. **ruff T201** — `print()` is banned. Use the logger. Ruff will fail CI on any `print` statement.

7. **Model name for OpenRouter** — Use `google/gemini-2.5-flash-lite` (not `-preview` or other variants) for the default Gemini model.
