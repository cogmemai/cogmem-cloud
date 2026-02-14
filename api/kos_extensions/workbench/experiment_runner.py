"""ExperimentRunner — orchestrates the full multi-cycle evaluation loop.

The runner ties together:
1. DataAnalyzer → profile CSV, derive initial strategy
2. Ingestion → chunk text, store items/passages, index for search
3. SearchScorer → run test queries, record outcomes
4. MetaKernel → evaluate strategy, generate proposals
5. RestructuringExecutor → apply approved proposals
6. Loop → re-ingest with new strategy, re-test, compare

Each cycle produces a CycleResult with ingestion and search quality metrics.
The experiment tracks all cycles and identifies the best-performing strategy.
"""

import csv
import io
import time
import uuid
from datetime import datetime
from typing import Any

from kos.cloud.workbench.data_analyzer import DataAnalyzer
from kos.cloud.workbench.models import (
    CycleResult,
    CycleStatus,
    DataProfile,
    Experiment,
    ExperimentStatus,
)
from kos.cloud.workbench.search_scorer import SearchScorer
from kos.core.acp.meta_kernel import MetaKernel
from kos.core.contracts.stores.object_store import ObjectStore
from kos.core.contracts.stores.outcome_store import OutcomeStore
from kos.core.contracts.stores.proposal_store import ProposalStore
from kos.core.contracts.stores.retrieval.text_search import TextSearchProvider
from kos.core.contracts.stores.retrieval.vector_search import VectorSearchProvider
from kos.core.contracts.stores.strategy_store import StrategyStore
from kos.core.models.ids import KosId
from kos.core.models.item import Item
from kos.core.models.passage import ExtractionMethod, Passage, TextSpan
from kos.core.models.strategy import MemoryStrategy, StrategyStatus
from kos.core.models.strategy_change_proposal import ProposalStatus


