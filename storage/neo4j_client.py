"""Neo4j async client with bi-temporal CRUD operations.

Handles the dual-track storage:
- Entity Layer: create/update/query entities and relationships
- Temporal Event Layer: store temporal events, manage SUPERSEDED_BY chains
- Point-in-time queries: snapshot the graph at any given datetime
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncGenerator

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

from core.config import Neo4jSettings
from core.exceptions import Neo4jConnectionError
from core.models import (
    Entity,
    Episode,
    Relationship,
    TemporalEvent,
)
from storage.schema import init_schema

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Async Neo4j client for temporal knowledge base."""

    def __init__(self, settings: Neo4jSettings) -> None:
        self._settings = settings
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Establish connection and initialize schema."""
        try:
            self._driver = AsyncGraphDatabase.driver(
                self._settings.uri,
                auth=(self._settings.user, self._settings.password),
            )
            await self._driver.verify_connectivity()
            async with self.session() as session:
                await init_schema(session)
            logger.info("Connected to Neo4j at %s", self._settings.uri)
        except Exception as e:
            raise Neo4jConnectionError(f"Failed to connect to Neo4j: {e}") from e

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def clear_database(self) -> dict[str, int]:
        """Delete ALL nodes and relationships. Returns counts of deleted items."""
        count_query = """
        MATCH (n)
        OPTIONAL MATCH (n)-[r]-()
        RETURN count(DISTINCT n) AS nodes, count(DISTINCT r) AS relationships
        """
        delete_query = """
        MATCH (n) DETACH DELETE n
        """
        async with self.session() as session:
            result = await session.run(count_query)
            record = await result.single()
            counts = {
                "nodes": record["nodes"] if record else 0,
                "relationships": record["relationships"] if record else 0,
            }
            await session.run(delete_query)
            logger.info(
                "Cleared database: %d nodes, %d relationships",
                counts["nodes"],
                counts["relationships"],
            )
            return counts

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        if not self._driver:
            raise Neo4jConnectionError("Not connected")
        async with self._driver.session() as session:
            yield session

    # --- Entity Layer ---

    async def create_entity(self, entity: Entity) -> str:
        """Create or merge an entity node."""
        query = """
        MERGE (e:Entity {id: $id})
        SET e.name = $name,
            e.entity_type = $entity_type,
            e.canonical_name = $canonical_name,
            e.properties = $properties,
            e.embedding = $embedding,
            e.valid_at = $valid_at,
            e.invalid_at = $invalid_at,
            e.expired_at = $expired_at,
            e.created_at = $created_at,
            e.is_current = $is_current,
            e.invalidation_mode = $invalidation_mode,
            e.source_episode_id = $source_episode_id
        RETURN e.id
        """
        async with self.session() as session:
            result = await session.run(
                query,
                id=entity.id,
                name=entity.name,
                entity_type=entity.entity_type,
                canonical_name=entity.canonical_name,
                properties=str(entity.properties),
                embedding=entity.embedding,
                valid_at=_to_iso(entity.temporal.valid_at),
                invalid_at=_to_iso(entity.temporal.invalid_at),
                expired_at=_to_iso(entity.temporal.expired_at),
                created_at=_to_iso(entity.temporal.created_at),
                is_current=entity.temporal.is_current,
                invalidation_mode=entity.invalidation_mode.value,
                source_episode_id=entity.temporal.source_episode_id,
            )
            record = await result.single()
            return record["e.id"] if record else entity.id

    async def create_relationship(self, rel: Relationship) -> str:
        """Create a relationship edge with bi-temporal properties."""
        query = """
        MATCH (src:Entity {id: $source_id})
        MATCH (tgt:Entity {id: $target_id})
        CREATE (src)-[r:RELATES_TO {
            id: $id,
            relation_type: $relation_type,
            properties: $properties,
            embedding: $embedding,
            fact_type: $fact_type,
            valid_at: $valid_at,
            invalid_at: $invalid_at,
            expired_at: $expired_at,
            created_at: $created_at,
            is_current: $is_current,
            source_episode_id: $source_episode_id
        }]->(tgt)
        RETURN r.id
        """
        async with self.session() as session:
            result = await session.run(
                query,
                id=rel.id,
                source_id=rel.source_id,
                target_id=rel.target_id,
                relation_type=rel.relation_type,
                properties=str(rel.properties),
                embedding=rel.embedding,
                fact_type=rel.fact_type.value,
                valid_at=_to_iso(rel.temporal.valid_at),
                invalid_at=_to_iso(rel.temporal.invalid_at),
                expired_at=_to_iso(rel.temporal.expired_at),
                created_at=_to_iso(rel.temporal.created_at),
                is_current=rel.temporal.is_current,
                source_episode_id=rel.temporal.source_episode_id,
            )
            record = await result.single()
            return record["r.id"] if record else rel.id

    # --- Temporal Event Layer ---

    async def create_temporal_event(self, event: TemporalEvent) -> str:
        """Store an atomic temporal fact."""
        query = """
        CREATE (te:TemporalEvent {
            id: $id,
            statement: $statement,
            fact_type: $fact_type,
            entity_ids: $entity_ids,
            embedding: $embedding,
            confidence: $confidence,
            source: $source,
            valid_at: $valid_at,
            invalid_at: $invalid_at,
            expired_at: $expired_at,
            created_at: $created_at,
            is_current: $is_current,
            source_episode_id: $source_episode_id
        })
        RETURN te.id
        """
        async with self.session() as session:
            result = await session.run(
                query,
                id=event.id,
                statement=event.statement,
                fact_type=event.fact_type.value,
                entity_ids=event.entity_ids,
                embedding=event.embedding,
                confidence=event.confidence,
                source=event.source,
                valid_at=_to_iso(event.temporal.valid_at),
                invalid_at=_to_iso(event.temporal.invalid_at),
                expired_at=_to_iso(event.temporal.expired_at),
                created_at=_to_iso(event.temporal.created_at),
                is_current=event.temporal.is_current,
                source_episode_id=event.temporal.source_episode_id,
            )
            record = await result.single()
            return record["te.id"] if record else event.id

    async def link_event_to_entities(self, event_id: str, entity_ids: list[str]) -> None:
        """Create MENTIONS edges from event to referenced entities."""
        query = """
        MATCH (te:TemporalEvent {id: $event_id})
        MATCH (e:Entity) WHERE e.id IN $entity_ids
        MERGE (te)-[:MENTIONS]->(e)
        """
        async with self.session() as session:
            await session.run(query, event_id=event_id, entity_ids=entity_ids)

    async def supersede_event(self, old_id: str, new_id: str) -> None:
        """Mark old event as superseded by new one. Create SUPERSEDED_BY edge."""
        query = """
        MATCH (old:TemporalEvent {id: $old_id})
        MATCH (new:TemporalEvent {id: $new_id})
        SET old.is_current = false,
            old.invalid_at = $now
        CREATE (old)-[:SUPERSEDED_BY]->(new)
        """
        async with self.session() as session:
            await session.run(
                query,
                old_id=old_id,
                new_id=new_id,
                now=_to_iso(datetime.now(UTC)),
            )

    # --- Episode ---

    async def create_episode(self, episode: Episode) -> str:
        """Store episode metadata."""
        query = """
        CREATE (ep:Episode {
            id: $id,
            content: $content,
            episode_type: $episode_type,
            source: $source,
            reference_time: $reference_time,
            created_at: $created_at
        })
        RETURN ep.id
        """
        async with self.session() as session:
            result = await session.run(
                query,
                id=episode.id,
                content=episode.content[:500],  # Store truncated content as metadata
                episode_type=episode.episode_type.value,
                source=episode.source,
                reference_time=_to_iso(episode.reference_time),
                created_at=_to_iso(episode.created_at),
            )
            record = await result.single()
            return record["ep.id"] if record else episode.id

    # --- Temporal Queries (Point-in-Time) ---

    async def query_point_in_time(
        self, point: datetime, entity_type: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get a snapshot of all current facts at a specific point in time."""
        type_filter = "AND te.entity_type = $entity_type" if entity_type else ""
        query = f"""
        MATCH (te:TemporalEvent)
        WHERE te.valid_at <= $point
          AND (te.expired_at IS NULL OR te.expired_at > $point)
          AND (te.invalid_at IS NULL OR te.invalid_at > $point)
          {type_filter}
        RETURN te.id AS id, te.statement AS statement,
               te.valid_at AS valid_at, te.fact_type AS fact_type,
               te.confidence AS confidence
        ORDER BY te.valid_at DESC
        LIMIT $limit
        """
        params: dict[str, Any] = {"point": _to_iso(point), "limit": limit}
        if entity_type:
            params["entity_type"] = entity_type

        async with self.session() as session:
            result = await session.run(query, **params)
            return [dict(record) async for record in result]

    async def get_entity_timeline(self, entity_id: str) -> list[dict[str, Any]]:
        """Get full timeline of events mentioning an entity."""
        query = """
        MATCH (te:TemporalEvent)-[:MENTIONS]->(e:Entity {id: $entity_id})
        OPTIONAL MATCH (te)-[:SUPERSEDED_BY]->(newer:TemporalEvent)
        RETURN te.id AS id, te.statement AS statement,
               te.valid_at AS valid_at, te.invalid_at AS invalid_at,
               te.is_current AS is_current, newer.id AS superseded_by
        ORDER BY te.valid_at ASC
        """
        async with self.session() as session:
            result = await session.run(query, entity_id=entity_id)
            return [dict(record) async for record in result]

    async def get_supersession_chain(self, event_id: str) -> list[dict[str, Any]]:
        """Follow the SUPERSEDED_BY chain from an event."""
        query = """
        MATCH path = (start:TemporalEvent {id: $event_id})-[:SUPERSEDED_BY*0..]->(end)
        UNWIND nodes(path) AS te
        WITH DISTINCT te
        RETURN te.id AS id, te.statement AS statement,
               te.valid_at AS valid_at, te.invalid_at AS invalid_at,
               te.is_current AS is_current
        ORDER BY te.valid_at ASC
        """
        async with self.session() as session:
            result = await session.run(query, event_id=event_id)
            return [dict(record) async for record in result]

    # --- Search helpers ---

    async def find_entities_by_name(self, name: str, limit: int = 5) -> list[dict[str, Any]]:
        """Full-text search for entities by name."""
        query = """
        CALL db.index.fulltext.queryNodes('entity_fulltext', $name)
        YIELD node, score
        RETURN node.id AS id, node.name AS name,
               node.entity_type AS entity_type,
               node.canonical_name AS canonical_name,
               score
        LIMIT $limit
        """
        async with self.session() as session:
            result = await session.run(query, name=name, limit=limit)
            return [dict(record) async for record in result]

    async def vector_search_events(
        self, embedding: list[float], limit: int = 10, current_only: bool = True
    ) -> list[dict[str, Any]]:
        """Vector similarity search on temporal events."""
        current_filter = "AND node.is_current = true" if current_only else ""
        query = f"""
        CALL db.index.vector.queryNodes('event_embedding', $limit, $embedding)
        YIELD node, score
        WHERE score > 0.3 {current_filter}
        RETURN node.id AS id, node.statement AS statement,
               node.valid_at AS valid_at, node.is_current AS is_current,
               score
        ORDER BY score DESC
        """
        async with self.session() as session:
            result = await session.run(query, embedding=embedding, limit=limit)
            return [dict(record) async for record in result]

    async def get_current_events_for_entities(self, entity_ids: list[str]) -> list[dict[str, Any]]:
        """Get all current temporal events for given entities."""
        query = """
        MATCH (te:TemporalEvent)-[:MENTIONS]->(e:Entity)
        WHERE e.id IN $entity_ids AND te.is_current = true
        RETURN te.id AS id, te.statement AS statement,
               te.valid_at AS valid_at, te.embedding AS embedding,
               te.entity_ids AS entity_ids
        """
        async with self.session() as session:
            result = await session.run(query, entity_ids=entity_ids)
            return [dict(record) async for record in result]

    async def get_all_entities(self, limit: int = 200) -> list[dict[str, Any]]:
        """Get all entities with their basic info."""
        query = """
        MATCH (e:Entity)
        RETURN COALESCE(e.id, e.uuid) AS id,
               e.name AS name,
               COALESCE(e.entity_type, head(e.labels)) AS entity_type,
               e.canonical_name AS canonical_name
        ORDER BY e.name
        LIMIT $limit
        """
        async with self.session() as session:
            result = await session.run(query, limit=limit)
            return [dict(record) async for record in result]

    async def get_entity_details(self, entity_id: str) -> dict[str, Any] | None:
        """Get entity with its relationships and event counts."""
        query = """
        MATCH (e:Entity)
        WHERE e.id = $entity_id OR e.uuid = $entity_id
        OPTIONAL MATCH (e)<-[:MENTIONS]-(te:TemporalEvent)
        WITH e,
             count(te) AS total_events,
             count(CASE WHEN te.is_current = true THEN 1 END) AS current_events
        OPTIONAL MATCH (e)-[r:RELATES_TO]->(other:Entity)
        WITH e, total_events, current_events,
             collect(DISTINCT {
                id: COALESCE(r.id, r.uuid),
                relation_type: COALESCE(r.relation_type, r.name),
                target_id: COALESCE(other.id, other.uuid),
                target_name: other.name,
                direction: 'outgoing'
             }) AS outgoing
        OPTIONAL MATCH (e)<-[r2:RELATES_TO]-(other2:Entity)
        RETURN COALESCE(e.id, e.uuid) AS id, e.name AS name,
               COALESCE(e.entity_type, head(e.labels)) AS entity_type,
               e.canonical_name AS canonical_name,
               e.valid_at AS valid_at,
               e.created_at AS created_at,
               total_events, current_events,
               outgoing +
               collect(DISTINCT {
                id: COALESCE(r2.id, r2.uuid),
                relation_type: COALESCE(r2.relation_type, r2.name),
                target_id: COALESCE(other2.id, other2.uuid),
                target_name: other2.name,
                direction: 'incoming'
               }) AS relationships
        """
        async with self.session() as session:
            result = await session.run(query, entity_id=entity_id)
            record = await result.single()
            if not record:
                return None
            data = dict(record)
            # Filter out empty relationship entries (from OPTIONAL MATCH)
            data["relationships"] = [r for r in data.get("relationships", []) if r.get("target_id")]
            return data

    async def get_graph_data(self, limit: int = 100) -> dict[str, Any]:
        """Get entities and relationships for graph visualization."""
        nodes_query = """
        MATCH (e:Entity)
        RETURN COALESCE(e.id, e.uuid) AS id,
               e.name AS name,
               COALESCE(e.entity_type, head(e.labels)) AS entity_type
        ORDER BY e.name
        LIMIT $limit
        """
        edges_query = """
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        RETURN COALESCE(src.id, src.uuid) AS source,
               COALESCE(tgt.id, tgt.uuid) AS target,
               COALESCE(r.relationship_type, r.name) AS label
        LIMIT $limit
        """
        async with self.session() as session:
            nodes_result = await session.run(nodes_query, limit=limit)
            nodes = [dict(record) async for record in nodes_result]

            edges_result = await session.run(edges_query, limit=limit)
            edges = [dict(record) async for record in edges_result]

        return {"nodes": nodes, "edges": edges}

    # --- Communities ---

    async def get_communities(self) -> list[dict[str, Any]]:
        """Get existing Community nodes with their members."""
        query = """
        MATCH (c:Community)
        OPTIONAL MATCH (c)-[:HAS_MEMBER]->(e:Entity)
        WITH c, collect({id: COALESCE(e.id, e.uuid), name: e.name, entity_type: COALESCE(e.entity_type, head(e.labels))}) AS members
        RETURN c.uuid AS id, c.name AS name, c.summary AS summary,
               size(members) AS member_count, members
        ORDER BY size(members) DESC
        """
        async with self.session() as session:
            result = await session.run(query)
            records = [dict(r) async for r in result]
            # Filter out null members from OPTIONAL MATCH
            for rec in records:
                rec["members"] = [m for m in rec.get("members", []) if m.get("id")]
            return records

    async def get_entity_clusters(self) -> list[dict[str, Any]]:
        """Lightweight community detection via connected components (no LLM).

        Groups entities by RELATES_TO connectivity using BFS traversal.
        """
        query = """
        MATCH (e:Entity)
        OPTIONAL MATCH path = (e)-[:RELATES_TO*1..5]-(connected:Entity)
        WITH e, collect(DISTINCT connected) AS neighbors
        RETURN COALESCE(e.id, e.uuid) AS id,
               e.name AS name,
               COALESCE(e.entity_type, head(e.labels)) AS entity_type,
               [n IN neighbors | COALESCE(n.id, n.uuid)] AS connected_ids
        """
        async with self.session() as session:
            result = await session.run(query)
            nodes = [dict(r) async for r in result]

        # BFS to find connected components
        adjacency: dict[str, set[str]] = {}
        node_map: dict[str, dict] = {}
        for n in nodes:
            nid = n["id"]
            node_map[nid] = {"id": nid, "name": n["name"], "entity_type": n["entity_type"]}
            adjacency[nid] = set(n.get("connected_ids", []))

        visited: set[str] = set()
        clusters: list[list[dict]] = []
        for nid in adjacency:
            if nid in visited:
                continue
            # BFS
            component: list[str] = []
            queue = [nid]
            while queue:
                curr = queue.pop(0)
                if curr in visited:
                    continue
                visited.add(curr)
                component.append(curr)
                for neighbor in adjacency.get(curr, []):
                    if neighbor not in visited:
                        queue.append(neighbor)
            clusters.append([node_map[c] for c in component if c in node_map])

        # Sort by size descending, return with cluster_id
        clusters.sort(key=len, reverse=True)
        return [{"cluster_id": i, "size": len(c), "members": c} for i, c in enumerate(clusters)]

    # --- Contradictions ---

    async def get_contradictions(self) -> dict[str, Any]:
        """Get all supersession chains grouped by root event, with entity hotspots."""
        # All supersession chains (old → new)
        chains_q = """
        MATCH (old:TemporalEvent)-[:SUPERSEDED_BY]->(new:TemporalEvent)
        OPTIONAL MATCH (old)-[:MENTIONS]->(e:Entity)
        WITH old, new, collect(DISTINCT e.name) AS entities
        RETURN old.id AS old_id,
               old.statement AS old_statement,
               old.valid_at AS old_valid_at,
               old.invalid_at AS old_invalid_at,
               new.id AS new_id,
               new.statement AS new_statement,
               new.valid_at AS new_valid_at,
               new.is_current AS new_is_current,
               entities
        ORDER BY old.invalid_at DESC
        """
        # Entity hotspots: entities with most superseded facts
        hotspots_q = """
        MATCH (te:TemporalEvent)-[:SUPERSEDED_BY]->(:TemporalEvent)
        MATCH (te)-[:MENTIONS]->(e:Entity)
        WITH COALESCE(e.id, e.uuid) AS entity_id, e.name AS entity_name,
             COALESCE(e.entity_type, head(e.labels)) AS entity_type,
             count(te) AS superseded_count
        WHERE superseded_count > 0
        RETURN entity_id, entity_name, entity_type, superseded_count
        ORDER BY superseded_count DESC
        LIMIT 20
        """
        # Recent invalidation log
        log_q = """
        MATCH (te:TemporalEvent)
        WHERE te.invalid_at IS NOT NULL
        OPTIONAL MATCH (te)-[:SUPERSEDED_BY]->(newer:TemporalEvent)
        OPTIONAL MATCH (te)-[:MENTIONS]->(e:Entity)
        WITH te, newer, collect(DISTINCT e.name) AS entities
        RETURN te.id AS id,
               te.statement AS statement,
               te.valid_at AS valid_at,
               te.invalid_at AS invalid_at,
               newer.id AS replaced_by_id,
               newer.statement AS replaced_by,
               entities
        ORDER BY te.invalid_at DESC
        LIMIT 50
        """
        async with self.session() as session:
            res = await session.run(chains_q)
            chains = [dict(r) async for r in res]

            res = await session.run(hotspots_q)
            hotspots = [dict(r) async for r in res]

            res = await session.run(log_q)
            log = [dict(r) async for r in res]

        return {"chains": chains, "hotspots": hotspots, "invalidation_log": log}

    # --- Export ---

    async def export_all(self) -> dict[str, Any]:
        """Export all graph data as JSON-serializable dict."""
        entities_q = """
        MATCH (e:Entity)
        RETURN e {.*} AS data
        """
        events_q = """
        MATCH (te:TemporalEvent)
        OPTIONAL MATCH (te)-[:MENTIONS]->(e:Entity)
        WITH te, collect(e.id) AS mention_ids
        RETURN te {.*} AS data, mention_ids
        """
        episodes_q = """
        MATCH (ep:Episode)
        RETURN ep {.*} AS data
        """
        rels_q = """
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        RETURN r {.*, source_id: src.id, target_id: tgt.id} AS data
        """
        supersessions_q = """
        MATCH (old:TemporalEvent)-[:SUPERSEDED_BY]->(new:TemporalEvent)
        RETURN old.id AS old_id, new.id AS new_id
        """
        async with self.session() as session:
            res = await session.run(entities_q)
            entities = [dict(r["data"]) async for r in res]

            res = await session.run(events_q)
            events = []
            async for r in res:
                ev = dict(r["data"])
                ev["mention_ids"] = r["mention_ids"]
                events.append(ev)

            res = await session.run(episodes_q)
            episodes = [dict(r["data"]) async for r in res]

            res = await session.run(rels_q)
            relationships = [dict(r["data"]) async for r in res]

            res = await session.run(supersessions_q)
            supersessions = [{"old_id": r["old_id"], "new_id": r["new_id"]} async for r in res]

        return {
            "version": "1.0",
            "entities": entities,
            "events": events,
            "episodes": episodes,
            "relationships": relationships,
            "supersessions": supersessions,
        }

    async def import_all(self, data: dict[str, Any]) -> dict[str, int]:
        """Import graph data from export JSON. Merges by ID."""
        counts = {"entities": 0, "events": 0, "episodes": 0, "relationships": 0, "supersessions": 0}

        async with self.session() as session:
            for e in data.get("entities", []):
                await session.run(
                    "MERGE (n:Entity {id: $id}) SET n += $props",
                    id=e["id"],
                    props={k: v for k, v in e.items() if v is not None},
                )
                counts["entities"] += 1

            for ev in data.get("events", []):
                mention_ids = ev.pop("mention_ids", [])
                await session.run(
                    "MERGE (n:TemporalEvent {id: $id}) SET n += $props",
                    id=ev["id"],
                    props={k: v for k, v in ev.items() if v is not None},
                )
                if mention_ids:
                    await session.run(
                        """
                        MATCH (te:TemporalEvent {id: $eid})
                        MATCH (e:Entity) WHERE e.id IN $eids
                        MERGE (te)-[:MENTIONS]->(e)
                        """,
                        eid=ev["id"],
                        eids=mention_ids,
                    )
                counts["events"] += 1

            for ep in data.get("episodes", []):
                await session.run(
                    "MERGE (n:Episode {id: $id}) SET n += $props",
                    id=ep["id"],
                    props={k: v for k, v in ep.items() if v is not None},
                )
                counts["episodes"] += 1

            for r in data.get("relationships", []):
                source_id = r.pop("source_id", None)
                target_id = r.pop("target_id", None)
                if source_id and target_id:
                    await session.run(
                        """
                        MATCH (src:Entity {id: $src}), (tgt:Entity {id: $tgt})
                        MERGE (src)-[r:RELATES_TO {id: $rid}]->(tgt)
                        SET r += $props
                        """,
                        src=source_id,
                        tgt=target_id,
                        rid=r.get("id", ""),
                        props={k: v for k, v in r.items() if v is not None},
                    )
                    counts["relationships"] += 1

            for s in data.get("supersessions", []):
                await session.run(
                    """
                    MATCH (old:TemporalEvent {id: $old_id})
                    MATCH (new:TemporalEvent {id: $new_id})
                    MERGE (old)-[:SUPERSEDED_BY]->(new)
                    """,
                    old_id=s["old_id"],
                    new_id=s["new_id"],
                )
                counts["supersessions"] += 1

        return counts

    # --- Stats ---

    async def get_stats(self) -> dict[str, int]:
        """Get graph statistics."""
        query = """
        MATCH (e:Entity) WITH count(e) AS entities
        MATCH (te:TemporalEvent) WITH entities, count(te) AS events
        MATCH (te2:TemporalEvent {is_current: true}) WITH entities, events, count(te2) AS current_events
        MATCH (ep:Episode) WITH entities, events, current_events, count(ep) AS episodes
        RETURN entities, events, current_events, episodes
        """
        async with self.session() as session:
            result = await session.run(query)
            record = await result.single()
            if record:
                return dict(record)
            return {"entities": 0, "events": 0, "current_events": 0, "episodes": 0}


def _to_iso(dt: datetime | None) -> str | None:
    """Convert datetime to ISO string for Neo4j storage."""
    if dt is None:
        return None
    return dt.isoformat()
