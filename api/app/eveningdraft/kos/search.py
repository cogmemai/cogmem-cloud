"""KOS search for Evening Draft.

Queries passages stored in the user's SurrealDB tenant database.
Uses the blocking ``surrealdb.Surreal`` library — all functions are
synchronous so they can be called from ``run_in_executor``.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def search_passages_sync(db, query: str, tenant_id: str, limit: int = 10) -> str:
    """Search passages and return a formatted context string.

    Uses SurrealQL string::contains for keyword matching.
    Returns a ready-to-use context string for the Muse system prompt.
    """
    if not query or not query.strip():
        return ""

    words = query.strip().lower().split()
    if not words:
        return ""

    # Build a WHERE clause that matches any word (limit to 5 terms)
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
        result = db.query(sql)
        # SurrealDB blocking lib returns list of result sets
        rows = result[0] if result and isinstance(result, list) else []
        if isinstance(rows, dict) and "result" in rows:
            rows = rows["result"]
    except Exception as e:
        logger.warning("Search query failed: %s", e)
        return ""

    if not rows:
        return ""

    # Build context string
    context_parts: list[str] = []
    total_chars = 0
    max_chars = 2000

    for row in rows[:5]:
        text = row.get("text", "")
        snippet = text[:200] + "..." if len(text) > 200 else text
        if total_chars + len(snippet) <= max_chars:
            context_parts.append(snippet)
            total_chars += len(snippet)
        else:
            break

    if not context_parts:
        return ""

    numbered = [f"[{i+1}] {part}" for i, part in enumerate(context_parts)]
    return "Relevant context from knowledge base:\n\n" + "\n\n".join(numbered)
