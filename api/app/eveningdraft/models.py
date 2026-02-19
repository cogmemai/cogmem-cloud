"""Evening Draft user models — stored in the 'eveningdraft' Postgres schema."""

import uuid
from datetime import datetime, timezone

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Pydantic-only schemas (no table=True) ----------

class EDUserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class EDUserCreate(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class EDUserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class EDUserPublic(SQLModel):
    id: uuid.UUID
    email: EmailStr
    is_active: bool
    is_superuser: bool
    full_name: str | None = None
    tenant_id: str | None = None
    created_at: datetime | None = None


# ---------- Database table ----------

class EveningDraftUser(SQLModel, table=True):
    __tablename__ = "user"
    __table_args__ = {"schema": "eveningdraft"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    hashed_password: str
    tenant_id: str | None = Field(default=None, max_length=255, index=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
