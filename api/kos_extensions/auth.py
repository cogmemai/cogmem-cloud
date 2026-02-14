"""JWT authentication for the cloud API.

Validates tokens issued by the cogmem-server backend (Postgres/JWT auth).
Both services share the same SECRET_KEY so tokens are interoperable.

Usage in routes:
    from kos.cloud.auth import get_current_tenant

    @router.get("/my-endpoint")
    async def my_endpoint(tenant: TenantInfo = Depends(get_current_tenant)):
        # tenant.user_id, tenant.tenant_id available
        ...
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

ALGORITHM = "HS256"

# Shared secret with cogmem-server — must match SECRET_KEY in cogmem-server .env
SECRET_KEY = os.environ.get("SECRET_KEY", "changethis")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


@dataclass
class TenantInfo:
    """Resolved tenant context from a JWT token."""
    user_id: str
    tenant_id: str  # SurrealDB database name: tenant_{user_id_hex}


def get_current_tenant(token: str | None = Depends(oauth2_scheme)) -> TenantInfo:
    """Extract and validate tenant info from the JWT bearer token.

    The token's ``sub`` claim contains the user UUID (as issued by cogmem-server).
    The tenant_id is derived as ``tenant_{user_id_hex}`` matching the provisioning logic.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    # Derive tenant_id from user UUID (matches cogmem-server/app/core/tenant.py)
    clean_id = user_id.replace("-", "")
    tenant_id = f"tenant_{clean_id}"

    return TenantInfo(user_id=user_id, tenant_id=tenant_id)


def get_optional_tenant(token: str | None = Depends(oauth2_scheme)) -> TenantInfo | None:
    """Like get_current_tenant but returns None for unauthenticated requests."""
    if token is None:
        return None
    return get_current_tenant(token)
