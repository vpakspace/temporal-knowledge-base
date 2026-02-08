"""Unit tests for MCP server _impl functions.

All external dependencies (Neo4j, OpenAI, Graphiti) are mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mcp_server
from core.models import (
    IntentType,
    SearchQuery,
    SearchResponse,
    SearchResult,
    TemporalMetadata,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test."""
    mcp_server._state = None
    yield
    mcp_server._state = None


@pytest.fixture
def mock_state():
    """Create a mock _State with all dependencies mocked."""
    state = mcp_server._State()
    state.neo4j = AsyncMock()
    state.graphiti = AsyncMock()
    state.vector_store = AsyncMock()
    state.llm = AsyncMock()
    state.pipeline = AsyncMock()
    state.query_engine = AsyncMock()
    state.response_builder = AsyncMock()
    state.settings = MagicMock()
    return state


@pytest.fixture
def patch_get_state(mock_state):
    """Patch get_state to return mock state without real initialization."""

    async def _get_state():
        return mock_state

    with patch.object(mcp_server, "get_state", _get_state):
        yield mock_state


# --- tkb_ingest ---


@pytest.mark.asyncio
async def test_ingest_basic(patch_get_state):
    """Test basic episode ingestion."""
    patch_get_state.pipeline.ingest_episode.return_value = {
        "episode_id": "ep-1",
        "source": "test",
        "chunks": 1,
        "entities_extracted": 2,
        "entities_resolved": 2,
        "temporal_events": 3,
        "relationships": 1,
        "invalidated": 0,
        "graphiti_result": {},
    }

    result = await mcp_server._tkb_ingest_impl(
        content="Alice joined Acme Corp in 2024.",
        source="test-doc",
    )

    assert result["episode_id"] == "ep-1"
    assert result["entities_extracted"] == 2
    patch_get_state.pipeline.ingest_episode.assert_called_once()
    call_kwargs = patch_get_state.pipeline.ingest_episode.call_args.kwargs
    assert call_kwargs["content"] == "Alice joined Acme Corp in 2024."
    assert call_kwargs["source"] == "test-doc"


@pytest.mark.asyncio
async def test_ingest_with_reference_time(patch_get_state):
    """Test ingestion with explicit reference time."""
    patch_get_state.pipeline.ingest_episode.return_value = {"episode_id": "ep-2"}

    await mcp_server._tkb_ingest_impl(
        content="Revenue update",
        source="report",
        reference_time="2024-06-15T10:00:00+00:00",
    )

    call_kwargs = patch_get_state.pipeline.ingest_episode.call_args.kwargs
    assert call_kwargs["reference_time"] is not None
    assert call_kwargs["reference_time"].year == 2024
    assert call_kwargs["reference_time"].month == 6


@pytest.mark.asyncio
async def test_ingest_invalid_episode_type(patch_get_state):
    """Test that invalid episode_type falls back to TEXT."""
    patch_get_state.pipeline.ingest_episode.return_value = {"episode_id": "ep-3"}

    await mcp_server._tkb_ingest_impl(
        content="Some content",
        episode_type="invalid_type",
    )

    call_kwargs = patch_get_state.pipeline.ingest_episode.call_args.kwargs
    assert call_kwargs["episode_type"].value == "text"


@pytest.mark.asyncio
async def test_ingest_with_group_id(patch_get_state):
    """Test ingestion with group_id."""
    patch_get_state.pipeline.ingest_episode.return_value = {"episode_id": "ep-4"}

    await mcp_server._tkb_ingest_impl(
        content="Content",
        group_id="project-alpha",
    )

    call_kwargs = patch_get_state.pipeline.ingest_episode.call_args.kwargs
    assert call_kwargs["group_id"] == "project-alpha"


# --- tkb_search ---


