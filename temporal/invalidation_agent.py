"""Invalidation Agent: detects contradictions and supersedes old facts.

Implements the 3-filter + LLM pipeline from GraphOS architecture:
1. Temporal Overlap: check if events cover the same time period
2. Shared Entities: check if events reference the same entities
3. Semantic Similarity: check embedding cosine similarity > threshold
4. LLM Confirmation: final check via LLM to confirm contradiction
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from core.config import AppSettings
from core.exceptions import InvalidationError
from core.models import (
    DriftSeverity,
    InvalidationCandidate,
    InvalidationResult,
    TemporalEvent,
)
from core.webhooks import WebhookManager
from generation.llm_client import LLMClient
from storage.neo4j_client import Neo4jClient
from storage.vector_store import VectorStore

logger = logging.getLogger(__name__)


class InvalidationAgent:
    """Detects contradictions between new and existing temporal events.

    Pipeline: temporal_overlap → shared_entities → semantic_similarity → llm_check
    """

    def __init__(
        self,
        neo4j: Neo4jClient,
        vector_store: VectorStore,
        llm: LLMClient,
        settings: AppSettings,
        webhook_manager: WebhookManager | None = None,
    ) -> None:
        self._neo4j = neo4j
        self._vectors = vector_store
        self._llm = llm
        self._similarity_threshold = settings.invalidation_similarity_threshold
        self._webhooks = webhook_manager

    async def process_new_events(self, new_events: list[TemporalEvent]) -> InvalidationResult:
        """Process new events and invalidate contradicted existing ones."""
        invalidated_ids: list[str] = []
        supersede_pairs: list[tuple[str, str]] = []
        max_severity = DriftSeverity.INFO

        for new_event in new_events:
            candidates = await self._find_candidates(new_event)
            for candidate in candidates:
                if candidate.llm_confirmed:
                    # Supersede the old event
                    await self._neo4j.supersede_event(
                        old_id=candidate.existing_event.id,
                        new_id=new_event.id,
                    )
                    invalidated_ids.append(candidate.existing_event.id)
                    supersede_pairs.append((candidate.existing_event.id, new_event.id))
                    logger.info(
                        "Superseded event '%s' with '%s'",
                        candidate.existing_event.statement[:50],
                        new_event.statement[:50],
                    )
                    max_severity = DriftSeverity.CRITICAL
                    # Fire webhook
                    if self._webhooks:
                        try:
                            await self._webhooks.notify_supersession(
                                old_id=candidate.existing_event.id,
                                old_statement=candidate.existing_event.statement,
                                new_id=new_event.id,
                                new_statement=new_event.statement,
                            )
                        except Exception as e:
                            logger.warning("Webhook notification failed: %s", e)

        return InvalidationResult(
            invalidated_events=invalidated_ids,
            supersede_pairs=supersede_pairs,
            severity=max_severity if invalidated_ids else DriftSeverity.INFO,
        )

    async def _find_candidates(self, new_event: TemporalEvent) -> list[InvalidationCandidate]:
        """Find existing events that may be contradicted by the new one.

        3-filter pipeline:
        1. Get events for shared entities (filter 2)
        2. Check temporal overlap (filter 1)
        3. Check semantic similarity (filter 3)
        4. LLM confirmation (filter 4)
        """
        if not new_event.entity_ids:
            return []

        # Filter 2: shared entities — get existing current events for same entities
        existing_records = await self._neo4j.get_current_events_for_entities(new_event.entity_ids)

        candidates: list[InvalidationCandidate] = []

        for record in existing_records:
            existing_id = record["id"]
            # Don't compare event with itself
            if existing_id == new_event.id:
                continue

            existing_event = TemporalEvent(
                id=existing_id,
                statement=record["statement"],
                entity_ids=record.get("entity_ids", []),
                embedding=record.get("embedding"),
            )

            # Find shared entity IDs
            shared = set(new_event.entity_ids) & set(existing_event.entity_ids)
            if not shared:
                continue

            candidate = InvalidationCandidate(
                existing_event=existing_event,
                new_event=new_event,
                shared_entity_ids=list(shared),
            )

            # Filter 1: temporal overlap
            candidate.temporal_overlap = self._check_temporal_overlap(existing_event, new_event)

            # Filter 3: semantic similarity
            if new_event.embedding and existing_event.embedding:
                candidate.semantic_similarity = VectorStore.cosine_similarity(
                    new_event.embedding, existing_event.embedding
                )

            # Only proceed to LLM if similarity is above threshold
            if candidate.semantic_similarity >= self._similarity_threshold:
                # Filter 4: LLM confirmation
                candidate.llm_confirmed = await self._llm_check(
                    existing_event.statement, new_event.statement
                )

            if candidate.llm_confirmed:
                candidates.append(candidate)

        return candidates

    def _check_temporal_overlap(self, existing: TemporalEvent, new: TemporalEvent) -> bool:
        """Check if two events have overlapping temporal scopes."""
        existing_valid = existing.temporal.valid_at
        new_valid = new.temporal.valid_at

        if existing_valid is None or new_valid is None:
            return True  # If no temporal info, assume potential overlap

        existing_expired = existing.temporal.expired_at
        if existing_expired and new_valid > existing_expired:
            return False  # New event is after existing expired

        return True

    async def _llm_check(self, existing_fact: str, new_fact: str) -> bool:
        """Use LLM to confirm if facts contradict each other."""
        try:
            result = await self._llm.check_contradiction(existing_fact, new_fact)
            return result.get("contradicts", False)
        except Exception as e:
            logger.warning("LLM contradiction check failed: %s", e)
            return False
