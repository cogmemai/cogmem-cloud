"""Standalone KOS data models for Evening Draft.

No dependency on cogmem-kos — these are self-contained Pydantic models
for items, passages, entities, and search results stored in SurrealDB.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid.uuid4())


# ── Enums ────────────────────────────────────────────────────────────────────

class Source(str, Enum):
    CHAT = "chat"
    NOTE = "note"
    FILE = "file"
    FILES = "files"
    PDF = "pdf"
    EMAIL = "email"
    WEB = "web"
    OTHER = "other"


class EntityType(str, Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    DATE = "date"
    TECHNOLOGY = "technology"
    CONCEPT = "concept"
    OTHER = "other"


# ── Core Models ──────────────────────────────────────────────────────────────

class TextSpan(BaseModel):
    start: int
    end: int


class Item(BaseModel):
    kos_id: str = Field(default_factory=new_id)
    tenant_id: str
    user_id: str
    source: Source = Source.CHAT
    external_id: str | None = None
    title: str = ""
    content_text: str = ""
    content_type: str = "text/plain"
    llm_prompt: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict = Field(default_factory=dict)


class Passage(BaseModel):
    kos_id: str = Field(default_factory=new_id)
    item_id: str
    tenant_id: str
    user_id: str
    text: str = ""
    span: TextSpan | None = None
    sequence: int = 0
    metadata: dict = Field(default_factory=dict)


class Entity(BaseModel):
    kos_id: str = Field(default_factory=new_id)
    tenant_id: str
    user_id: str
    name: str
    entity_type: EntityType = EntityType.OTHER
    aliases: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """A chat message stored in the tenant's SurrealDB."""
    kos_id: str = Field(default_factory=new_id)
    tenant_id: str
    user_id: str
    session_id: str = Field(default_factory=new_id)
    role: str  # "user" | "assistant" | "system"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict = Field(default_factory=dict)


# ── Search Results ───────────────────────────────────────────────────────────

class SearchHit(BaseModel):
    kos_id: str
    score: float = 0.0
    snippet: str = ""
    title: str | None = None
    source: str | None = None
    item_id: str | None = None


class SearchResults(BaseModel):
    hits: list[SearchHit] = Field(default_factory=list)
    total: int = 0
    took_ms: int = 0
