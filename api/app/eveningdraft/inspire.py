"""Inspire endpoint for Evening Draft.

Provides semantic search over the shared Gutenberg literature corpus
stored in the ed_literature SurrealDB database. Uses HNSW vector index
for fast approximate nearest-neighbor search.

All SurrealDB calls use the blocking ``surrealdb.Surreal`` library
wrapped in ``run_in_executor`` to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from openai import OpenAI

from app.eveningdraft.deps import CurrentEDUser
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inspire", tags=["eveningdraft-inspire"])

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
LIT_NAMESPACE = "eveningdraft"
LIT_DATABASE = "ed_literature"


# ── Request / Response models ─────────────────────────────────────────────

class InspireSearchRequest(BaseModel):
    query: str
    limit: int = 10
    era: str | None = None
    author: str | None = None


class PassageResult(BaseModel):
    text: str
    title: str
    author: str
    year: int
    era: str
    work_id: str
    gutenberg_id: str
    sequence: int
    distance: float


class InspireSearchResponse(BaseModel):
    results: list[PassageResult]
    total: int
    query: str


class AuthorInfo(BaseModel):
    name: str
    work_count: int
    eras: list[str]
    notable_works: list[str]


class WorkInfo(BaseModel):
    gutenberg_id: str
    title: str
    author: str
    year: int
    era: str
    word_count: int
    chunk_count: int


class CorpusStats(BaseModel):
    works: int
    passages: int
    authors: int


class ChatMessage(BaseModel):
    role: str
    content: str


class InspireChatRequest(BaseModel):
    messages: list[ChatMessage]
    limit: int = 8
    era: str | None = None
    author: str | None = None


class InspireChatResponse(BaseModel):
    reply: str
    passages: list[PassageResult]


# ── SurrealDB helpers ─────────────────────────────────────────────────────

def _extract_rows(result) -> list[dict]:
    if not result:
        return []
    if isinstance(result, list) and all(isinstance(r, dict) for r in result):
        if len(result) == 1 and "result" in result[0]:
            inner = result[0]["result"]
            if isinstance(inner, list):
                return [r for r in inner if isinstance(r, dict)]
        return result
    return []


def _get_lit_db():
    """Get a blocking SurrealDB connection to the literature database."""
    from surrealdb import Surreal
    db = Surreal(settings.SURREALDB_URL)
    db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
    db.use(LIT_NAMESPACE, LIT_DATABASE)
    return db


def _embed_query_sync(text: str) -> list[float]:
    """Embed a query string using OpenRouter (synchronous)."""
    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
    )
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0].embedding


def _search_sync(
    query: str,
    limit: int = 10,
    era: str | None = None,
    author: str | None = None,
) -> list[dict]:
    """Embed query + HNSW search (synchronous, for run_in_executor)."""
    query_vec = _embed_query_sync(query)

    db = _get_lit_db()
    try:
        filters = [f"embedding <|{limit}, COSINE|> $qvec"]
        params: dict = {"qvec": query_vec}

        if era:
            filters.append("era = $era")
            params["era"] = era
        if author:
            filters.append("author = $author")
            params["author"] = author

        where_clause = "WHERE " + " AND ".join(filters)

        sql = f"""
            SELECT text, title, author, year, era, work_id, work_id AS gutenberg_id, sequence,
                   vector::distance::knn() AS distance
            FROM ed_lit_passages
            {where_clause}
            ORDER BY distance
        """

        result = db.query(sql, params)
        return _extract_rows(result)
    finally:
        db.close()


MEDIA_BASE_URL = "https://media.cogmem.ai/media"

INSPIRE_SYSTEM_PROMPT = """You are a literary guide with deep knowledge of classic literature.
You have been given passages from classic texts that are relevant to the user's question.
Use these passages to inform your response, quoting them when appropriate.
Be thoughtful, insightful, and help the user explore themes, ideas, and connections across literature.
Always cite the work and author when referencing a passage.

