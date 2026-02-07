"""Search recipes extending Graphiti's built-in configurations.

Adds temporal-aware search on top of Graphiti's hybrid search:
- Temporal filtering (point-in-time, time ranges)
- Follow-the-thread reranking (graph traversal from center node)
- Combined entity + event search
"""

from __future__ import annotations

import logging

from graphiti_core.search.search_filters import (
    ComparisonOperator,
    DateFilter,
    PropertyFilter,
    SearchFilters,
)

from core.models import IntentType, SearchQuery

logger = logging.getLogger(__name__)


def build_search_filters(query: SearchQuery) -> SearchFilters | None:
    """Build Graphiti SearchFilters from our SearchQuery model."""
    kwargs: dict = {}

    # Time range filter on valid_at
    if query.time_range_start:
        kwargs["valid_at"] = DateFilter(
            date=query.time_range_start,
            comparison_operator=ComparisonOperator.greater_than_equal,
        )

    if query.time_range_end:
        kwargs["created_at"] = DateFilter(
            date=query.time_range_end,
            comparison_operator=ComparisonOperator.less_than_equal,
        )

    # Entity type filter
    if query.entity_types:
        kwargs["property_filters"] = [
            PropertyFilter(
                property_name="entity_type",
                property_value=et,
                comparison_operator=ComparisonOperator.equals,
            )
            for et in query.entity_types
        ]

    if not kwargs:
        return None

    return SearchFilters(**kwargs)


def select_recipe(intent: IntentType) -> str:
    """Select best search recipe based on query intent."""
    if intent == IntentType.STRUCTURAL:
        return "node_rrf"
    elif intent == IntentType.TEMPORAL:
        return "edge_rrf"
    return "edge_rrf"
