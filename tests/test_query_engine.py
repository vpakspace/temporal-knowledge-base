"""Unit tests for QueryEngine.search_with_fallback().

Tests the broad search fallback logic that was extracted from
api/server.py and mcp_server.py during refactoring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models import (
    IntentType,
    SearchQuery,
    SearchResponse,
    SearchResult,
    TemporalMetadata,
)
from retrieval.query_engine import QueryEngine


@pytest.fixture
def query_engine():
    """Create QueryEngine with mocked dependencies."""
    graphiti = AsyncMock()
    neo4j = AsyncMock()
    llm = AsyncMock()
    engine = QueryEngine(graphiti, neo4j, llm)
    engine.search = AsyncMock()
    return engine


@pytest.mark.asyncio
async def test_fallback_not_triggered_without_point_in_time(query_engine):
    """No fallback when point_in_time is None."""
    primary = SearchResponse(
        query=SearchQuery(query="test"),
        results=[SearchResult(id="r-1", content="fact 1")],
        total_count=1,
    )
    query_engine.search.return_value = primary

    result = await query_engine.search_with_fallback(query="test")

    assert query_engine.search.call_count == 1
    assert result.results == primary.results


@pytest.mark.asyncio
async def test_fallback_not_triggered_with_enough_results(query_engine):
    """No fallback when >=5 results found."""
    results = [SearchResult(id=f"r-{i}", content=f"fact {i}") for i in range(5)]
    primary = SearchResponse(
        query=SearchQuery(query="test"),
        results=results,
        total_count=5,
    )
    query_engine.search.return_value = primary

    pit = datetime(2023, 12, 31, tzinfo=UTC)
    result = await query_engine.search_with_fallback(query="test", point_in_time=pit)

    assert query_engine.search.call_count == 1
    assert len(result.results) == 5


@pytest.mark.asyncio
async def test_fallback_triggered_on_few_results(query_engine):
    """Fallback triggered when point_in_time set and <5 results."""
    pit = datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC)

    primary = SearchResponse(
        query=SearchQuery(query="test"),
        results=[
            SearchResult(
                id="r-1",
                content="Microsoft invested $1B",
                temporal=TemporalMetadata(valid_at=datetime(2023, 1, 15, tzinfo=UTC)),
            ),
        ],
        total_count=1,
    )
    broad = SearchResponse(
        query=SearchQuery(query="test"),
        results=[
            SearchResult(
                id="r-1",
                content="Microsoft invested $1B",
                temporal=TemporalMetadata(valid_at=datetime(2023, 1, 15, tzinfo=UTC)),
            ),
            SearchResult(
                id="r-2",
                content="OpenAI valued at $29B",
                temporal=TemporalMetadata(valid_at=datetime(2023, 6, 1, tzinfo=UTC)),
            ),
        ],
        total_count=2,
    )
    query_engine.search.side_effect = [primary, broad]

    result = await query_engine.search_with_fallback(query="test", point_in_time=pit)

    assert query_engine.search.call_count == 2
    assert len(result.results) == 2
    ids = {r.id for r in result.results}
    assert ids == {"r-1", "r-2"}


@pytest.mark.asyncio
async def test_fallback_filters_future_facts(query_engine):
    """Broad results with valid_at > point_in_time are excluded."""
    pit = datetime(2023, 6, 1, tzinfo=UTC)

    primary = SearchResponse(
        query=SearchQuery(query="test"),
        results=[
            SearchResult(
                id="r-1",
                content="early fact",
                temporal=TemporalMetadata(valid_at=datetime(2023, 1, 1, tzinfo=UTC)),
            ),
        ],
        total_count=1,
    )
    broad = SearchResponse(
        query=SearchQuery(query="test"),
        results=[
            SearchResult(
                id="r-2",
                content="future fact",
                temporal=TemporalMetadata(valid_at=datetime(2024, 1, 1, tzinfo=UTC)),
            ),
            SearchResult(
                id="r-3",
                content="past fact",
                temporal=TemporalMetadata(valid_at=datetime(2023, 3, 1, tzinfo=UTC)),
            ),
        ],
        total_count=2,
    )
    query_engine.search.side_effect = [primary, broad]

    result = await query_engine.search_with_fallback(query="test", point_in_time=pit)

    ids = {r.id for r in result.results}
    assert "r-1" in ids
    assert "r-3" in ids
    assert "r-2" not in ids  # future fact excluded


@pytest.mark.asyncio
async def test_fallback_includes_results_without_temporal(query_engine):
    """Broad results without temporal metadata are included."""
    pit = datetime(2023, 12, 31, tzinfo=UTC)

    primary = SearchResponse(
        query=SearchQuery(query="test"),
        results=[SearchResult(id="r-1", content="fact 1")],
        total_count=1,
    )
    broad = SearchResponse(
        query=SearchQuery(query="test"),
        results=[
            SearchResult(id="r-2", content="no temporal"),
        ],
        total_count=1,
    )
    query_engine.search.side_effect = [primary, broad]

    result = await query_engine.search_with_fallback(query="test", point_in_time=pit)

    ids = {r.id for r in result.results}
    assert "r-2" in ids


@pytest.mark.asyncio
async def test_fallback_deduplicates_by_id(query_engine):
    """Duplicate IDs from broad search are not added twice."""
    pit = datetime(2023, 12, 31, tzinfo=UTC)

    primary = SearchResponse(
        query=SearchQuery(query="test"),
        results=[SearchResult(id="r-1", content="fact 1")],
        total_count=1,
    )
    broad = SearchResponse(
        query=SearchQuery(query="test"),
        results=[
            SearchResult(id="r-1", content="fact 1 duplicate"),
            SearchResult(id="r-2", content="fact 2"),
        ],
        total_count=2,
    )
    query_engine.search.side_effect = [primary, broad]

    result = await query_engine.search_with_fallback(query="test", point_in_time=pit)

    ids = [r.id for r in result.results]
    assert ids.count("r-1") == 1
    assert "r-2" in ids


@pytest.mark.asyncio
async def test_fallback_respects_limit(query_engine):
    """Results are truncated to the specified limit."""
    pit = datetime(2023, 12, 31, tzinfo=UTC)

    primary = SearchResponse(
        query=SearchQuery(query="test"),
        results=[SearchResult(id="r-1", content="fact 1")],
        total_count=1,
    )
    broad = SearchResponse(
        query=SearchQuery(query="test"),
        results=[SearchResult(id=f"r-{i}", content=f"fact {i}") for i in range(2, 20)],
        total_count=18,
    )
    query_engine.search.side_effect = [primary, broad]

    result = await query_engine.search_with_fallback(
        query="test", point_in_time=pit, limit=5
    )

    assert len(result.results) <= 5


@pytest.mark.asyncio
async def test_fallback_passes_intent_to_primary_search(query_engine):
    """Custom intent is forwarded to the primary search call."""
    primary = SearchResponse(
        query=SearchQuery(query="test"),
        results=[SearchResult(id=f"r-{i}", content=f"f{i}") for i in range(5)],
        total_count=5,
    )
    query_engine.search.return_value = primary

    await query_engine.search_with_fallback(
        query="test", intent=IntentType.TEMPORAL
    )

    call_args = query_engine.search.call_args[0][0]
    assert call_args.intent == IntentType.TEMPORAL
