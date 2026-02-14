"""SearchScorer — automated search quality testing.

Runs a set of test queries against the KOS and scores the results
for precision, recall, and latency. Generates OutcomeEvents that
feed back into the MetaKernel evaluation loop.
"""

import time
import uuid
from datetime import datetime
from typing import Any

from kos.cloud.workbench.models import SearchTestResult
from kos.core.contracts.stores.retrieval.text_search import TextSearchProvider
from kos.core.contracts.stores.retrieval.vector_search import VectorSearchProvider
from kos.core.contracts.stores.outcome_store import OutcomeStore
from kos.core.models.ids import KosId
from kos.core.models.outcome_event import OutcomeEvent, OutcomeSource, OutcomeType


class SearchScorer:
    """Runs test queries and scores search quality."""

    def __init__(
        self,
        text_search: TextSearchProvider,
        vector_search: VectorSearchProvider | None = None,
        outcome_store: OutcomeStore | None = None,
    ) -> None:
        self._text_search = text_search
        self._vector_search = vector_search
        self._outcome_store = outcome_store

    async def run_test_queries(
        self,
        queries: list[str],
        tenant_id: str,
        strategy_id: str,
        expected_keywords_map: dict[str, list[str]] | None = None,
    ) -> list[SearchTestResult]:
        """Run a batch of test queries and score results.

        Args:
            queries: List of search queries to test.
            tenant_id: Tenant to search within.
            strategy_id: Active strategy ID (for outcome recording).
            expected_keywords_map: Optional mapping of query → expected keywords
                in results. Used for precision/recall scoring.

        Returns:
            List of SearchTestResult with quality metrics.
        """
        results: list[SearchTestResult] = []
        expected_map = expected_keywords_map or {}

        for query in queries:
            result = await self._run_single_query(
                query=query,
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                expected_keywords=expected_map.get(query, []),
            )
            results.append(result)

        return results

    async def _run_single_query(
        self,
        query: str,
        tenant_id: str,
        strategy_id: str,
        expected_keywords: list[str],
    ) -> SearchTestResult:
        """Run a single test query and score it."""
        start = time.monotonic()

        try:
            search_results = await self._text_search.search(
                query=query,
                tenant_id=tenant_id,
                limit=20,
            )
            elapsed_ms = (time.monotonic() - start) * 1000

            hits_returned = len(search_results.hits)
            snippets = [
                hit.snippet or (hit.highlights[0] if hit.highlights else "")
                for hit in search_results.hits[:5]
            ]

            # Score relevance
            if expected_keywords:
                relevant_hits = 0
                for hit in search_results.hits:
                    hit_text = (hit.snippet or "") + " ".join(hit.highlights)
                    hit_text_lower = hit_text.lower()
                    if any(kw.lower() in hit_text_lower for kw in expected_keywords):
                        relevant_hits += 1

                precision = relevant_hits / hits_returned if hits_returned > 0 else 0.0
                recall = (
                    min(relevant_hits / len(expected_keywords), 1.0)
                    if expected_keywords
                    else 0.0
                )
            else:
                # Without expected keywords, use hit count as proxy
                relevant_hits = hits_returned
                precision = 1.0 if hits_returned > 0 else 0.0
                recall = 1.0 if hits_returned > 0 else 0.0

            # Record outcome event
            outcome_type = (
                OutcomeType.RETRIEVAL_SATISFIED
                if hits_returned > 0
                else OutcomeType.RETRIEVAL_FAILED
            )

        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            hits_returned = 0
            relevant_hits = 0
            precision = 0.0
            recall = 0.0
            snippets = []
            outcome_type = OutcomeType.RETRIEVAL_FAILED

        # Record outcome for the MetaKernel
        if self._outcome_store is not None:
            outcome = OutcomeEvent(
                kos_id=KosId(f"outcome-wb-{uuid.uuid4().hex[:12]}"),
                tenant_id=tenant_id,
                strategy_id=KosId(strategy_id),
                outcome_type=outcome_type,
                source=OutcomeSource.SYSTEM,
                metrics={
                    "latency_ms": elapsed_ms,
                    "hits_returned": hits_returned,
                    "precision": precision,
                    "recall": recall,
                },
                context={
                    "query": query,
                    "source": "workbench",
                },
            )
            await self._outcome_store.save_outcome(outcome)

        return SearchTestResult(
            query=query,
            expected_keywords=expected_keywords,
            hits_returned=hits_returned,
            relevant_hits=relevant_hits,
            precision=precision,
            recall=recall,
            latency_ms=elapsed_ms,
            top_snippets=snippets,
        )
