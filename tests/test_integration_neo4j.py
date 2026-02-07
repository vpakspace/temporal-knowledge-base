"""Integration tests for Neo4j client — real database operations.

Tests the bi-temporal CRUD, point-in-time queries, entity timeline,
SUPERSEDED_BY chains, and full-text search.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.models import (
    Entity,
    Episode,
    EpisodeType,
    FactType,
    Relationship,
    TemporalEvent,
    TemporalMetadata,
)
from storage.neo4j_client import Neo4jClient
from tests.conftest import skip_no_neo4j

pytestmark = [pytest.mark.integration, skip_no_neo4j]


# --- Entity CRUD ---


async def test_create_and_retrieve_entity(neo4j_client: Neo4jClient):
    entity = Entity(
        id="test-entity-1",
        name="Acme Corporation",
        entity_type="Organization",
        canonical_name="acme",
        temporal=TemporalMetadata(
            valid_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
    )
    result_id = await neo4j_client.create_entity(entity)
    assert result_id == "test-entity-1"

    # Verify via full-text search
    found = await neo4j_client.find_entities_by_name("Acme", limit=3)
    assert len(found) >= 1
    assert any(r["id"] == "test-entity-1" for r in found)


async def test_entity_merge_on_same_id(neo4j_client: Neo4jClient):
    """MERGE should update existing entity, not create duplicate."""
    entity_v1 = Entity(
        id="test-entity-merge",
        name="OldName Corp",
        entity_type="Organization",
    )
    entity_v2 = Entity(
        id="test-entity-merge",
        name="NewName Corp",
        entity_type="Organization",
    )
    await neo4j_client.create_entity(entity_v1)
    await neo4j_client.create_entity(entity_v2)

    found = await neo4j_client.find_entities_by_name("NewName", limit=5)
    assert any(r["id"] == "test-entity-merge" for r in found)


# --- Relationship CRUD ---


async def test_create_relationship(neo4j_client: Neo4jClient):
    src = Entity(id="test-rel-src", name="Alice", entity_type="Person")
    tgt = Entity(id="test-rel-tgt", name="Acme Inc", entity_type="Organization")
    await neo4j_client.create_entity(src)
    await neo4j_client.create_entity(tgt)

    rel = Relationship(
        id="test-rel-1",
        source_id="test-rel-src",
        target_id="test-rel-tgt",
        relation_type="WORKS_FOR",
        fact_type=FactType.DYNAMIC,
        temporal=TemporalMetadata(
            valid_at=datetime(2024, 6, 1, tzinfo=UTC),
        ),
    )
    result_id = await neo4j_client.create_relationship(rel)
    assert result_id == "test-rel-1"


# --- Temporal Events ---


async def test_create_temporal_event(neo4j_client: Neo4jClient):
    event = TemporalEvent(
        id="test-event-1",
        statement="Alice became CEO of Acme Corporation in January 2024.",
        fact_type=FactType.DYNAMIC,
        entity_ids=["test-entity-1"],
        confidence=0.95,
        source="test",
        temporal=TemporalMetadata(
            valid_at=datetime(2024, 1, 15, tzinfo=UTC),
        ),
    )
    result_id = await neo4j_client.create_temporal_event(event)
    assert result_id == "test-event-1"


async def test_link_event_to_entities(neo4j_client: Neo4jClient):
    entity = Entity(id="test-link-ent", name="LinkTest Corp", entity_type="Organization")
    event = TemporalEvent(
        id="test-link-evt",
        statement="LinkTest Corp was founded in 2020.",
        entity_ids=["test-link-ent"],
        temporal=TemporalMetadata(valid_at=datetime(2020, 1, 1, tzinfo=UTC)),
    )
    await neo4j_client.create_entity(entity)
    await neo4j_client.create_temporal_event(event)
    await neo4j_client.link_event_to_entities("test-link-evt", ["test-link-ent"])

    # Verify via timeline
    timeline = await neo4j_client.get_entity_timeline("test-link-ent")
    assert len(timeline) >= 1
    assert any(r["id"] == "test-link-evt" for r in timeline)


# --- Supersession ---


async def test_supersede_event(neo4j_client: Neo4jClient):
    old_event = TemporalEvent(
        id="test-supersede-old",
        statement="Bob is CTO of TechCo.",
        fact_type=FactType.DYNAMIC,
        temporal=TemporalMetadata(valid_at=datetime(2023, 1, 1, tzinfo=UTC)),
    )
    new_event = TemporalEvent(
        id="test-supersede-new",
        statement="Charlie is CTO of TechCo (Bob resigned).",
        fact_type=FactType.DYNAMIC,
        temporal=TemporalMetadata(valid_at=datetime(2024, 6, 1, tzinfo=UTC)),
    )
    await neo4j_client.create_temporal_event(old_event)
    await neo4j_client.create_temporal_event(new_event)

    await neo4j_client.supersede_event("test-supersede-old", "test-supersede-new")

    # Verify chain
    chain = await neo4j_client.get_supersession_chain("test-supersede-old")
    assert len(chain) == 2
    assert chain[0]["id"] == "test-supersede-old"
    assert chain[0]["is_current"] is False
    assert chain[1]["id"] == "test-supersede-new"
    assert chain[1]["is_current"] is True


# --- Point-in-Time Queries ---


async def test_point_in_time_query(neo4j_clean: Neo4jClient):
    """Create events at different times, query at specific point."""
    neo4j = neo4j_clean

    ev1 = TemporalEvent(
        id="test-pit-1",
        statement="Company revenue was $10M.",
        temporal=TemporalMetadata(valid_at=datetime(2023, 1, 1, tzinfo=UTC)),
    )
    ev2 = TemporalEvent(
        id="test-pit-2",
        statement="Company revenue grew to $15M.",
        temporal=TemporalMetadata(valid_at=datetime(2024, 1, 1, tzinfo=UTC)),
    )
    ev3 = TemporalEvent(
        id="test-pit-3",
        statement="Company revenue reached $20M.",
        temporal=TemporalMetadata(valid_at=datetime(2025, 1, 1, tzinfo=UTC)),
    )
    await neo4j.create_temporal_event(ev1)
    await neo4j.create_temporal_event(ev2)
    await neo4j.create_temporal_event(ev3)

    # Query mid-2024: should see events 1 and 2 but not 3
    results = await neo4j.query_point_in_time(
        point=datetime(2024, 6, 1, tzinfo=UTC), limit=50
    )
    result_ids = {r["id"] for r in results}
    assert "test-pit-1" in result_ids
    assert "test-pit-2" in result_ids
    assert "test-pit-3" not in result_ids


# --- Entity Timeline ---


async def test_entity_timeline(neo4j_clean: Neo4jClient):
    neo4j = neo4j_clean

    entity = Entity(id="test-tl-ent", name="Timeline Corp", entity_type="Organization")
    await neo4j.create_entity(entity)

    for i, year in enumerate([2020, 2022, 2024]):
        evt = TemporalEvent(
            id=f"test-tl-evt-{i}",
            statement=f"Timeline Corp event in {year}.",
            entity_ids=["test-tl-ent"],
            temporal=TemporalMetadata(valid_at=datetime(year, 6, 1, tzinfo=UTC)),
        )
        await neo4j.create_temporal_event(evt)
        await neo4j.link_event_to_entities(f"test-tl-evt-{i}", ["test-tl-ent"])

    timeline = await neo4j.get_entity_timeline("test-tl-ent")
    assert len(timeline) == 3
    # Should be ordered by valid_at ASC
    statements = [r["statement"] for r in timeline]
    assert "2020" in statements[0]
    assert "2024" in statements[2]


# --- Episode ---


async def test_create_episode(neo4j_client: Neo4jClient):
    episode = Episode(
        id="test-episode-1",
        content="This is a test episode about Acme Corporation acquiring Beta Inc.",
        episode_type=EpisodeType.TEXT,
        source="test_suite",
        reference_time=datetime(2024, 3, 1, tzinfo=UTC),
    )
    result_id = await neo4j_client.create_episode(episode)
    assert result_id == "test-episode-1"


# --- Stats ---


async def test_get_stats(neo4j_clean: Neo4jClient):
    neo4j = neo4j_clean

    entity = Entity(id="test-stats-ent", name="Stats Corp", entity_type="Organization")
    event = TemporalEvent(
        id="test-stats-evt",
        statement="Stats Corp was founded.",
        temporal=TemporalMetadata(valid_at=datetime(2024, 1, 1, tzinfo=UTC)),
    )
    episode = Episode(
        id="test-stats-ep",
        content="Test content.",
        source="test",
    )
    await neo4j.create_entity(entity)
    await neo4j.create_temporal_event(event)
    await neo4j.create_episode(episode)

    stats = await neo4j.get_stats()
    assert stats["entities"] >= 1
    assert stats["events"] >= 1
    assert stats["episodes"] >= 1
