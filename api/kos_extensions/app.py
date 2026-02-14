"""Cloud offering FastAPI application.

Self-contained entry point that uses SurrealDB for all contracts.
Run with: uvicorn kos.cloud.app:app --host 0.0.0.0 --port 8000 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from kos.cloud.config import get_cloud_settings
from kos.cloud.registry import CloudProviderRegistry
from kos.cloud.schema import create_cloud_schema
from kos.providers.surrealdb.client import SurrealDBClient


_registry: CloudProviderRegistry | None = None


def _get_registry() -> CloudProviderRegistry:
    """Get the global cloud provider registry."""
    if _registry is None:
        raise RuntimeError("Cloud registry not initialized. App lifespan not started.")
    return _registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect SurrealDB, init schema, teardown."""
    global _registry

    settings = get_cloud_settings()
    client = SurrealDBClient(
        url=settings.surrealdb_url,
        namespace=settings.surrealdb_namespace,
        database=settings.surrealdb_database,
        user=settings.surrealdb_user,
        password=settings.surrealdb_password,
    )
    await client.connect()
    await create_cloud_schema(client)

    _registry = CloudProviderRegistry(client)
    yield
    await _registry.close()
    _registry = None


def create_cloud_app() -> FastAPI:
    """Create the cloud FastAPI application."""
    settings = get_cloud_settings()

    cloud_app = FastAPI(
        title="cogmem-kos-acs Cloud",
        description="CogMem Knowledge Operating System — Enterprise Cloud (SurrealDB)",
        version="0.1.0",
        lifespan=lifespan,
    )

    cloud_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Include the existing KOS HTTP routes ---
    from kos.kernel.api.http.routes import search, entities, items

    cloud_app.include_router(search.router)
    cloud_app.include_router(entities.router)
    cloud_app.include_router(items.router)

    # --- Cloud-specific ACP routes ---
    from kos.cloud.routes.acp import router as acp_router
    from kos.cloud.routes.workbench import router as workbench_router

    cloud_app.include_router(acp_router)
    cloud_app.include_router(workbench_router)

    # --- Cloud-specific dependency overrides ---
    # Override the kernel's DI functions so the existing routes use our registry
    from kos.kernel.api.http import dependencies as kernel_deps

    async def _cloud_object_store():
        return _get_registry().object_store

    async def _cloud_outbox_store():
        return _get_registry().outbox_store

    async def _cloud_text_search():
        return _get_registry().text_search

    async def _cloud_graph_search():
        return _get_registry().graph_search

    async def _cloud_vector_search():
        return _get_registry().vector_search

    async def _cloud_search_plan():
        from kos.core.planning.search_first import SearchFirstPlan
        reg = _get_registry()
        return SearchFirstPlan(
            text_search=reg.text_search,
            object_store=reg.object_store,
            graph_search=reg.graph_search,
        )

    async def _cloud_wikipedia_plan():
        from kos.core.planning.wikipedia_page import WikipediaPagePlan
        reg = _get_registry()
        return WikipediaPagePlan(
            graph_search=reg.graph_search,
            text_search=reg.text_search,
        )

    # Patch the kernel dependency module so existing routes resolve to cloud providers
    kernel_deps.get_object_store = _cloud_object_store
    kernel_deps.get_outbox_store = _cloud_outbox_store
    kernel_deps.get_text_search = _cloud_text_search
    kernel_deps.get_graph_search = _cloud_graph_search
    kernel_deps.get_vector_search = _cloud_vector_search
    kernel_deps.get_search_plan = _cloud_search_plan
    kernel_deps.get_wikipedia_plan = _cloud_wikipedia_plan

    # --- Cloud-only endpoints ---

    @cloud_app.get("/admin/health", tags=["admin"])
    async def health_check():
        """Check SurrealDB connectivity."""
        reg = _get_registry()
        healthy = await reg.client.health_check()
        return {
            "status": "healthy" if healthy else "unhealthy",
            "mode": "cloud",
            "providers": {
                "surrealdb": "healthy" if healthy else "unhealthy",
            },
            "contracts": {
                "object_store": "surrealdb",
                "outbox_store": "surrealdb",
                "admin_store": "surrealdb",
                "text_search": "surrealdb",
                "vector_search": "surrealdb",
                "graph_search": "surrealdb",
                "strategy_store": "surrealdb",
                "outcome_store": "surrealdb",
                "proposal_store": "surrealdb",
            },
        }

    @cloud_app.get("/", tags=["root"])
    async def root():
        return {
            "name": "cogmem-kos-acs",
            "version": "0.1.0",
            "mode": "cloud",
            "description": "Enterprise Cloud — SurrealDB unified backend",
        }

    return cloud_app


app = create_cloud_app()
