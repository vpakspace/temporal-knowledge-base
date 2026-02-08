"""Entity resolution: map name variations to canonical entities.

Handles:
- Name normalization ("IBM Corp" → "IBM")
- Fuzzy matching via embeddings (cosine similarity)
- Merging duplicate entities in the graph
"""

from __future__ import annotations

import logging
import re

from core.models import Entity
from storage.neo4j_client import Neo4jClient
from storage.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Threshold for considering two entity names as the same
NAME_SIMILARITY_THRESHOLD = 0.85


class EntityResolver:
    """Resolve extracted entities to canonical forms."""

    def __init__(
        self,
        neo4j: Neo4jClient,
        vector_store: VectorStore,
    ) -> None:
        self._neo4j = neo4j
        self._vectors = vector_store

    async def resolve_batch(self, entities: list[Entity]) -> list[Entity]:
        """Resolve a batch of entities, deduplicating and mapping to canonical forms."""
        resolved: list[Entity] = []
        seen_names: dict[str, Entity] = {}

        for entity in entities:
            normalized = self._normalize_name(entity.name)

            # Local dedup within batch
            if normalized in seen_names:
                continue

            # Check if entity exists in graph
            existing = await self._find_existing(entity)
            if existing and existing.get("id"):
                entity.id = existing["id"]
                entity.canonical_name = existing.get("canonical_name") or existing["name"]
                logger.debug(
                    "Resolved '%s' → '%s' (existing)",
                    entity.name,
                    entity.canonical_name,
                )
            else:
                entity.canonical_name = entity.name

            # Generate embedding if not present
            if not entity.embedding:
                entity.embedding = await self._vectors.embed_text(
                    f"{entity.entity_type}: {entity.name}"
                )

            seen_names[normalized] = entity
            resolved.append(entity)

        return resolved

    async def _find_existing(self, entity: Entity) -> dict | None:
        """Find existing entity in graph by name similarity."""
        # First try exact full-text search
        candidates = await self._neo4j.find_entities_by_name(entity.name, limit=5)

        if not candidates:
            return None

        # Check for exact match
        normalized = self._normalize_name(entity.name)
        for candidate in candidates:
            if self._normalize_name(candidate["name"]) == normalized:
                return candidate

        # Fuzzy match via embeddings
        entity_embedding = await self._vectors.embed_text(f"{entity.entity_type}: {entity.name}")
        for candidate in candidates:
            cand_embedding = await self._vectors.embed_text(
                f"{candidate.get('entity_type', 'Concept')}: {candidate['name']}"
            )
            similarity = VectorStore.cosine_similarity(entity_embedding, cand_embedding)
            if similarity >= NAME_SIMILARITY_THRESHOLD:
                return candidate

        return None

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize entity name for comparison."""
        name = name.lower().strip()
        # Remove common suffixes
        for suffix in (" inc", " inc.", " corp", " corp.", " ltd", " ltd.", " llc"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        # Remove extra whitespace
        name = re.sub(r"\s+", " ", name)
        return name.strip()
