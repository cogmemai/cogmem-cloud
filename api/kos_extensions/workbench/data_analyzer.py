"""DataAnalyzer — profiles CSV data and derives an initial MemoryStrategy.

This fills a critical gap in the ACP: the MetaKernel only reacts to outcome
signals *after* ingestion. The DataAnalyzer examines raw data *before*
ingestion to propose an intelligent starting strategy.

Heuristics:
- Short texts (< 200 chars avg) → sentence chunking, small chunks
- Medium texts (200-1000 chars) → paragraph chunking
- Long texts (> 1000 chars) → semantic chunking, larger chunks
- Many columns → likely structured data, graph-heavy strategy
- Few text columns → simpler retrieval, FTS-first
- High cardinality text → vector search benefits
"""

import csv
import io
import sys
import uuid
from typing import Any

# Allow very large CSV fields (e.g. full document text in a single cell)
csv.field_size_limit(sys.maxsize)

from kos_extensions.workbench.models import DataProfile
from kos.core.models.ids import KosId
from kos.core.models.strategy import (
    ChunkingMode,
    ClaimPolicy,
    DocumentPolicy,
    GraphConstraintLevel,
    GraphPolicy,
    MemoryStrategy,
    RetrievalMode,
    RetrievalPolicy,
    StrategyCreator,
    StrategyScopeType,
    StrategyStatus,
    VectorPolicy,
)


