"""5-stage temporal ingestion pipeline (GraphOS Layer 5).

Pipeline stages:
1. Loading: Accept text, JSON, or document content
2. Chunking: Adaptive semantic chunking
3. Dual-Track Extraction: entities + temporal events via LLM
4. Resolution & Validation: entity deduplication, ontology check
5. Graph Writing: store in Neo4j via Graphiti + our temporal layer
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from core.config import AppSettings
from core.exceptions import EpisodeProcessingError
from core.metrics import metrics
from core.models import (
    Entity,
    Episode,
    EpisodeType,
    ExtractionResult,
    FactType,
    Relationship,
    TemporalEvent,
    TemporalMetadata,
)
from generation.llm_client import LLMClient
from graphiti_adapter.client import GraphitiClient
from ingestion.chunker import SemanticChunker
from ingestion.extractor import DualTrackExtractor
from storage.neo4j_client import Neo4jClient
from storage.vector_store import VectorStore
from temporal.invalidation_agent import InvalidationAgent
from temporal.resolution import EntityResolver

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrates the 5-stage temporal ingestion process."""

    def __init__(
        self,
        graphiti: GraphitiClient,
        neo4j: Neo4jClient,
        vector_store: VectorStore,
        llm: LLMClient,
        invalidation_agent: InvalidationAgent,
        entity_resolver: EntityResolver,
        settings: AppSettings,
    ) -> None:
        self._graphiti = graphiti
        self._neo4j = neo4j
        self._vectors = vector_store
        self._llm = llm
        self._invalidation = invalidation_agent
        self._resolver = entity_resolver
        self._settings = settings
        self._chunker = SemanticChunker()
        self._extractor = DualTrackExtractor(llm)

    async def ingest_episode(
        self,
        content: str,
        source: str = "manual",
        episode_type: EpisodeType = EpisodeType.TEXT,
        reference_time: datetime | None = None,
        group_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest a single episode through the full pipeline.

        Returns summary of what was extracted and stored.
        """
        pipeline_start = time.monotonic()

        if reference_time is None:
            reference_time = datetime.now(UTC)

        episode = Episode(
            content=content,
            episode_type=episode_type,
            source=source,
            reference_time=reference_time,
            metadata=metadata or {},
        )

        logger.info("Ingesting episode '%s' (type=%s)", source, episode_type.value)

        # Stage 1: Graphiti ingestion (handles entity extraction + edge creation)
        # Graphiti may fail on some inputs (e.g., null entity IDs during extraction)
        # but our temporal layer (stages 2-5) should still proceed.
        graphiti_result: dict[str, Any] = {}
        try:
            graphiti_result = await self._graphiti.add_episode(
                name=source,
                content=content,
                source=source,
                reference_time=reference_time,
                episode_type=episode_type,
                group_id=group_id,
            )
        except Exception as e:
            logger.warning("Graphiti ingestion failed (continuing with temporal layer): %s", e)

        # Stage 2: Chunk for our temporal layer
        chunks = self._chunker.chunk(content)

        # Stage 3: Dual-track extraction (our temporal events layer)
        all_entities: list[Entity] = []
        all_events: list[TemporalEvent] = []
        all_relationships: list[Relationship] = []

        for chunk in chunks:
            extraction = await self._extractor.extract(
                chunk, source=source, reference_time=reference_time
            )
            all_entities.extend(extraction.entities)
            all_events.extend(extraction.temporal_events)
            all_relationships.extend(extraction.relationships)

        # Stage 4: Entity resolution
        resolved_entities = await self._resolver.resolve_batch(all_entities)

        # Generate embeddings for temporal events
        if all_events:
            statements = [e.statement for e in all_events]
            embeddings = await self._vectors.embed_batch(statements)
            for event, emb in zip(all_events, embeddings):
                event.embedding = emb

        # Stage 5a: Store in our temporal event layer
        for entity in resolved_entities:
            await self._neo4j.create_entity(entity)

        for event in all_events:
            event.temporal.source_episode_id = episode.id
            await self._neo4j.create_temporal_event(event)
            if event.entity_ids:
                await self._neo4j.link_event_to_entities(event.id, event.entity_ids)

        # Stage 5b: Run invalidation agent on new events
        invalidation_result = await self._invalidation.process_new_events(all_events)

        # Store episode metadata
        await self._neo4j.create_episode(episode)

        duration_ms = (time.monotonic() - pipeline_start) * 1000
        metrics.inc("ingest_total")
        metrics.inc("entities_extracted_total", len(all_entities))
        metrics.inc("events_extracted_total", len(all_events))
        metrics.inc("invalidated_total", len(invalidation_result.invalidated_events))
        metrics.timing("ingest_duration", duration_ms)

        summary = {
            "episode_id": episode.id,
            "source": source,
            "chunks": len(chunks),
            "entities_extracted": len(all_entities),
            "entities_resolved": len(resolved_entities),
            "temporal_events": len(all_events),
            "relationships": len(all_relationships),
            "invalidated": len(invalidation_result.invalidated_events),
            "graphiti_result": graphiti_result,
        }
        logger.info("Episode ingested: %s", summary)
        return summary

    async def ingest_batch(self, episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ingest multiple episodes sequentially."""
        results = []
        for ep_data in episodes:
            result = await self.ingest_episode(**ep_data)
            results.append(result)
        return results