class ExperimentRunner:
    """Orchestrates multi-cycle evaluation experiments."""

    def __init__(
        self,
        object_store: ObjectStore,
        text_search: TextSearchProvider,
        vector_search: VectorSearchProvider | None,
        strategy_store: StrategyStore,
        outcome_store: OutcomeStore,
        proposal_store: ProposalStore,
    ) -> None:
        self._object_store = object_store
        self._text_search = text_search
        self._vector_search = vector_search
        self._strategy_store = strategy_store
        self._outcome_store = outcome_store
        self._proposal_store = proposal_store

        self._analyzer = DataAnalyzer()
        self._scorer = SearchScorer(
            text_search=text_search,
            vector_search=vector_search,
            outcome_store=outcome_store,
        )
        self._meta_kernel = MetaKernel(
            strategy_store=strategy_store,
            outcome_store=outcome_store,
            proposal_store=proposal_store,
            evaluation_window_hours=1,  # Short window for workbench
        )

        # In-memory experiment store (keyed by experiment_id)
        self._experiments: dict[str, Experiment] = {}
        # Raw CSV content cache (keyed by experiment_id)
        self._csv_cache: dict[str, str] = {}

    def list_experiments(self) -> list[Experiment]:
        """List all experiments."""
        return list(self._experiments.values())

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        """Get an experiment by ID."""
        return self._experiments.get(experiment_id)

    async def create_experiment(
        self,
        name: str,
        csv_content: str,
        test_queries: list[str] | None = None,
        max_cycles: int = 3,
    ) -> Experiment:
        """Create a new experiment from CSV data.

        Profiles the data and derives an initial strategy but does NOT
        start ingestion. Call run_next_cycle() to begin.
        """
        experiment_id = f"exp-{uuid.uuid4().hex[:12]}"

        # Profile the data
        profile = self._analyzer.profile_csv(csv_content)

        # Auto-generate test queries from data if none provided
        if not test_queries:
            test_queries = self._generate_test_queries(csv_content, profile)

        experiment = Experiment(
            experiment_id=experiment_id,
            name=name,
            status=ExperimentStatus.ANALYZING,
            data_profile=profile,
            filename=f"{name}.csv",
            max_cycles=max_cycles,
            test_queries=test_queries,
        )

        self._experiments[experiment_id] = experiment
        self._csv_cache[experiment_id] = csv_content

        # Derive and save initial strategy
        strategy = self._analyzer.derive_strategy(
            profile, scope_id=experiment.tenant_id
        )
        await self._strategy_store.save_strategy(strategy)

        experiment.status = ExperimentStatus.CREATED
        experiment.updated_at = datetime.utcnow()

        return experiment

    async def run_next_cycle(self, experiment_id: str) -> CycleResult:
        """Run the next evaluation cycle for an experiment.

        Each cycle:
        1. Resolves the current active strategy
        2. Ingests data using that strategy
        3. Runs search quality tests
        4. Records outcomes
        5. Runs MetaKernel evaluation
        6. Auto-approves and records any proposals for the next cycle
        """
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment {experiment_id} not found")

        csv_content = self._csv_cache.get(experiment_id)
        if csv_content is None:
            raise ValueError(f"CSV data not found for experiment {experiment_id}")

        cycle_number = len(experiment.cycles) + 1
        if cycle_number > experiment.max_cycles:
            raise ValueError(
                f"Experiment has reached max cycles ({experiment.max_cycles})"
            )

        # Get current active strategy
        strategies = await self._strategy_store.list_strategies(
            scope_id=experiment.tenant_id,
            include_deprecated=False,
        )
        active_strategies = [s for s in strategies if s.status == StrategyStatus.ACTIVE]
        strategy = active_strategies[0] if active_strategies else self._analyzer.derive_strategy(
            experiment.data_profile, scope_id=experiment.tenant_id
        )

        cycle = CycleResult(
            cycle_number=cycle_number,
            status=CycleStatus.INGESTING,
            strategy_id=str(strategy.kos_id),
            strategy_summary=strategy.rationale,
            started_at=datetime.utcnow(),
        )
        experiment.cycles.append(cycle)
        experiment.status = ExperimentStatus.INGESTING
        experiment.updated_at = datetime.utcnow()

        try:
            # --- Phase 1: Ingest data ---
            ingestion_start = time.monotonic()
            items, passages = await self._ingest_csv(
                csv_content=csv_content,
                strategy=strategy,
                tenant_id=experiment.tenant_id,
                user_id=experiment.user_id,
                cycle_number=cycle_number,
            )
            cycle.items_ingested = len(items)
            cycle.passages_created = len(passages)
            cycle.ingestion_time_ms = (time.monotonic() - ingestion_start) * 1000

            # --- Phase 2: Run search tests ---
            cycle.status = CycleStatus.TESTING
            experiment.status = ExperimentStatus.TESTING
            experiment.updated_at = datetime.utcnow()

            test_results = await self._scorer.run_test_queries(
                queries=experiment.test_queries,
                tenant_id=experiment.tenant_id,
                strategy_id=str(strategy.kos_id),
            )
            cycle.test_results = test_results

            if test_results:
                cycle.avg_precision = sum(r.precision for r in test_results) / len(test_results)
                cycle.avg_recall = sum(r.recall for r in test_results) / len(test_results)
                cycle.avg_latency_ms = sum(r.latency_ms for r in test_results) / len(test_results)

            # --- Phase 3: MetaKernel evaluation ---
            cycle.status = CycleStatus.EVALUATING
            experiment.status = ExperimentStatus.EVALUATING
            experiment.updated_at = datetime.utcnow()

            evaluation = await self._meta_kernel.evaluate_strategy(strategy)
            cycle.failure_rate = evaluation.failure_rate
            cycle.conflict_density = evaluation.conflict_density
            cycle.issues_detected = evaluation.issues

            # Generate proposal if warranted
            proposal = await self._meta_kernel.generate_proposal(evaluation)
            if proposal is not None:
                cycle.proposal_generated = True
                cycle.proposal_summary = proposal.change_summary

                # Auto-approve for workbench experiments
                await self._proposal_store.update_status(
                    proposal.kos_id, ProposalStatus.APPROVED
                )

                # Activate the proposed strategy
                proposed_strategy = await self._strategy_store.get_strategy(
                    proposal.proposed_strategy_id
                )
                if proposed_strategy is not None:
                    proposed_strategy.status = StrategyStatus.ACTIVE
                    await self._strategy_store.save_strategy(proposed_strategy)

                # Deprecate the old strategy
                await self._strategy_store.deprecate_strategy(strategy.kos_id)

                await self._proposal_store.update_status(
                    proposal.kos_id, ProposalStatus.COMPLETED
                )

            # --- Done ---
            cycle.status = CycleStatus.COMPLETED
            cycle.completed_at = datetime.utcnow()

            # Update best cycle tracking
            self._update_best_cycle(experiment)

            if cycle_number >= experiment.max_cycles:
                experiment.status = ExperimentStatus.COMPLETED
            else:
                experiment.status = ExperimentStatus.CREATED  # Ready for next cycle
            experiment.updated_at = datetime.utcnow()

        except Exception as e:
            cycle.status = CycleStatus.FAILED
            cycle.issues_detected.append(f"Cycle failed: {str(e)}")
            experiment.status = ExperimentStatus.FAILED
            experiment.updated_at = datetime.utcnow()
            raise

        return cycle

    async def _ingest_csv(
        self,
        csv_content: str,
        strategy: MemoryStrategy,
        tenant_id: str,
        user_id: str,
        cycle_number: int,
    ) -> tuple[list[Item], list[Passage]]:
        """Ingest CSV rows as Items and chunk them into Passages.

        Uses the strategy's document_policy to determine chunking.
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        columns = reader.fieldnames or []

        # Identify the primary text column(s)
        text_cols = []
        title_col = None
        for col in columns:
            col_lower = col.lower()
            if col_lower in ("title", "name", "subject"):
                title_col = col
            elif col_lower in ("content", "text", "body", "description", "message", "answer"):
                text_cols.append(col)

        # Fallback: use all non-numeric columns as text
        if not text_cols:
            text_cols = [c for c in columns if c != title_col]

        items: list[Item] = []
        passages: list[Passage] = []

        for i, row in enumerate(reader):
            # Build content from text columns
            content_parts = []
            for col in text_cols:
                val = row.get(col, "").strip()
                if val:
                    content_parts.append(f"{col}: {val}")

            content_text = "\n".join(content_parts)
            if not content_text.strip():
                continue

            title = row.get(title_col, f"Row {i + 1}") if title_col else f"Row {i + 1}"

            item_id = KosId(f"item-wb-c{cycle_number}-{uuid.uuid4().hex[:8]}")
            item = Item(
                kos_id=item_id,
                tenant_id=tenant_id,
                user_id=user_id,
                source="api",
                title=title,
                content_text=content_text,
                content_type="csv_row",
                metadata={"cycle": cycle_number, "row_index": i},
            )

            # Store item
            await self._object_store.save_item(item)
            items.append(item)

            # Chunk into passages using strategy
            row_passages = self._chunk_text(
                text=content_text,
                item_id=item_id,
                tenant_id=tenant_id,
                user_id=user_id,
                strategy=strategy,
                cycle_number=cycle_number,
            )

            for passage in row_passages:
                await self._object_store.save_passage(passage)

                # Index for text search
                await self._text_search.index_passage(
                    kos_id=str(passage.kos_id),
                    tenant_id=tenant_id,
                    user_id=user_id,
                    item_id=str(item_id),
                    text=passage.text,
                    title=title,
                    source="api",
                    content_type="csv_row",
                    metadata={"cycle": cycle_number},
                )

                passages.append(passage)

        return items, passages

    def _chunk_text(
        self,
        text: str,
        item_id: KosId,
        tenant_id: str,
        user_id: str,
        strategy: MemoryStrategy,
        cycle_number: int,
    ) -> list[Passage]:
        """Chunk text according to the strategy's document policy."""
        doc_policy = strategy.document_policy
        chunk_size = doc_policy.chunk_size
        overlap = doc_policy.overlap

        passages: list[Passage] = []

        if doc_policy.chunking_mode == "sentence":
            chunks = self._chunk_by_sentence(text, chunk_size)
        elif doc_policy.chunking_mode == "paragraph":
            chunks = self._chunk_by_paragraph(text, chunk_size)
        else:
            # Fixed or semantic (fallback to fixed for now)
            chunks = self._chunk_fixed(text, chunk_size, overlap)

        for seq, (chunk_text, start, end) in enumerate(chunks):
            if not chunk_text.strip():
                continue

            passage = Passage(
                kos_id=KosId(f"psg-wb-c{cycle_number}-{uuid.uuid4().hex[:8]}"),
                item_id=item_id,
                tenant_id=tenant_id,
                user_id=user_id,
                text=chunk_text,
                span=TextSpan(start=start, end=end),
                sequence=seq,
                extraction_method=ExtractionMethod.CHUNKING,
                metadata={"cycle": cycle_number, "chunking_mode": doc_policy.chunking_mode.value},
            )
            passages.append(passage)

        return passages

    def _chunk_fixed(
        self, text: str, chunk_size: int, overlap: int
    ) -> list[tuple[str, int, int]]:
        """Fixed-size chunking with overlap."""
        chunks: list[tuple[str, int, int]] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append((text[start:end], start, end))
            start += chunk_size - overlap
            if start >= len(text):
                break
        return chunks

    def _chunk_by_sentence(
        self, text: str, max_chunk_size: int
    ) -> list[tuple[str, int, int]]:
        """Sentence-based chunking — group sentences up to max_chunk_size."""
        import re

        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks: list[tuple[str, int, int]] = []
        current_chunk = ""
        current_start = 0

        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 > max_chunk_size and current_chunk:
                end = current_start + len(current_chunk)
                chunks.append((current_chunk.strip(), current_start, end))
                current_start = end
                current_chunk = sentence
            else:
                current_chunk = (current_chunk + " " + sentence).strip()

        if current_chunk.strip():
            end = current_start + len(current_chunk)
            chunks.append((current_chunk.strip(), current_start, end))

        return chunks

    def _chunk_by_paragraph(
        self, text: str, max_chunk_size: int
    ) -> list[tuple[str, int, int]]:
        """Paragraph-based chunking — split on double newlines."""
        paragraphs = text.split("\n\n")
        chunks: list[tuple[str, int, int]] = []
        current_chunk = ""
        current_start = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 2 > max_chunk_size and current_chunk:
                end = current_start + len(current_chunk)
                chunks.append((current_chunk.strip(), current_start, end))
                current_start = end
                current_chunk = para
            else:
                current_chunk = (current_chunk + "\n\n" + para).strip()

        if current_chunk.strip():
            end = current_start + len(current_chunk)
            chunks.append((current_chunk.strip(), current_start, end))

        return chunks

    def _generate_test_queries(
        self, csv_content: str, profile: DataProfile
    ) -> list[str]:
        """Auto-generate test queries from the data.

        Extracts distinctive terms from the first few rows of text columns
        to create meaningful search queries.
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        queries: list[str] = []

        for i, row in enumerate(reader):
            if i >= 5:
                break

            for col in profile.text_columns[:2]:
                val = row.get(col, "").strip()
                if val and len(val) > 20:
                    # Take first meaningful phrase (up to 60 chars)
                    words = val.split()
                    query = " ".join(words[:6])
                    if query not in queries:
                        queries.append(query)

        # Ensure at least one query
        if not queries:
            queries = ["test query"]

        return queries[:10]

    def _update_best_cycle(self, experiment: Experiment) -> None:
        """Update the best cycle based on avg_precision."""
        best_precision = -1.0
        best_idx = None

        for i, cycle in enumerate(experiment.cycles):
            if cycle.status == CycleStatus.COMPLETED:
                score = cycle.avg_precision * 0.6 + cycle.avg_recall * 0.4
                if score > best_precision:
                    best_precision = score
                    best_idx = i

        if best_idx is not None:
            experiment.best_cycle = best_idx + 1
            experiment.best_strategy_id = experiment.cycles[best_idx].strategy_id
