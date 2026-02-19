"""KOS search for Evening Draft.

Queries passages stored in the user's SurrealDB tenant database.
Simple keyword-based search until we add vector embeddings.
"""

from __future__ import annotations

import logging
import time

from surrealdb import SurrealDB

from app.eveningdraft.kos.models import SearchHit, SearchResults

logger = logging.getLogger(__name__)


async def search_passages(
    db: SurrealDB,
    query: str,
    tenant_id: str,
    limit: int = 10,
) -> SearchResults:
    """Search passages in the tenant's SurrealDB database.

    Uses a simple CONTAINS-based text search. Returns ranked results.
    """
    start = time.monotonic()

    if not query or not query.strip():
        return SearchResults()

    # SurrealDB text search — use string::contains for now
    # Future: add full-text index or vector search
    words = query.strip().lower().split()
    if not words:
        return SearchResults()

    # Build a WHERE clause that matches any word
    conditions = " OR ".join(
        [f"string::lowercase(text) CONTAINS '{w}'" for w in words[:5]]
    )

    sql = f"""
        SELECT kos_id, text, item_id, metadata, sequence
        FROM ed_passages
        WHERE ({conditions})
        ORDER BY sequence ASC
        LIMIT {limit}
    """

    try:
        result = await db.query(sql)
        rows = result[0] if result and isinstance(result, list) else []
        if isinstance(rows, dict) and "result" in rows:
            rows = rows["result"]
    except Exception as e:
        logger.warning("Search query failed: %s", e)
        return SearchResults()

    hits: list[SearchHit] = []
    for row in rows:
        text = row.get("text", "")
        snippet = text[:200] + "..." if len(text) > 200 else text
        title = row.get("metadata", {}).get("source_title", None)

        hits.append(
            SearchHit(
                kos_id=row.get("kos_id", ""),
                score=1.0,  # simple match score
                snippet=snippet,
                title=title,
                item_id=row.get("item_id"),
            )
        )

    took_ms = int((time.monotonic() - start) * 1000)

    return SearchResults(
        hits=hits,
        total=len(hits),
        took_ms=took_ms,
    )


async def get_context_for_chat(
    db: SurrealDB,
    query: str,
    tenant_id: str,
    max_passages: int = 5,
    max_chars: int = 2000,
) -> str:
    """Retrieve relevant context passages for the Muse system prompt."""
    results = await search_passages(db, query, tenant_id, limit=max_passages * 2)

    context_parts: list[str] = []
    total_chars = 0

    for hit in results.hits[:max_passages]:
        if total_chars + len(hit.snippet) <= max_chars:
            context_parts.append(hit.snippet)
            total_chars += len(hit.snippet)
        else:
            break

    if not context_parts:
        return ""

    numbered = [f"[{i+1}] {part}" for i, part in enumerate(context_parts)]
    return "Relevant context from knowledge base:\n\n" + "\n\n".join(numbered)
