"""KOS search for Evening Draft.

Queries passages stored in the user's SurrealDB tenant database.
Uses the blocking ``surrealdb.Surreal`` library — all functions are
synchronous so they can be called from ``run_in_executor``.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def search_journal_passages_sync(
    db,
    query: str,
    tenant_id: str,
    exclude_content_types: list[str] | None = None,
    limit: int = 5,
) -> str:
    """Search journal passages, excluding chat content types.

    Matches the Swift KOSSearchService.searchJournalPassages flow:
    - Excludes content_type in ['chat/user', 'chat/assistant'] by default
    - Returns a formatted context string for the Muse system prompt.
    """
    if not query or not query.strip():
        return ""

    if exclude_content_types is None:
        exclude_content_types = ["chat/assistant", "chat/user"]

    words = query.strip().lower().split()
    if not words:
        return ""

    # Build a WHERE clause that matches any word (limit to 5 terms)
    word_conditions = " OR ".join(
        [f"string::lowercase(text) CONTAINS '{w}'" for w in words[:5]]
    )

    # Exclude chat content types from journal search (matches Swift)
    exclude_clause = ""
    if exclude_content_types:
        # Join item_id to ed_items to filter by content_type
        # Use a subquery approach: find item_ids with excluded content_types
        type_list = ", ".join([f"'{ct}'" for ct in exclude_content_types])
        exclude_clause = f"""
            AND item_id NOT IN (
                SELECT VALUE kos_id FROM ed_items WHERE content_type IN [{type_list}]
            )
        """

    sql = f"""
        SELECT kos_id, text, item_id, metadata, sequence
        FROM ed_passages
        WHERE ({word_conditions})
        {exclude_clause}
        ORDER BY sequence ASC
        LIMIT {limit}
    """

    try:
        result = db.query(sql)
        rows = result[0] if result and isinstance(result, list) else []
        if isinstance(rows, dict) and "result" in rows:
            rows = rows["result"]
    except Exception as e:
        logger.warning("Journal search query failed: %s", e)
        return ""

    if not rows:
        return ""

    # Build context string
    context_parts: list[str] = []
    total_chars = 0
    max_chars = 2000

    for row in rows:
        text = row.get("text", "")
        snippet = text[:300] + "..." if len(text) > 300 else text
        if total_chars + len(snippet) <= max_chars:
            context_parts.append(snippet)
            total_chars += len(snippet)
        else:
            break

    if not context_parts:
        return ""

    numbered = [f"[{i+1}] {part}" for i, part in enumerate(context_parts)]
    return "\n\n".join(numbered)


def search_all_passages_sync(db, query: str, tenant_id: str, limit: int = 10) -> str:
    """Search all passages (no content_type filtering).

    Used for general search across all KOS content.
    """
    if not query or not query.strip():
        return ""

    words = query.strip().lower().split()
    if not words:
        return ""

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
        rows = result[0] if result and isinstance(result, list) else []
        if isinstance(rows, dict) and "result" in rows:
            rows = rows["result"]
    except Exception as e:
        logger.warning("Search query failed: %s", e)
        return ""

    if not rows:
        return ""

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
    return "\n\n".join(numbered)
