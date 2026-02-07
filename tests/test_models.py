"""Tests for core data models."""

from datetime import UTC, datetime

from core.models import (
    DriftSeverity,
    Entity,
    Episode,
    EpisodeType,
    ExtractionResult,
    FactType,
    IntentType,
    InvalidationCandidate,
    InvalidationMode,
    InvalidationResult,
    Relationship,
    SearchQuery,
    SearchResponse,
    SearchResult,
    TemporalEvent,
    TemporalMetadata,
)


def test_entity_creation():
    entity = Entity(name="IBM", entity_type="Organization")
    assert entity.name == "IBM"
    assert entity.entity_type == "Organization"
    assert entity.id  # UUID generated
    assert entity.temporal.is_current is True
    assert entity.invalidation_mode == InvalidationMode.REPLACE


def test_entity_display_name():
    entity = Entity(name="IBM Corp", entity_type="Organization", canonical_name="IBM")
    assert entity.display_name == "IBM"

    entity2 = Entity(name="IBM Corp", entity_type="Organization")
    assert entity2.display_name == "IBM Corp"


def test_temporal_metadata_defaults():
    meta = TemporalMetadata()
    assert meta.valid_at is None
    assert meta.invalid_at is None
    assert meta.is_current is True
    assert meta.created_at is not None


def test_temporal_event_creation():
    event = TemporalEvent(
        statement="Lisa Su became CEO of AMD on October 8, 2014",
        fact_type=FactType.DYNAMIC,
        entity_ids=["entity-1", "entity-2"],
        temporal=TemporalMetadata(
            valid_at=datetime(2014, 10, 8, tzinfo=UTC),
        ),
    )
    assert event.statement.startswith("Lisa Su")
    assert event.fact_type == FactType.DYNAMIC
    assert len(event.entity_ids) == 2
    assert event.temporal.valid_at.year == 2014


def test_episode_types():
    assert EpisodeType.TEXT.value == "text"
    assert EpisodeType.JSON.value == "json"
    assert EpisodeType.CHAT.value == "chat"
    assert EpisodeType.DOCUMENT.value == "document"


def test_episode_creation():
    ep = Episode(content="test content", source="test.txt")
    assert ep.content == "test content"
    assert ep.source == "test.txt"
    assert ep.episode_type == EpisodeType.TEXT


def test_relationship_creation():
    rel = Relationship(
        source_id="entity-1",
        target_id="entity-2",
        relation_type="CEO_OF",
        fact_type=FactType.DYNAMIC,
    )
    assert rel.relation_type == "CEO_OF"
    assert rel.fact_type == FactType.DYNAMIC


def test_extraction_result():
    result = ExtractionResult(
        episode_id="ep-1",
        entities=[Entity(name="IBM", entity_type="Organization")],
        temporal_events=[
            TemporalEvent(statement="IBM was founded in 1911", fact_type=FactType.STATIC)
        ],
    )
    assert len(result.entities) == 1
    assert len(result.temporal_events) == 1


def test_invalidation_candidate():
    existing = TemporalEvent(statement="John is CEO of Acme")
    new = TemporalEvent(statement="Jane is CEO of Acme")
    candidate = InvalidationCandidate(
        existing_event=existing,
        new_event=new,
        shared_entity_ids=["acme-id"],
        semantic_similarity=0.85,
        llm_confirmed=True,
    )
    assert candidate.llm_confirmed is True
    assert candidate.semantic_similarity == 0.85


def test_invalidation_result():
    result = InvalidationResult(
        invalidated_events=["ev-1"],
        supersede_pairs=[("ev-1", "ev-2")],
        severity=DriftSeverity.CRITICAL,
    )
    assert len(result.invalidated_events) == 1
    assert result.severity == DriftSeverity.CRITICAL


def test_search_query():
    q = SearchQuery(
        query="Who is CEO of AMD?",
        intent=IntentType.STRUCTURAL,
        limit=5,
    )
    assert q.intent == IntentType.STRUCTURAL
    assert q.limit == 5
    assert q.include_superseded is False


def test_search_result():
    r = SearchResult(
        id="res-1",
        content="Lisa Su is CEO of AMD",
        score=0.95,
        result_type="relationship",
    )
    assert r.score == 0.95


def test_search_response():
    resp = SearchResponse(
        query=SearchQuery(query="test"),
        results=[SearchResult(id="1", content="fact")],
        total_count=1,
    )
    assert resp.total_count == 1
    assert len(resp.results) == 1


def test_intent_types():
    assert IntentType.STRUCTURAL.value == "structural"
    assert IntentType.TEMPORAL.value == "temporal"
    assert IntentType.HYBRID.value == "hybrid"


def test_fact_types():
    assert FactType.STATIC.value == "static"
    assert FactType.DYNAMIC.value == "dynamic"
    assert FactType.ATEMPORAL.value == "atemporal"
