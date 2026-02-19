"""Evening Draft API routes — signup, login, user management.

All routes are mounted under /api/v1/eveningdraft/ prefix.
Uses a separate Postgres schema ('eveningdraft') and SurrealDB namespace.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.core import security
from app.core.config import settings
from app.models import Token
from app.eveningdraft import crud
from app.eveningdraft.deps import CurrentEDUser, EDSessionDep
from app.eveningdraft.models import (
    EDUserCreate,
    EDUserPublic,
    EDUserRegister,
)
from app.eveningdraft.tenant import provision_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eveningdraft", tags=["eveningdraft"])

# Include sub-routers
from app.eveningdraft.chat import router as chat_router
from app.eveningdraft.journal import router as journal_router
from app.eveningdraft.desk import router as desk_router
from app.eveningdraft.workshop import router as workshop_router
from app.eveningdraft.inspire import router as inspire_router

router.include_router(chat_router)
router.include_router(journal_router)
router.include_router(desk_router)
router.include_router(workshop_router)
router.include_router(inspire_router)


# ── Login ────────────────────────────────────────────────────────────────

@router.post("/login/access-token")
def login_access_token(
    session: EDSessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """OAuth2 compatible token login for Evening Draft users."""
    user = crud.authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
    )


@router.post("/login/test-token", response_model=EDUserPublic)
def test_token(current_user: CurrentEDUser) -> Any:
    """Test access token."""
    return current_user


# ── Users ────────────────────────────────────────────────────────────────

@router.get("/users/me", response_model=EDUserPublic)
def read_user_me(current_user: CurrentEDUser) -> Any:
    """Get current Evening Draft user."""
    return current_user


@router.post("/users/signup", response_model=EDUserPublic)
async def register_user(session: EDSessionDep, user_in: EDUserRegister) -> Any:
    """
    Create new Evening Draft user.
    Also provisions an isolated SurrealDB tenant database under the
    'eveningdraft' namespace.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    user_create = EDUserCreate.model_validate(user_in)
    user = crud.create_user(session=session, user_create=user_create)

    # Provision SurrealDB tenant database under 'eveningdraft' namespace
    try:
        tenant_id = await provision_tenant(user.id)
        user.tenant_id = tenant_id
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info("ED tenant %s provisioned for user %s", tenant_id, user.email)
    except Exception:
        logger.exception("Failed to provision ED tenant for user %s", user.email)
        user.tenant_id = f"pending_{user.id.hex}"
        session.add(user)
        session.commit()
        session.refresh(user)

    return user


@router.post("/users/me/provision-tenant", response_model=EDUserPublic)
async def provision_tenant_for_me(
    session: EDSessionDep, current_user: CurrentEDUser
) -> Any:
    """
    (Re-)provision the SurrealDB tenant database for the current Evening Draft user.
    """
    try:
        tenant_id = await provision_tenant(current_user.id)
        current_user.tenant_id = tenant_id
        session.add(current_user)
        session.commit()
        session.refresh(current_user)
        logger.info("ED tenant %s (re-)provisioned for user %s", tenant_id, current_user.email)
    except Exception:
        logger.exception("Failed to provision ED tenant for user %s", current_user.email)
        raise HTTPException(
            status_code=503,
            detail="Failed to provision tenant database. Is SurrealDB reachable?",
        )
    return current_user


@router.post("/users/me/clear-data")
async def clear_user_data(current_user: CurrentEDUser) -> Any:
    """Clear all KOS data from the user's SurrealDB tenant database."""
    import asyncio
    from surrealdb import Surreal

    tenant_id = current_user.tenant_id
    if not tenant_id or tenant_id.startswith("pending_"):
        raise HTTPException(status_code=400, detail="No tenant database provisioned")

    def _clear_sync() -> dict:
        db = Surreal(settings.SURREALDB_URL)
        try:
            db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
            db.use("eveningdraft", tenant_id)
            tables = [
                "ed_chat_messages",
                "ed_entities",
                "ed_passages",
                "ed_items",
                "ed_journal_entries",
                "ed_desk_sources",
            ]
            cleared = []
            for table in tables:
                try:
                    db.query(f"DELETE FROM {table}")
                    cleared.append(table)
                except Exception as e:
                    logger.warning("Failed to clear %s: %s", table, e)
            return {"cleared_tables": cleared, "tenant_id": tenant_id}
        finally:
            db.close()

    result = await asyncio.get_event_loop().run_in_executor(None, _clear_sync)
    logger.info("Cleared data for tenant %s: %s", tenant_id, result["cleared_tables"])
    return {"status": "ok", **result}
