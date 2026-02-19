from fastapi import APIRouter

from app.api.routes import chat, items, login, private, users, utils
from app.core.config import settings

# KOS/ACS tenant-scoped routes
from kos_extensions.routes.kos import router as kos_router
from kos_extensions.routes.acp import router as acp_router
from kos_extensions.routes.workbench import router as workbench_router

# Evening Draft routes (separate Postgres schema + SurrealDB namespace)
from app.eveningdraft.routes import router as eveningdraft_router

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(chat.router)
api_router.include_router(eveningdraft_router)

# KOS kernel routes (search, items, entities) — tenant-scoped
api_router.include_router(kos_router)
# ACP routes (strategies, proposals, outcomes) — tenant-scoped
api_router.include_router(acp_router)
# Workbench routes (experiments) — tenant-scoped
api_router.include_router(workbench_router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
