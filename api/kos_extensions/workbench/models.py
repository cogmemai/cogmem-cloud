"""Workbench models — experiment tracking, cycle results, and scoring."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExperimentStatus(str, Enum):
    """Lifecycle of a workbench experiment."""

    CREATED = "created"
    ANALYZING = "analyzing"
    INGESTING = "ingesting"
    TESTING = "testing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class CycleStatus(str, Enum):
    """Status of a single evaluation cycle within an experiment."""

    PENDING = "pending"
    INGESTING = "ingesting"
    TESTING = "testing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class SearchTestResult(BaseModel):
    """Result of a single search quality test."""

    query: str = Field(..., description="Test query")
    expected_keywords: list[str] = Field(default_factory=list)
    hits_returned: int = Field(0)
    relevant_hits: int = Field(0)
    precision: float = Field(0.0)
    recall: float = Field(0.0)
    latency_ms: float = Field(0.0)
    top_snippets: list[str] = Field(default_factory=list)


class CycleResult(BaseModel):
    """Results from one evaluation cycle."""

    cycle_number: int = Field(..., ge=1)
    status: CycleStatus = Field(CycleStatus.PENDING)
    strategy_id: str = Field(..., description="Strategy used in this cycle")
    strategy_summary: str = Field("")

    # Ingestion metrics
    items_ingested: int = Field(0)
    passages_created: int = Field(0)
    entities_extracted: int = Field(0)
    ingestion_time_ms: float = Field(0.0)

    # Search quality metrics
    test_results: list[SearchTestResult] = Field(default_factory=list)
    avg_precision: float = Field(0.0)
    avg_recall: float = Field(0.0)
    avg_latency_ms: float = Field(0.0)

    # ACP evaluation
    failure_rate: float = Field(0.0)
    conflict_density: float = Field(0.0)
    issues_detected: list[str] = Field(default_factory=list)
    proposal_generated: bool = Field(False)
    proposal_summary: str | None = Field(None)

    started_at: datetime | None = Field(None)
    completed_at: datetime | None = Field(None)


class DataProfile(BaseModel):
    """Profile of uploaded CSV data — used to derive initial strategy."""

    total_rows: int = Field(0)
    columns: list[str] = Field(default_factory=list)
    text_columns: list[str] = Field(default_factory=list)
    numeric_columns: list[str] = Field(default_factory=list)
    avg_text_length: float = Field(0.0)
    max_text_length: int = Field(0)
    sample_values: dict[str, list[str]] = Field(default_factory=dict)
    detected_content_type: str = Field("generic")
    analysis_notes: list[str] = Field(default_factory=list)


class Experiment(BaseModel):
    """A workbench experiment — tracks the full multi-cycle evaluation."""

    experiment_id: str = Field(..., description="Unique experiment identifier")
    name: str = Field("Untitled Experiment")
    status: ExperimentStatus = Field(ExperimentStatus.CREATED)
    tenant_id: str = Field("workbench")
    user_id: str = Field("workbench-user")

    # Data
    filename: str = Field("")
    data_profile: DataProfile | None = Field(None)

    # Configuration
    max_cycles: int = Field(3, ge=1, le=20)
    test_queries: list[str] = Field(default_factory=list)

    # Results
    cycles: list[CycleResult] = Field(default_factory=list)
    best_cycle: int | None = Field(None)
    best_strategy_id: str | None = Field(None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"frozen": False, "extra": "forbid"}
