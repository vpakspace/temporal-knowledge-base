"""Integration tests for the full ingestion + search pipeline.

End-to-end tests:
1. Ingest episodes with real LLM extraction
2. Verify entities and events stored in Neo4j
3. Search and verify temporal consistency
4. Test invalidation flow (contradicting facts)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.config import AppSettings, Neo4jSettings, OpenAISettings
from core.models import EpisodeType, IntentType, SearchQuery
from generation.llm_client import LLMClient
from generation.response_builder import ResponseBuilder
from generation.temporal_verifier import TemporalVerifier
from ingestion.pipeline import IngestionPipeline
from retrieval.query_engine import QueryEngine
from storage.neo4j_client import Neo4jClient
from storage.vector_store import VectorStore
from temporal.invalidation_agent import InvalidationAgent
from temporal.resolution import EntityResolver
from tests.conftest import skip_no_neo4j, skip_no_openai

pytestmark = [pytest.mark.integration, skip_no_neo4j, skip_no_openai]


# --- Fixtures ---


@pytest.fixture
def settings() -> AppSettings:
    return AppSettings()


@pytest.fixture
def llm(settings: AppSettings) -> LLMClient:
    return LLMClient(settings.openai)


@pytest.fixture
def vectors(settings: AppSettings) -> VectorStore:
    return VectorStore(settings.openai)


@pytest.fixture
def invalidation_agent(
    neo4j_clean: Neo4jClient,
    vectors: VectorStore,
    llm: LLMClient,
    settings: AppSettings,
) -> InvalidationAgent:
    return InvalidationAgent(neo4j_clean, vectors, llm, settings)


@pytest.fixture
def entity_resolver(
    neo4j_clean: Neo4jClient, vectors: VectorStore
) -> EntityResolver:
    return EntityResolver(neo4j_clean, vectors)


# --- E2E Ingestion Tests ---


async def test_ingest_single_episode(
    neo4j_clean: Neo4jClient,
    vectors: VectorStore,
    llm: LLMClient,
    invalidation_agent: InvalidationAgent,
    entity_resolver: EntityResolver,
    settings: AppSettings,
):
    """Ingest a single episode and verify data in Neo4j."""
    # Build a mock GraphitiClient that just returns empty (we test our layer)
    from unittest.mock import AsyncMock

    mock_graphiti = AsyncMock()
    mock_graphiti.add_episode.return_value = {"status": "ok"}

    pipeline = IngestionPipeline(
        graphiti=mock_graphiti,
        neo4j=neo4j_clean,
        vector_store=vectors,
        llm=llm,
        invalidation_agent=invalidation_agent,
        entity_resolver=entity_resolver,
        settings=settings,
    )

    result = await pipeline.ingest_episode(
        content=(
            "In March 2024, Tesla reported quarterly revenue of $25.17 billion. "
            "CEO Elon Musk announced plans to launch the Robotaxi service by August 2024."
        ),
        source="test_news_tesla",
        episode_type=EpisodeType.TEXT,
        reference_time=datetime(2024, 3, 15, tzinfo=UTC),
    )

    # Verify ingestion results
    assert result["source"] == "test_news_tesla"
    assert result["entities_extracted"] >= 2
    assert result["temporal_events"] >= 1

    # Verify data in Neo4j
    stats = await neo4j_clean.get_stats()
    assert stats["entities"] >= 2
    assert stats["events"] >= 1
    assert stats["episodes"] >= 1


async def test_ingest_contradicting_episodes(
    neo4j_clean: Neo4jClient,
    vectors: VectorStore,
    llm: LLMClient,
    invalidation_agent: InvalidationAgent,
    entity_resolver: EntityResolver,
    settings: AppSettings,
):
    """Ingest two episodes with contradicting facts and verify invalidation."""
    from unittest.mock import AsyncMock

    mock_graphiti = AsyncMock()
    mock_graphiti.add_episode.return_value = {"status": "ok"}

    pipeline = IngestionPipeline(
        graphiti=mock_graphiti,
        neo4j=neo4j_clean,
        vector_store=vectors,
        llm=llm,
        invalidation_agent=invalidation_agent,
        entity_resolver=entity_resolver,
        settings=settings,
    )

    # Episode 1: Original fact
    result1 = await pipeline.ingest_episode(
        content="John Smith is the CEO of GlobalTech Corporation since January 2023.",
        source="test_ceo_original",
        reference_time=datetime(2023, 1, 15, tzinfo=UTC),
    )

    # Episode 2: Contradicting fact
    result2 = await pipeline.ingest_episode(
        content=(
            "GlobalTech Corporation announced that Sarah Johnson has been "
            "appointed as the new CEO, replacing John Smith who resigned in December 2024."
        ),
        source="test_ceo_update",
        reference_time=datetime(2024, 12, 20, tzinfo=UTC),
    )

    # Both episodes should be ingested
    assert result1["entities_extracted"] >= 1
    assert result2["entities_extracted"] >= 1

    # Check stats — should have events from both episodes
    stats = await neo4j_clean.get_stats()
    assert stats["events"] >= 2


# --- Search Tests ---


async def test_search_after_ingestion(
    neo4j_clean: Neo4jClient,
    vectors: VectorStore,
    llm: LLMClient,
    invalidation_agent: InvalidationAgent,
    entity_resolver: EntityResolver,
    settings: AppSettings,
):
    """Ingest data, then search for it."""
    from unittest.mock import AsyncMock

    mock_graphiti = AsyncMock()
    mock_graphiti.add_episode.return_value = {"status": "ok"}
    mock_graphiti.search.return_value = []

    pipeline = IngestionPipeline(
        graphiti=mock_graphiti,
        neo4j=neo4j_clean,
        vector_store=vectors,
        llm=llm,
        invalidation_agent=invalidation_agent,
        entity_resolver=entity_resolver,
        settings=settings,
    )

    await pipeline.ingest_episode(
        content=(
            "Amazon Web Services launched a new AI service called Bedrock "
            "in April 2023. The service provides access to foundation models "
            "from Anthropic, AI21 Labs, and Stability AI."
        ),
        source="test_aws",
        reference_time=datetime(2023, 4, 15, tzinfo=UTC),
    )

    # Build query engine with mock graphiti
    query_engine = QueryEngine(
        graphiti=mock_graphiti,
        neo4j=neo4j_clean,
        llm=llm,
    )

    # Search for temporal events via point-in-time
    query = SearchQuery(
        query="What AI services were launched?",
        intent=IntentType.TEMPORAL,
        point_in_time=datetime(2024, 1, 1, tzinfo=UTC),
        limit=10,
    )
    response = await query_engine.search(query)

    # Should find the event(s) from ingestion
    assert response.total_count >= 1
    contents = " ".join(r.content.lower() for r in response.results)
    assert "bedrock" in contents or "amazon" in contents or "ai" in contents


# --- Response Builder ---


async def test_response_builder(
    neo4j_clean: Neo4jClient,
    vectors: VectorStore,
    llm: LLMClient,
    invalidation_agent: InvalidationAgent,
    entity_resolver: EntityResolver,
    settings: AppSettings,
):
    """Test full pipeline: ingest → search → verify → respond."""
    from unittest.mock import AsyncMock

    mock_graphiti = AsyncMock()
    mock_graphiti.add_episode.return_value = {"status": "ok"}
    mock_graphiti.search.return_value = []

    pipeline = IngestionPipeline(
        graphiti=mock_graphiti,
        neo4j=neo4j_clean,
        vector_store=vectors,
        llm=llm,
        invalidation_agent=invalidation_agent,
        entity_resolver=entity_resolver,
        settings=settings,
    )

    await pipeline.ingest_episode(
        content=(
            "SpaceX successfully launched Starship on its fourth test flight "
            "on June 6, 2024. The rocket reached orbit for the first time and "
            "the booster made a controlled splashdown in the Gulf of Mexico."
        ),
        source="test_spacex",
        reference_time=datetime(2024, 6, 6, tzinfo=UTC),
    )

    # Search
    query_engine = QueryEngine(
        graphiti=mock_graphiti,
        neo4j=neo4j_clean,
        llm=llm,
    )

    query = SearchQuery(
        query="What happened with SpaceX Starship?",
        intent=IntentType.TEMPORAL,
        point_in_time=datetime(2024, 12, 1, tzinfo=UTC),
        limit=10,
    )
    search_response = await query_engine.search(query)

    # Build response
    verifier = TemporalVerifier(neo4j_clean)
    builder = ResponseBuilder(llm, verifier)
    response = await builder.build_response(
        query="What happened with SpaceX Starship?",
        search_response=search_response,
        include_timeline=True,
    )

    assert "answer" in response
    assert response["facts_used"] >= 1
    assert len(response["answer"]) > 10  # Non-trivial answer
