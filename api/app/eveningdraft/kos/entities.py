"""Regex-based entity extraction for Evening Draft KOS.

Ported from kos_extensions/ingest.py — standalone, no cogmem-kos dependency.
"""

from __future__ import annotations

import re

from app.eveningdraft.kos.models import EntityType

ENTITY_PATTERNS: dict[EntityType, list[str]] = {
    EntityType.PERSON: [
        r"\b(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+",
        r"\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?=\s+(?:said|says|told|wrote|is|was|has|had))",
    ],
    EntityType.ORGANIZATION: [
        r"\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\s+(?:Inc\.|Corp\.|LLC|Ltd\.|Company|Corporation|Foundation|Institute|University|College)\b",
        r"\b(?:The\s+)?[A-Z][A-Za-z]+\s+(?:Group|Team|Department|Division|Board)\b",
    ],
    EntityType.LOCATION: [
        r"\b(?:New\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s+[A-Z]{2}\b",
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:City|County|State|Country|Province|Region)\b",
    ],
    EntityType.DATE: [
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    ],
}


def extract_entities(text: str) -> list[tuple[str, EntityType]]:
    """Extract named entities from *text* using regex patterns.

    Returns list of ``(entity_name, entity_type)``.
    """
    entities: list[tuple[str, EntityType]] = []
    seen: set[str] = set()

    for entity_type, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            for match in re.findall(pattern, text):
                name = match.strip()
                if name and name not in seen and len(name) > 2:
                    seen.add(name)
                    entities.append((name, entity_type))

    return entities