class DataAnalyzer:
    """Analyzes CSV data and derives an initial MemoryStrategy."""

    def profile_csv(self, csv_content: str) -> DataProfile:
        """Profile CSV content and return a DataProfile."""
        reader = csv.DictReader(io.StringIO(csv_content))
        columns = reader.fieldnames or []

        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append(row)

        if not rows:
            return DataProfile(
                total_rows=0,
                columns=list(columns),
                analysis_notes=["Empty CSV — no rows found."],
            )

        total_rows = len(rows)

        # Classify columns
        text_columns: list[str] = []
        numeric_columns: list[str] = []

        for col in columns:
            values = [row.get(col, "") for row in rows if row.get(col, "").strip()]
            if not values:
                continue

            # Check if numeric
            numeric_count = 0
            for v in values[:100]:
                try:
                    float(v.replace(",", ""))
                    numeric_count += 1
                except (ValueError, AttributeError):
                    pass

            if numeric_count / len(values[:100]) > 0.8:
                numeric_columns.append(col)
            else:
                # Check average length to determine if it's a text field
                avg_len = sum(len(v) for v in values[:100]) / len(values[:100])
                if avg_len > 10:
                    text_columns.append(col)

        # Compute text stats across text columns
        all_text_lengths: list[int] = []
        for col in text_columns:
            for row in rows:
                val = row.get(col, "")
                if val.strip():
                    all_text_lengths.append(len(val))

        avg_text_length = (
            sum(all_text_lengths) / len(all_text_lengths) if all_text_lengths else 0.0
        )
        max_text_length = max(all_text_lengths) if all_text_lengths else 0

        # Sample values
        sample_values: dict[str, list[str]] = {}
        for col in columns:
            vals = [row.get(col, "") for row in rows[:5] if row.get(col, "").strip()]
            sample_values[col] = vals[:3]

        # Detect content type
        detected_content_type = self._detect_content_type(
            columns, text_columns, avg_text_length, sample_values
        )

        # Analysis notes
        notes: list[str] = []
        notes.append(f"{total_rows} rows, {len(columns)} columns")
        notes.append(f"{len(text_columns)} text columns, {len(numeric_columns)} numeric columns")
        if avg_text_length > 0:
            notes.append(f"Avg text length: {avg_text_length:.0f} chars")
        notes.append(f"Detected content type: {detected_content_type}")

        return DataProfile(
            total_rows=total_rows,
            columns=list(columns),
            text_columns=text_columns,
            numeric_columns=numeric_columns,
            avg_text_length=avg_text_length,
            max_text_length=max_text_length,
            sample_values=sample_values,
            detected_content_type=detected_content_type,
            analysis_notes=notes,
        )

    def derive_strategy(
        self,
        profile: DataProfile,
        scope_id: str = "workbench",
    ) -> MemoryStrategy:
        """Derive an initial MemoryStrategy from a DataProfile.

        Uses heuristics based on text length, column count, and content type
        to choose chunking, retrieval, and graph policies.
        """
        # --- Chunking policy ---
        if profile.avg_text_length < 200:
            chunking_mode = ChunkingMode.SENTENCE
            chunk_size = 200
            overlap = 20
        elif profile.avg_text_length < 1000:
            chunking_mode = ChunkingMode.PARAGRAPH
            chunk_size = 500
            overlap = 50
        else:
            chunking_mode = ChunkingMode.SEMANTIC
            chunk_size = 1000
            overlap = 100

        # --- Retrieval policy ---
        if len(profile.text_columns) <= 1:
            retrieval_mode = RetrievalMode.FTS_FIRST
            top_k = 10
        elif profile.avg_text_length > 500:
            retrieval_mode = RetrievalMode.HYBRID
            top_k = 20
        else:
            retrieval_mode = RetrievalMode.VECTOR_FIRST
            top_k = 15

        # --- Graph policy ---
        many_columns = len(profile.columns) > 5
        graph_enabled = many_columns or profile.detected_content_type in (
            "structured", "relational", "knowledge_base"
        )
        constraint_level = (
            GraphConstraintLevel.SOFT if graph_enabled
            else GraphConstraintLevel.NONE
        )

        # --- Vector policy ---
        vector_enabled = profile.avg_text_length > 50

        rationale_parts = [
            f"Auto-derived from data profile: {profile.total_rows} rows,",
            f"{len(profile.text_columns)} text cols,",
            f"avg text {profile.avg_text_length:.0f} chars.",
            f"Content type: {profile.detected_content_type}.",
            f"Chunking: {chunking_mode.value} ({chunk_size} chars).",
            f"Retrieval: {retrieval_mode.value} (top_k={top_k}).",
            f"Graph: {'enabled' if graph_enabled else 'disabled'}.",
            f"Vector: {'enabled' if vector_enabled else 'disabled'}.",
        ]

        return MemoryStrategy(
            kos_id=KosId(f"strategy-wb-{uuid.uuid4().hex[:12]}"),
            scope_type=StrategyScopeType.TENANT,
            scope_id=scope_id,
            version=1,
            status=StrategyStatus.ACTIVE,
            created_by=StrategyCreator.AGENT,
            rationale=" ".join(rationale_parts),
            retrieval_policy=RetrievalPolicy(
                mode=retrieval_mode,
                top_k_default=top_k,
                rerank_enabled=retrieval_mode == RetrievalMode.HYBRID,
            ),
            document_policy=DocumentPolicy(
                chunking_mode=chunking_mode,
                chunk_size=chunk_size,
                overlap=overlap,
            ),
            vector_policy=VectorPolicy(enabled=vector_enabled),
            graph_policy=GraphPolicy(
                enabled=graph_enabled,
                constraint_level=constraint_level,
            ),
            claim_policy=ClaimPolicy(),
        )

    def _detect_content_type(
        self,
        columns: list[str],
        text_columns: list[str],
        avg_text_length: float,
        sample_values: dict[str, list[str]],
    ) -> str:
        """Heuristic content type detection from column names and data."""
        col_lower = [c.lower() for c in columns]

        # Email-like
        if any(k in col_lower for k in ("subject", "from", "to", "body", "sender")):
            return "email"

        # Chat/conversation
        if any(k in col_lower for k in ("message", "speaker", "role", "utterance")):
            return "conversation"

        # Knowledge base / FAQ
        if any(k in col_lower for k in ("question", "answer", "faq", "topic")):
            return "knowledge_base"

        # Articles / documents
        if any(k in col_lower for k in ("title", "content", "body", "text", "article")):
            if avg_text_length > 500:
                return "articles"
            return "short_text"

        # Structured / relational
        if len(text_columns) < len(columns) / 2:
            return "structured"

        return "generic"
