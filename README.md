# cogmem-cloud

Private repository for the CogMem Cloud offering — the paid, hosted version of the Knowledge Operating System.

## Structure

```
cogmem-cloud/
├── api/                    # Unified backend (auth + KOS enterprise API)
│   ├── app/                # Auth server (users, login, JWT, tenant provisioning)
│   ├── kos_extensions/     # ACS-only modules (cloud app, workbench, ACP routes)
│   ├── Dockerfile
│   └── pyproject.toml
│
├── cockpit/                # Cloud dashboard frontend (Next.js)
│   ├── src/
│   ├── Dockerfile
│   └── package.json
│
├── k8s/                    # Kubernetes manifests for bare metal cluster
│   ├── base/              # ConfigMaps, secrets, namespaces
│   ├── services/          # Deployments + Services (backend, cockpit, databases)
│   ├── ingress/           # Ingress rules for *.cogmem.ai
│   └── databases/         # StatefulSets for Postgres, SurrealDB, Neo4j, etc.
│
├── scripts/                # Deploy and test scripts
└── docker-login.sh         # GHCR authentication
```

## Dependencies

- **cogmem-kos** (MIT, open-source) — the core KOS engine, installed as a pip package
- **PostgreSQL** — user accounts and auth
- **SurrealDB** — per-tenant knowledge storage
- **Kubernetes** — orchestration on bare metal

## Deployment

- **api** → `ghcr.io/cogmemai/cogmem-backend:latest` → `api.cogmem.ai`
- **cockpit** → `ghcr.io/cogmemai/cogmem-cockpit:latest` → `dashboard.cogmem.ai`
- **website** → Vercel (separate repo: `cogmem-website`) → `cogmem.ai`