Relevant passages from the literature corpus:
{context}"""


def _chat_sync(
    messages: list[dict],
    limit: int = 8,
    era: str | None = None,
    author: str | None = None,
) -> tuple[str, list[dict]]:
    """RAG chat: embed last user message, retrieve passages, call LLM (synchronous)."""
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    if not last_user:
        return "Please ask a question about literature.", []

    passages = _search_sync(last_user, limit=limit, era=era, author=author)

    context_parts = []
    for i, p in enumerate(passages, 1):
        context_parts.append(
            f"[{i}] \"{p['text']}\"\n    — {p['title']} by {p['author']} ({p['year']})"
        )
    context = "\n\n".join(context_parts)

    system_prompt = INSPIRE_SYSTEM_PROMPT.format(context=context)

    chat_messages = [{"role": "system", "content": system_prompt}]
    for m in messages:
        chat_messages.append({"role": m["role"], "content": m["content"]})

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
    )
    response = client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=chat_messages,
        max_tokens=1024,
    )
    reply = response.choices[0].message.content or ""
    return reply, passages


def _browse_authors_sync(limit: int = 50) -> list[dict]:
    db = _get_lit_db()
    try:
        result = db.query(
            "SELECT name, work_count, eras, notable_works FROM ed_lit_authors "
            "ORDER BY work_count DESC LIMIT $lim",
            {"lim": limit},
        )
        return _extract_rows(result)
    finally:
        db.close()


def _browse_works_sync(
    author: str | None = None,
    era: str | None = None,
    limit: int = 50,
) -> list[dict]:
    db = _get_lit_db()
    try:
        filters = []
        params: dict = {"lim": limit}
        if author:
            filters.append("author = $author")
            params["author"] = author
        if era:
            filters.append("era = $era")
            params["era"] = era

        where = "WHERE " + " AND ".join(filters) if filters else ""
        result = db.query(
            f"SELECT gutenberg_id, title, author, year, era, word_count, chunk_count "
            f"FROM ed_lit_works {where} ORDER BY year ASC LIMIT $lim",
            params,
        )
        return _extract_rows(result)
    finally:
        db.close()


def _corpus_stats_sync() -> dict:
    db = _get_lit_db()
    try:
        works = _extract_rows(db.query("SELECT count() AS c FROM ed_lit_works GROUP ALL"))
        passages = _extract_rows(db.query("SELECT count() AS c FROM ed_lit_passages GROUP ALL"))
        authors = _extract_rows(db.query("SELECT count() AS c FROM ed_lit_authors GROUP ALL"))
        return {
            "works": works[0].get("c", 0) if works else 0,
            "passages": passages[0].get("c", 0) if passages else 0,
            "authors": authors[0].get("c", 0) if authors else 0,
        }
    finally:
        db.close()


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/search", response_model=InspireSearchResponse)
async def inspire_search(
    body: InspireSearchRequest,
    current_user: CurrentEDUser,
) -> Any:
    """Semantic search over the literature corpus."""
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(
        None, _search_sync, body.query, body.limit, body.era, body.author,
    )

    results = []
    for row in rows:
        results.append(PassageResult(
            text=row.get("text", ""),
            title=row.get("title", ""),
            author=row.get("author", ""),
            year=row.get("year", 0),
            era=row.get("era", ""),
            work_id=row.get("work_id", ""),
            gutenberg_id=row.get("gutenberg_id", ""),
            sequence=row.get("sequence", 0),
            distance=row.get("distance", 0.0),
        ))

    return InspireSearchResponse(
        results=results,
        total=len(results),
        query=body.query,
    )


@router.get("/browse/authors")
async def browse_authors(
    current_user: CurrentEDUser,
    limit: int = Query(default=50, le=200),
) -> list[AuthorInfo]:
    """List authors in the literature corpus."""
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(None, _browse_authors_sync, limit)
    return [
        AuthorInfo(
            name=r.get("name", ""),
            work_count=r.get("work_count", 0),
            eras=r.get("eras", []),
            notable_works=r.get("notable_works", []),
        )
        for r in rows
    ]


@router.get("/browse/works")
async def browse_works(
    current_user: CurrentEDUser,
    author: str | None = Query(default=None),
    era: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> list[WorkInfo]:
    """List works in the literature corpus with optional filters."""
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(None, _browse_works_sync, author, era, limit)
    return [
        WorkInfo(
            gutenberg_id=r.get("gutenberg_id", ""),
            title=r.get("title", ""),
            author=r.get("author", ""),
            year=r.get("year", 0),
            era=r.get("era", ""),
            word_count=r.get("word_count", 0),
            chunk_count=r.get("chunk_count", 0),
        )
        for r in rows
    ]


@router.get("/stats", response_model=CorpusStats)
async def get_corpus_stats(current_user: CurrentEDUser) -> Any:
    """Get literature corpus statistics."""
    loop = asyncio.get_event_loop()
    stats = await loop.run_in_executor(None, _corpus_stats_sync)
    return CorpusStats(**stats)


@router.post("/chat", response_model=InspireChatResponse)
async def inspire_chat(
    body: InspireChatRequest,
    current_user: CurrentEDUser,
) -> Any:
    """RAG chat over the literature corpus. Retrieves relevant passages via HNSW
    and uses them as context for an LLM response."""
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")

    loop = asyncio.get_event_loop()
    reply, passage_rows = await loop.run_in_executor(
        None, _chat_sync,
        [m.model_dump() for m in body.messages],
        body.limit,
        body.era,
        body.author,
    )

    passages = [
        PassageResult(
            text=row.get("text", ""),
            title=row.get("title", ""),
            author=row.get("author", ""),
            year=row.get("year", 0),
            era=row.get("era", ""),
            work_id=row.get("work_id", ""),
            gutenberg_id=row.get("gutenberg_id", ""),
            sequence=row.get("sequence", 0),
            distance=row.get("distance", 0.0),
        )
        for row in passage_rows
    ]

    return InspireChatResponse(reply=reply, passages=passages)


@router.get("/reader/{gutenberg_id}")
async def reader_redirect(
    gutenberg_id: str,
    current_user: CurrentEDUser,
) -> RedirectResponse:
    """Redirect to the raw text file on the media server."""
    url = f"{MEDIA_BASE_URL}/{gutenberg_id}.txt"
    return RedirectResponse(url=url, status_code=302)