@pytest.mark.asyncio
async def test_search_basic(patch_get_state):
    """Test basic search."""
    patch_get_state.query_engine.search.return_value = SearchResponse(
        query=SearchQuery(query="CEO of Acme"),
        results=[
            SearchResult(
                id="r-1",
                content="Alice is CEO of Acme Corp",
                result_type="relationship",
                temporal=TemporalMetadata(
                    valid_at=datetime(2024, 1, 1, tzinfo=UTC),
                    is_current=True,
                ),
            ),
        ],
        total_count=1,
    )

    result = await mcp_server._tkb_search_impl(query="CEO of Acme")

    assert result["query"] == "CEO of Acme"
    assert result["total_count"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["content"] == "Alice is CEO of Acme Corp"
    assert result["results"][0]["is_current"] is True


@pytest.mark.asyncio
async def test_search_with_intent(patch_get_state):
    """Test search with explicit intent."""
    patch_get_state.query_engine.search.return_value = SearchResponse(
        query=SearchQuery(query="test", intent=IntentType.TEMPORAL),
        results=[],
        total_count=0,
    )

    result = await mcp_server._tkb_search_impl(query="test", intent="temporal")

    call_args = patch_get_state.query_engine.search.call_args[0][0]
    assert call_args.intent == IntentType.TEMPORAL
    assert result["total_count"] == 0


@pytest.mark.asyncio
async def test_search_with_point_in_time(patch_get_state):
    """Test search with point-in-time snapshot."""
    patch_get_state.query_engine.search.return_value = SearchResponse(
        query=SearchQuery(query="test"),
        results=[],
        total_count=0,
    )

    await mcp_server._tkb_search_impl(
        query="test",
        point_in_time="2023-12-31T23:59:59+00:00",
    )

    call_args = patch_get_state.query_engine.search.call_args[0][0]
    assert call_args.point_in_time is not None
    assert call_args.point_in_time.year == 2023


@pytest.mark.asyncio
async def test_search_invalid_intent_fallback(patch_get_state):
    """Test that invalid intent falls back to hybrid."""
    patch_get_state.query_engine.search.return_value = SearchResponse(
        query=SearchQuery(query="test"),
        results=[],
        total_count=0,
    )

    await mcp_server._tkb_search_impl(query="test", intent="invalid")

    call_args = patch_get_state.query_engine.search.call_args[0][0]
    assert call_args.intent == IntentType.HYBRID


# --- tkb_ask ---


# --- _extract_temporal_hint ---


class TestExtractTemporalHint:
    """Tests for temporal hint extraction from questions."""

    def test_standalone_year(self):
        """Extract year from '2023'."""
        result = mcp_server._extract_temporal_hint("что случилось в 2023 году")
        assert result is not None
        assert result.year == 2023
        assert result.month == 12
        assert result.day == 31

    def test_english_year(self):
        """Extract year from 'in 2024'."""
        result = mcp_server._extract_temporal_hint("what happened in 2024")
        assert result is not None
        assert result.year == 2024

    def test_russian_month_year(self):
        """Extract month+year from 'в январе 2024'."""
        result = mcp_server._extract_temporal_hint("сколько в январе 2024")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1

    def test_russian_month_year_december(self):
        """Extract month+year from 'в декабре 2023'."""
        result = mcp_server._extract_temporal_hint("что было в декабре 2023")
        assert result is not None
        assert result.year == 2023
        assert result.month == 12

    def test_english_month_year(self):
        """Extract month+year from 'January 2025'."""
        result = mcp_server._extract_temporal_hint("investment in January 2025")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1

    def test_year_range(self):
        """Extract end of range from '2023-2024'."""
        result = mcp_server._extract_temporal_hint("события 2023-2024")
        assert result is not None
        assert result.year == 2024
        assert result.month == 12

    def test_no_temporal_hint(self):
        """No date in question returns None."""
        result = mcp_server._extract_temporal_hint("кто является CEO")
        assert result is None

    def test_timezone_aware(self):
        """Extracted datetime should be timezone-aware (UTC)."""
        result = mcp_server._extract_temporal_hint("in 2023")
        assert result is not None
        assert result.tzinfo is not None


# --- tkb_ask ---


@pytest.mark.asyncio
async def test_ask_basic(patch_get_state):
    """Test ask with LLM response."""
    patch_get_state.query_engine.search_with_fallback.return_value = SearchResponse(
        query=SearchQuery(query="Who is CEO?"),
        results=[
            SearchResult(id="r-1", content="Alice is CEO"),
        ],
        total_count=1,
    )
    patch_get_state.response_builder.build_response.return_value = {
        "answer": "Alice is the CEO of Acme Corp.",
        "facts_used": 1,
        "sources": [{"id": "r-1", "content": "Alice is CEO", "valid_at": None}],
        "timeline": None,
    }

    result = await mcp_server._tkb_ask_impl(question="Who is CEO?")

    assert result["answer"] == "Alice is the CEO of Acme Corp."
    assert result["facts_used"] == 1


@pytest.mark.asyncio
async def test_ask_with_timeline(patch_get_state):
    """Test ask with timeline included."""
    patch_get_state.query_engine.search_with_fallback.return_value = SearchResponse(
        query=SearchQuery(query="CEO history"),
        results=[],
        total_count=0,
    )
    patch_get_state.response_builder.build_response.return_value = {
        "answer": "No information available.",
        "facts_used": 0,
        "sources": [],
        "timeline": [],
    }

    result = await mcp_server._tkb_ask_impl(
        question="CEO history",
        include_timeline=True,
    )

    call_kwargs = patch_get_state.response_builder.build_response.call_args.kwargs
    assert call_kwargs["include_timeline"] is True


@pytest.mark.asyncio
async def test_ask_extracts_temporal_hint(patch_get_state):
    """Test that ask with a year in the question passes point_in_time to search_with_fallback."""
    patch_get_state.query_engine.search_with_fallback.return_value = SearchResponse(
        query=SearchQuery(query="investment in 2023"),
        results=[
            SearchResult(id="r-1", content="Microsoft invested $1B"),
        ],
        total_count=1,
    )
    patch_get_state.response_builder.build_response.return_value = {
        "answer": "Microsoft invested $1B in OpenAI in 2023.",
        "facts_used": 1,
        "sources": [],
        "timeline": None,
    }

    await mcp_server._tkb_ask_impl(question="сколько Microsoft инвестировал в 2023 году")

    call_kwargs = patch_get_state.query_engine.search_with_fallback.call_args.kwargs
    assert call_kwargs["point_in_time"] is not None
    assert call_kwargs["point_in_time"].year == 2023


@pytest.mark.asyncio
async def test_ask_no_temporal_hint_no_point_in_time(patch_get_state):
    """Test that ask without temporal reference passes point_in_time=None."""
    patch_get_state.query_engine.search_with_fallback.return_value = SearchResponse(
        query=SearchQuery(query="Who is CEO?"),
        results=[
            SearchResult(id="r-1", content="Alice is CEO"),
        ],
        total_count=1,
    )
    patch_get_state.response_builder.build_response.return_value = {
        "answer": "Alice.",
        "facts_used": 1,
        "sources": [],
        "timeline": None,
    }

    await mcp_server._tkb_ask_impl(question="кто является CEO OpenAI")

    call_kwargs = patch_get_state.query_engine.search_with_fallback.call_args.kwargs
    assert call_kwargs["point_in_time"] is None


# --- tkb_timeline ---


@pytest.mark.asyncio
async def test_timeline(patch_get_state):
    """Test entity timeline retrieval."""
    patch_get_state.neo4j.get_entity_timeline.return_value = [
        {
            "id": "ev-1",
            "statement": "Alice joined Acme",
            "valid_at": "2020-01-01",
            "is_current": False,
            "superseded_by": "ev-2",
        },
        {
            "id": "ev-2",
            "statement": "Alice became CEO of Acme",
            "valid_at": "2024-01-01",
            "is_current": True,
            "superseded_by": None,
        },
    ]

    result = await mcp_server._tkb_timeline_impl(entity_id="entity-alice")

    assert result["entity_id"] == "entity-alice"
    assert result["total"] == 2
    assert len(result["events"]) == 2
    patch_get_state.neo4j.get_entity_timeline.assert_called_once_with("entity-alice")


# --- tkb_evolution ---


@pytest.mark.asyncio
async def test_evolution(patch_get_state):
    """Test SUPERSEDED_BY chain retrieval."""
    patch_get_state.neo4j.get_supersession_chain.return_value = [
        {
            "id": "ev-1",
            "statement": "Revenue was $1M",
            "valid_at": "2022-01-01",
            "is_current": False,
        },
        {
            "id": "ev-2",
            "statement": "Revenue grew to $5M",
            "valid_at": "2023-01-01",
            "is_current": False,
        },
        {
            "id": "ev-3",
            "statement": "Revenue reached $10M",
            "valid_at": "2024-01-01",
            "is_current": True,
        },
    ]

    result = await mcp_server._tkb_evolution_impl(event_id="ev-1")

    assert result["event_id"] == "ev-1"
    assert result["total"] == 3
    assert result["chain"][-1]["is_current"] is True


# --- tkb_stats ---


@pytest.mark.asyncio
async def test_stats(patch_get_state):
    """Test graph statistics."""
    patch_get_state.neo4j.get_stats.return_value = {
        "entities": 42,
        "events": 150,
        "current_events": 120,
        "episodes": 15,
    }

    result = await mcp_server._tkb_stats_impl()

    assert result["entities"] == 42
    assert result["events"] == 150
    assert result["current_events"] == 120
    assert result["episodes"] == 15


# --- State initialization ---


@pytest.mark.asyncio
async def test_state_class_initial():
    """Test _State class has None attributes initially."""
    state = mcp_server._State()
    assert state.neo4j is None
    assert state.pipeline is None
    assert state.query_engine is None
    assert state.response_builder is None
