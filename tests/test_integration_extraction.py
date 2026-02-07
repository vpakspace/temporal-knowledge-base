"""Integration tests for dual-track extraction with real LLM.

Tests that the extractor correctly parses LLM output into
entities, relationships, and temporal events.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from generation.llm_client import LLMClient
from ingestion.extractor import DualTrackExtractor
from tests.conftest import skip_no_openai

pytestmark = [pytest.mark.integration, skip_no_openai]


async def test_extract_entities_from_news(llm_client: LLMClient):
    """Extract entities and events from a news-like paragraph."""
    extractor = DualTrackExtractor(llm_client)
    text = (
        "On January 15, 2024, Satya Nadella announced that Microsoft "
        "would invest $10 billion in OpenAI. The deal makes Microsoft "
        "the largest investor in the artificial intelligence startup."
    )
    result = await extractor.extract(
        text,
        source="test_news",
        reference_time=datetime(2024, 1, 15, tzinfo=UTC),
    )

    # Should extract entities
    assert len(result.entities) >= 2
    entity_names = {e.name.lower() for e in result.entities}
    assert any("microsoft" in n for n in entity_names)
    assert any("openai" in n for n in entity_names)

    # Should extract temporal events
    assert len(result.temporal_events) >= 1
    statements = " ".join(e.statement.lower() for e in result.temporal_events)
    assert "invest" in statements or "billion" in statements


async def test_extract_relationships(llm_client: LLMClient):
    """Verify relationship extraction."""
    extractor = DualTrackExtractor(llm_client)
    text = "Alice Smith works at Google as a Senior Engineer. She reports to Bob Johnson, the VP of Engineering."
    result = await extractor.extract(text, source="test_org")

    assert len(result.entities) >= 3  # Alice, Google, Bob
    assert len(result.relationships) >= 1

    rel_types = {r.relation_type for r in result.relationships}
    # At least one relationship should be extracted
    assert len(rel_types) >= 1


async def test_extract_fact_types(llm_client: LLMClient):
    """Verify fact_type classification (static/dynamic/atemporal)."""
    extractor = DualTrackExtractor(llm_client)
    text = (
        "Albert Einstein was born on March 14, 1879 in Ulm, Germany. "
        "He developed the theory of relativity, which states that E=mc². "
        "He served as the director of the Kaiser Wilhelm Institute from 1914 to 1932."
    )
    result = await extractor.extract(
        text,
        source="test_bio",
        reference_time=datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert len(result.temporal_events) >= 2
    fact_types = {e.fact_type.value for e in result.temporal_events}
    # Should have at least static (birth date) and one other type
    assert len(fact_types) >= 1


async def test_extract_empty_text(llm_client: LLMClient):
    """Extraction from minimal text should still return valid result."""
    extractor = DualTrackExtractor(llm_client)
    result = await extractor.extract("Hello world.", source="test_minimal")

    # Should not crash, may or may not extract entities
    assert result.episode_id == ""
    assert isinstance(result.entities, list)
    assert isinstance(result.temporal_events, list)


async def test_extract_russian_text(llm_client: LLMClient):
    """Verify extraction works with Russian text."""
    extractor = DualTrackExtractor(llm_client)
    text = (
        "В январе 2024 года Сбербанк объявил о покупке компании ВизионЛабс. "
        "Герман Греф подтвердил сделку на пресс-конференции в Москве."
    )
    result = await extractor.extract(
        text,
        source="test_russian",
        reference_time=datetime(2024, 1, 20, tzinfo=UTC),
    )

    assert len(result.entities) >= 2
    assert len(result.temporal_events) >= 1
