"""Inspire endpoint for Evening Draft.

LLM-driven literary guide that uses tool-calling to search a lightweight
SurrealDB catalog of ~28K Gutenberg works. The LLM (Gemini Flash) knows
these texts from its training data and uses tools to verify availability
in the library, search by title/author/era, and retrieve passages from
the media server.

All SurrealDB calls use the blocking ``surrealdb.Surreal`` library
wrapped in ``run_in_executor`` to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import httpx
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from openai import OpenAI

from app.eveningdraft.deps import CurrentEDUser
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inspire", tags=["eveningdraft-inspire"])

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CHAT_MODEL = "google/gemini-2.5-flash-preview"
LIT_NAMESPACE = "eveningdraft"
LIT_DATABASE = "ed_literature"
MEDIA_BASE_URL = "https://media.cogmem.ai/media/literature"
MAX_TOOL_ROUNDS = 5


# ── Request / Response models ─────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class BookInfo(BaseModel):
    gutenberg_id: str
    title: str
    author: str
    year: int
    era: str
    gutenberg_url: str = ""


class InspireChatRequest(BaseModel):
    messages: list[ChatMessage]


class InspireChatResponse(BaseModel):
    reply: str
    books: list[BookInfo]


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


# ── Tool implementations ─────────────────────────────────────────────────

def _tool_search_library(
    query: str | None = None,
    author: str | None = None,
    era: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search the Gutenberg library catalog by title keywords, author, era, or year range."""
    db = _get_lit_db()
    try:
        filters = []
        params: dict[str, Any] = {"lim": min(limit, 20)}

        if query:
            filters.append("(title @@ $query OR author @@ $query)")
            params["query"] = query
        if author:
            filters.append("string::lowercase(author) CONTAINS string::lowercase($author)")
            params["author"] = author
        if era:
            filters.append("era = $era")
            params["era"] = era
        if year_min is not None:
            filters.append("year >= $year_min")
            params["year_min"] = year_min
        if year_max is not None:
            filters.append("year <= $year_max")
            params["year_max"] = year_max

        where = "WHERE " + " AND ".join(filters) if filters else ""
        sql = (
            f"SELECT gutenberg_id, title, author, year, era, gutenberg_url "
            f"FROM ed_lit_works {where} ORDER BY year ASC LIMIT $lim"
        )
        rows = _extract_rows(db.query(sql, params))
        return rows
    finally:
        db.close()


def _tool_get_book(gutenberg_id: str) -> dict | None:
    """Look up a specific book by its Gutenberg ID to verify it exists in the library."""
    db = _get_lit_db()
    try:
        rows = _extract_rows(db.query(
            "SELECT gutenberg_id, title, author, year, era, gutenberg_url "
            "FROM ed_lit_works WHERE gutenberg_id = $gid LIMIT 1",
            {"gid": str(gutenberg_id)},
        ))
        return rows[0] if rows else None
    finally:
        db.close()


def _tool_get_passage(gutenberg_id: str, search_term: str) -> dict:
    """Retrieve a passage from a book's full text by searching for a term.
    Returns the surrounding context around the first match."""
    url = f"{MEDIA_BASE_URL}/{gutenberg_id}.txt"
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        text = resp.text
    except Exception as e:
        return {"error": f"Could not fetch text for {gutenberg_id}: {e}"}

    # Find the search term (case-insensitive)
    pattern = re.compile(re.escape(search_term), re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return {"error": f"Term '{search_term}' not found in text {gutenberg_id}"}

    # Extract ~2000 chars of context around the match
    start = max(0, match.start() - 1000)
    end = min(len(text), match.end() + 1000)
    passage = text[start:end]

    # Clean up to paragraph boundaries
    if start > 0:
        nl = passage.find("\n")
        if nl > 0 and nl < 200:
            passage = passage[nl + 1:]
    if end < len(text):
        nl = passage.rfind("\n")
        if nl > len(passage) - 200:
            passage = passage[:nl]

    return {
        "gutenberg_id": gutenberg_id,
        "passage": passage.strip(),
        "match_position": match.start(),
    }


def _tool_get_library_stats() -> dict:
    """Get statistics about the library catalog."""
    db = _get_lit_db()
    try:
        works = _extract_rows(db.query("SELECT count() AS c FROM ed_lit_works GROUP ALL"))
        return {
            "total_works": works[0].get("c", 0) if works else 0,
            "eras": ["Ancient", "Medieval", "Renaissance", "Enlightenment", "Romantic", "Victorian", "Modern"],
        }
    finally:
        db.close()


# ── Tool definitions for OpenAI function-calling ─────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_library",
            "description": (
                "Search the Gutenberg library catalog of ~28,000 classic texts. "
                "Use this to find books by title keywords, author name, literary era, "
                "or year range. Returns matching works with their Gutenberg IDs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords for title or author (e.g. 'moby dick', 'shakespeare')",
                    },
                    "author": {
                        "type": "string",
                        "description": "Filter by author name (partial match, e.g. 'Melville')",
                    },
                    "era": {
                        "type": "string",
                        "enum": ["Ancient", "Medieval", "Renaissance", "Enlightenment", "Romantic", "Victorian", "Modern"],
                        "description": "Filter by literary era",
                    },
                    "year_min": {
                        "type": "integer",
                        "description": "Minimum publication year",
                    },
                    "year_max": {
                        "type": "integer",
                        "description": "Maximum publication year",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10, max 20)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_book",
            "description": (
                "Look up a specific book by its Project Gutenberg ID number to verify "
                "it exists in the library. Returns title, author, year, and era."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gutenberg_id": {
                        "type": "string",
                        "description": "The Project Gutenberg ID number (e.g. '2701' for Moby Dick)",
                    },
                },
                "required": ["gutenberg_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_passage",
            "description": (
                "Retrieve a specific passage from a book's full text by searching for "
                "a phrase or keyword. Returns ~2000 characters of context around the match. "
                "Use this when the user wants to read a specific part of a text, or when "
                "you want to quote an actual passage."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gutenberg_id": {
                        "type": "string",
                        "description": "The Gutenberg ID of the book",
                    },
                    "search_term": {
                        "type": "string",
                        "description": "A phrase or keyword to search for in the text",
                    },
                },
                "required": ["gutenberg_id", "search_term"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_library_stats",
            "description": "Get statistics about the library catalog (total works, available eras).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_DISPATCH = {
    "search_library": _tool_search_library,
    "get_book": _tool_get_book,
    "get_passage": _tool_get_passage,
    "get_library_stats": _tool_get_library_stats,
}

