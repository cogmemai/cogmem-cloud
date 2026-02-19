"""Text chunking for Evening Draft KOS.

Splits content into overlapping passages for search indexing.
Ported from kos_extensions/ingest.py — standalone, no cogmem-kos dependency.
"""

from __future__ import annotations

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[tuple[str, int, int]]:
    """Split *text* into overlapping chunks.

    Returns list of ``(chunk_text, start_offset, end_offset)``.
    """
    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [(text.strip(), 0, len(text))]

    chunks: list[tuple[str, int, int]] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Try to break at a natural boundary
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", " "]:
                last_sep = text.rfind(sep, start, end)
                if last_sep > start:
                    end = last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, start, end))

        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)

    return chunks
