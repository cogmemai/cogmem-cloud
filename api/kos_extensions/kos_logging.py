"""KOS pipeline logging utility.

Writes structured log entries to the `kos_logs` table in the tenant's
SurrealDB database.  Each entry captures:

- **agent**: which pipeline component produced the log (e.g. "cloud_ingest",
  "chunk_agent", "entity_extract_agent")
- **level**: INFO / WARN / ERROR / DEBUG
- **event_type**: what happened (e.g. "item_saved", "chunk_complete",
  "entity_extracted", "pipeline_start", "pipeline_end")
- **correlation_id**: groups all logs from a single ingest operation
- **item_id / passage_ids / entity_ids**: relevant KOS object references
- **duration_ms**: elapsed time for the operation
- **message**: human-readable description
- **metadata**: arbitrary extra context (error tracebacks, counts, etc.)
"""

from __future__ import annotations

import time
import uuid
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from kos.providers.surrealdb.client import SurrealDBClient

logger = logging.getLogger(__name__)


@dataclass
class KosLogEntry:
    agent: str
    level: str
    event_type: str
    message: str
    correlation_id: str
    item_id: str | None = None
    passage_ids: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "level": self.level,
            "event_type": self.event_type,
            "message": self.message,
            "correlation_id": self.correlation_id,
            "item_id": self.item_id,
            "passage_ids": self.passage_ids,
            "entity_ids": self.entity_ids,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class KosLogger:
    """Writes structured log entries to the tenant's kos_logs table."""

    def __init__(self, client: SurrealDBClient, correlation_id: str | None = None):
        self._client = client
        self.correlation_id = correlation_id or str(uuid.uuid4())

    async def log(
        self,
        agent: str,
        event_type: str,
        message: str,
        *,
        level: str = "INFO",
        item_id: str | None = None,
        passage_ids: list[str] | None = None,
        entity_ids: list[str] | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Write a single log entry to kos_logs."""
        entry = KosLogEntry(
            agent=agent,
            level=level,
            event_type=event_type,
            message=message,
            correlation_id=self.correlation_id,
            item_id=item_id,
            passage_ids=passage_ids or [],
            entity_ids=entity_ids or [],
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        try:
            await self._client.create("kos_logs", entry.to_dict())
        except Exception:
            logger.exception("Failed to write kos_log entry: %s", message)

    @asynccontextmanager
    async def timed(
        self,
        agent: str,
        event_type: str,
        message: str,
        *,
        item_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Context manager that logs start + end with duration.

        Usage::

            async with kos_logger.timed("chunk_agent", "chunk_item", "Chunking item X", item_id="X"):
                # ... do work ...
                pass
        """
        start = time.monotonic()
        await self.log(agent, f"{event_type}_start", f"[START] {message}", item_id=item_id, metadata=metadata)
        error_info: dict[str, Any] | None = None
        try:
            yield
        except Exception as exc:
            error_info = {"error": str(exc), "error_type": type(exc).__name__}
            raise
        finally:
            elapsed = (time.monotonic() - start) * 1000
            level = "ERROR" if error_info else "INFO"
            final_meta = {**(metadata or {}), **(error_info or {})}
            await self.log(
                agent,
                f"{event_type}_end",
                f"[END] {message} ({elapsed:.1f}ms)",
                level=level,
                item_id=item_id,
                duration_ms=elapsed,
                metadata=final_meta if final_meta else None,
            )
