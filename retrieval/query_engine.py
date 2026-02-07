"""Unified query engine combining Graphiti search with temporal layer.

Implements GraphOS Layers 2-4 (Query Understanding, Intent Classification,
Query Decomposition) and Layers 8-11 (Retrieval).
"""

from __future__ import annotations

import logging
from typing import Any

from core.models import (
    IntentType,
    SearchQuery,
    SearchResponse,
    SearchResult,
    TemporalMetadata,
)
from generation.llm_client import LLMClient
from graphiti_adapter.client import GraphitiClient
from graphiti_adapter.search_recipes import build_search_filters, select_recipe
from storage.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class QueryEngine:
    """Orchestrates search across Graphiti and our temporal layer."""

    def __init__(
        self,
        graphiti: GraphitiClient,
        neo4j: Neo4jClient,
        llm: LLMClient,
    ) -> None:
        self._graphiti = graphiti
        self._neo4j = neo4j
        self._llm = llm

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a unified search with intent-aware routing.

        1. Classify intent (structural/temporal/hybrid)
        2. Select search recipe
        3. Execute Graphiti search for edges/facts
        4. Execute temporal layer search if needed
        5. Merge and rerank results
        """
        # Step 1: Intent classification
        if query.intent == IntentType.HYBRID:
            detected = await self._llm.classify_intent(query.query)
            try:
                query.intent = IntentType(detected)
            except ValueError:
                query.intent = IntentType.HYBRID

        logger.info("Search: '%s' (intent=%s)", query.query, query.intent.value)

        results: list[SearchResult] = []

        # Step 2-3: Graphiti search (edges carry facts with temporal metadata)
        recipe = select_recipe(query.intent)
        filters = build_search_filters(query)

        graphiti_results = await self._graphiti.search(
            query=query.query,
            recipe=recipe,
            num_results=query.limit,
            search_filter=filters,
        )

        for edge in graphiti_results:
            result = SearchResult(
                id=edge.get("uuid", ""),
                content=edge.get("fact", edge.get("name", "")),
                result_type="relationship",
                temporal=TemporalMetadata(
                    valid_at=_parse_datetime(edge.get("valid_at")),
                    invalid_at=_parse_datetime(edge.get("invalid_at")),
                    expired_at=_parse_datetime(edge.get("expired_at")),
                ),
            )
            results.append(result)

        # Step 4: Temporal layer queries
        if query.intent in (IntentType.TEMPORAL, IntentType.HYBRID):
            temporal_results = await self._temporal_search(query)
            results.extend(temporal_results)

        # Step 5: Deduplicate and limit
        seen_content = set()
        unique_results: list[SearchResult] = []
        for r in results:
            if r.content not in seen_content:
                seen_content.add(r.content)
                unique_results.append(r)

        final = unique_results[: query.limit]

        return SearchResponse(
            query=query,
            results=final,
            total_count=len(unique_results),
        )

    async def _temporal_search(self, query: SearchQuery) -> list[SearchResult]:
        """Search the temporal event layer."""
        results: list[SearchResult] = []

        # Point-in-time snapshot
        if query.point_in_time:
            records = await self._neo4j.query_point_in_time(
                point=query.point_in_time,
                limit=query.limit,
            )
            for rec in records:
                results.append(
                    SearchResult(
                        id=rec.get("id", ""),
                        content=rec.get("statement", ""),
                        result_type="temporal_event",
                        temporal=TemporalMetadata(
                            valid_at=_parse_datetime(rec.get("valid_at")),
                        ),
                    )
                )

        return results

    async def get_timeline(self, entity_id: str) -> list[dict[str, Any]]:
        """Get full timeline of changes for an entity."""
        return await self._neo4j.get_entity_timeline(entity_id)

    async def get_evolution(self, event_id: str) -> list[dict[str, Any]]:
        """Get the supersession chain showing how a fact evolved."""
        return await self._neo4j.get_supersession_chain(event_id)


def _parse_datetime(val: str | None):
    """Try to parse datetime from string."""
    if not val or val == "None":
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None
