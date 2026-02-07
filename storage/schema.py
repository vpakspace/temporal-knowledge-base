"""Neo4j graph schema: constraints, indexes, and initialization.

Implements the dual-track storage model:
- Entity Layer: EntityNode, RELATES_TO edges with bi-temporal properties
- Temporal Event Layer: TemporalEvent nodes with SUPERSEDED_BY chains
"""

from __future__ import annotations

import logging

from neo4j import AsyncSession

logger = logging.getLogger(__name__)

CONSTRAINTS = [
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:TemporalEvent) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT episode_id IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
    "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
    "CREATE INDEX entity_canonical IF NOT EXISTS FOR (e:Entity) ON (e.canonical_name)",
    "CREATE INDEX event_is_current IF NOT EXISTS FOR (e:TemporalEvent) ON (e.is_current)",
    "CREATE INDEX event_valid_at IF NOT EXISTS FOR (e:TemporalEvent) ON (e.valid_at)",
    "CREATE INDEX episode_created IF NOT EXISTS FOR (e:Episode) ON (e.created_at)",
    # Full-text indexes for keyword search
    "CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.canonical_name]",
    "CREATE FULLTEXT INDEX event_fulltext IF NOT EXISTS FOR (e:TemporalEvent) ON EACH [e.statement]",
]

# Vector indexes require Neo4j 5.11+ (created separately)
VECTOR_INDEX_ENTITY = """
CALL db.index.vector.createNodeIndex(
  'entity_embedding', 'Entity', 'embedding', 1536, 'cosine'
)
"""

VECTOR_INDEX_EVENT = """
CALL db.index.vector.createNodeIndex(
  'event_embedding', 'TemporalEvent', 'embedding', 1536, 'cosine'
)
"""


async def init_schema(session: AsyncSession) -> None:
    """Initialize Neo4j schema with constraints, indexes."""
    for stmt in CONSTRAINTS:
        try:
            await session.run(stmt)
            logger.debug("Created constraint: %s", stmt[:60])
        except Exception as e:
            if "already exists" in str(e).lower():
                pass
            else:
                logger.warning("Constraint failed: %s", e)

    for stmt in INDEXES:
        try:
            await session.run(stmt)
            logger.debug("Created index: %s", stmt[:60])
        except Exception as e:
            if "already exists" in str(e).lower():
                pass
            else:
                logger.warning("Index failed: %s", e)

    # Vector indexes
    for stmt in (VECTOR_INDEX_ENTITY, VECTOR_INDEX_EVENT):
        try:
            await session.run(stmt)
        except Exception as e:
            if "already exists" in str(e).lower() or "equivalent index" in str(e).lower():
                pass
            else:
                logger.warning("Vector index failed (may need Neo4j 5.11+): %s", e)

    logger.info("Neo4j schema initialized")