SYSTEM_PROMPT = """You are a literary guide and reading companion for Evening Draft, \
a creative writing application. You have access to a digital library of approximately \
28,000 classic texts from Project Gutenberg spanning from ancient works to the early 20th century.

Your role:
- Help users discover books based on themes, moods, topics, or literary interests
- Recommend specific works and explain why they're relevant
- Discuss literary themes, characters, and ideas across the corpus
- Retrieve and share actual passages from the texts when relevant
- Be warm, knowledgeable, and conversational — like a well-read friend

You have tools to search the library catalog, verify books exist, and retrieve passages. \
ALWAYS use the search_library or get_book tool to verify a book is in the library before \
recommending it. When you find relevant books, present them with their Gutenberg ID so \
the user can open them in the reader.

When presenting book recommendations, format them clearly with the title, author, year, \
and Gutenberg ID. For example:
📖 **Moby Dick** by Herman Melville (1851) · #2701

If the user asks about a specific passage or theme in a book, use get_passage to retrieve \
the actual text and quote it directly.

You know these texts well from your training. Use that knowledge to have rich literary \
discussions, but always verify availability with the tools before telling the user they \
can read something."""


def _chat_with_tools_sync(messages: list[dict]) -> tuple[str, list[dict]]:
    """Run the tool-calling chat loop synchronously."""
    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
    )

    chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in messages:
        chat_messages.append({"role": m["role"], "content": m["content"]})

    books_mentioned: dict[str, dict] = {}

    for _round in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=chat_messages,
            tools=TOOLS,
            max_tokens=2048,
        )

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" or (
            choice.message.tool_calls and len(choice.message.tool_calls) > 0
        ):
            # Append the assistant message with tool calls
            chat_messages.append(choice.message.model_dump())

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                logger.info("Inspire tool call: %s(%s)", fn_name, fn_args)

                fn = TOOL_DISPATCH.get(fn_name)
                if fn:
                    try:
                        result = fn(**fn_args)
                    except Exception as e:
                        logger.exception("Tool %s failed", fn_name)
                        result = {"error": str(e)}
                else:
                    result = {"error": f"Unknown tool: {fn_name}"}

                # Track books mentioned
                if fn_name == "search_library" and isinstance(result, list):
                    for book in result:
                        gid = book.get("gutenberg_id")
                        if gid:
                            books_mentioned[gid] = book
                elif fn_name == "get_book" and isinstance(result, dict) and "gutenberg_id" in result:
                    books_mentioned[result["gutenberg_id"]] = result

                chat_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })
        else:
            # Final text response
            reply = choice.message.content or ""
            return reply, list(books_mentioned.values())

    # If we exhausted rounds, get a final response without tools
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=chat_messages,
        max_tokens=2048,
    )
    reply = response.choices[0].message.content or ""
    return reply, list(books_mentioned.values())


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/chat", response_model=InspireChatResponse)
async def inspire_chat(
    body: InspireChatRequest,
    current_user: CurrentEDUser,
) -> Any:
    """Chat with the literary guide. The LLM uses tool-calling to search
    the library catalog and retrieve passages from the full texts."""
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")

    loop = asyncio.get_event_loop()
    reply, book_rows = await loop.run_in_executor(
        None, _chat_with_tools_sync,
        [m.model_dump() for m in body.messages],
    )

    books = [
        BookInfo(
            gutenberg_id=b.get("gutenberg_id", ""),
            title=b.get("title", ""),
            author=b.get("author", ""),
            year=b.get("year", 0),
            era=b.get("era", ""),
            gutenberg_url=b.get("gutenberg_url", ""),
        )
        for b in book_rows
    ]

    return InspireChatResponse(reply=reply, books=books)


@router.get("/reader/{gutenberg_id}")
async def reader_redirect(
    gutenberg_id: str,
    current_user: CurrentEDUser,
) -> RedirectResponse:
    """Redirect to the raw text file on the media server."""
    url = f"{MEDIA_BASE_URL}/{gutenberg_id}.txt"
    return RedirectResponse(url=url, status_code=302)
