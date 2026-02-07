"""Dual-track extraction: entities + temporal events from text.

Track 1 (Entity Layer): Extract entities and structural relationships
Track 2 (Temporal Event Layer): Extract atomic temporal facts with timestamps

Uses LLM structured output for extraction.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from core.models import (
    Entity,
    ExtractionResult,
    FactType,
    Relationship,
    TemporalEvent,
    TemporalMetadata,
)
from generation.llm_client import LLMClient

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """\
You are a knowledge extraction assistant. Extract structured information from text.

Respond in JSON with two tracks:

{
  "entities": [
    {"name": "...", "entity_type": "Person|Organization|Product|Event|Location|Concept", "properties": {}}
  ],
  "relationships": [
    {"source": "entity_name", "target": "entity_name", "relation_type": "WORKS_FOR|CEO_OF|LOCATED_IN|PART_OF|TREATS|CAUSES|..."}
  ],
  "temporal_events": [
    {
      "statement": "atomic fact as a single sentence",
      "fact_type": "static|dynamic|atemporal",
      "entities": ["entity_name1", "entity_name2"],
      "valid_at": "ISO datetime or null if unknown"
    }
  ]
}

Rules:
- Each temporal_event must be a single atomic fact (one sentence)
- fact_type: static (rarely changes, e.g. date of birth), dynamic (changes over time, e.g. job title), atemporal (timeless, e.g. math)
- Extract ALL entities mentioned, even if no relationships are found
- valid_at should be the real-world time when the fact became true (not when you read it)
- If no specific date is mentioned, set valid_at to null
"""


class DualTrackExtractor:
    """Extract entities and temporal events from text using LLM."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def extract(
        self,
        text: str,
        source: str = "unknown",
        reference_time: datetime | None = None,
    ) -> ExtractionResult:
        """Run dual-track extraction on a text chunk."""
        if reference_time is None:
            reference_time = datetime.now(UTC)

        prompt = f"Extract entities and temporal facts from this text:\n\n{text}"
        raw = await self._llm.generate_json(prompt, system=EXTRACTION_SYSTEM_PROMPT)

        entities = self._parse_entities(raw.get("entities", []), reference_time, source)
        relationships = self._parse_relationships(raw.get("relationships", []), entities, reference_time, source)
        events = self._parse_events(raw.get("temporal_events", []), entities, reference_time, source)

        logger.info(
            "Extracted %d entities, %d relationships, %d events from chunk",
            len(entities), len(relationships), len(events),
        )
        return ExtractionResult(
            episode_id="",
            entities=entities,
            relationships=relationships,
            temporal_events=events,
        )

    def _parse_entities(
        self, raw_entities: list, reference_time: datetime, source: str
    ) -> list[Entity]:
        entities = []
        for raw in raw_entities:
            if not isinstance(raw, dict) or "name" not in raw:
                continue
            entity = Entity(
                name=raw["name"],
                entity_type=raw.get("entity_type", "Concept"),
                properties=raw.get("properties", {}),
                temporal=TemporalMetadata(
                    valid_at=reference_time,
                    source_episode_id=source,
                ),
            )
            entities.append(entity)
        return entities

    def _parse_relationships(
        self,
        raw_rels: list,
        entities: list[Entity],
        reference_time: datetime,
        source: str,
    ) -> list[Relationship]:
        name_to_id = {e.name.lower(): e.id for e in entities}
        relationships = []
        for raw in raw_rels:
            if not isinstance(raw, dict):
                continue
            src_name = raw.get("source", "").lower()
            tgt_name = raw.get("target", "").lower()
            src_id = name_to_id.get(src_name)
            tgt_id = name_to_id.get(tgt_name)
            if not src_id or not tgt_id:
                continue
            rel = Relationship(
                source_id=src_id,
                target_id=tgt_id,
                relation_type=raw.get("relation_type", "RELATED_TO"),
                temporal=TemporalMetadata(
                    valid_at=reference_time,
                    source_episode_id=source,
                ),
            )
            relationships.append(rel)
        return relationships

    def _parse_events(
        self,
        raw_events: list,
        entities: list[Entity],
        reference_time: datetime,
        source: str,
    ) -> list[TemporalEvent]:
        name_to_id = {e.name.lower(): e.id for e in entities}
        events = []
        for raw in raw_events:
            if not isinstance(raw, dict) or "statement" not in raw:
                continue

            # Parse valid_at
            valid_at = reference_time
            if raw.get("valid_at"):
                try:
                    valid_at = datetime.fromisoformat(raw["valid_at"])
                except (ValueError, TypeError):
                    pass

            # Map entity names to IDs
            entity_ids = []
            for ename in raw.get("entities", []):
                eid = name_to_id.get(ename.lower())
                if eid:
                    entity_ids.append(eid)

            fact_type_str = raw.get("fact_type", "dynamic")
            try:
                fact_type = FactType(fact_type_str)
            except ValueError:
                fact_type = FactType.DYNAMIC

            event = TemporalEvent(
                statement=raw["statement"],
                fact_type=fact_type,
                entity_ids=entity_ids,
                source=source,
                temporal=TemporalMetadata(
                    valid_at=valid_at,
                    source_episode_id=source,
                ),
            )
            events.append(event)
        return events
