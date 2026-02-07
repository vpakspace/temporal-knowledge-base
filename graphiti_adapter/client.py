"""Graphiti client wrapper for temporal knowledge base.

Wraps graphiti-core to provide:
- Simplified initialization with our config
- Episode management (add, remove, retrieve)
- Hybrid search with configurable recipes
- Access to the underlying Neo4j graph
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.llm_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType as GraphitiEpisodeType
from graphiti_core.search.search_config_recipes import (
    EDGE_HYBRID_SEARCH_MMR,
    EDGE_HYBRID_SEARCH_RRF,
    NODE_HYBRID_SEARCH_MMR,
    NODE_HYBRID_SEARCH_RRF,
)
from graphiti_core.search.search_filters import SearchFilters

from core.config import AppSettings
from core.exceptions import EpisodeProcessingError, SearchError
from core.models import EpisodeType

logger = logging.getLogger(__name__)

# Map our EpisodeType to Graphiti's
_EPISODE_TYPE_MAP = {
    EpisodeType.TEXT: GraphitiEpisodeType.text,
    EpisodeType.JSON: GraphitiEpisodeType.json,
    EpisodeType.CHAT: GraphitiEpisodeType.message,
    EpisodeType.DOCUMENT: GraphitiEpisodeType.text,
}

# Available search recipes
SEARCH_RECIPES = {
    "node_rrf": NODE_HYBRID_SEARCH_RRF,
    "node_mmr": NODE_HYBRID_SEARCH_MMR,
    "edge_rrf": EDGE_HYBRID_SEARCH_RRF,
    "edge_mmr": EDGE_HYBRID_SEARCH_MMR,
}


class GraphitiClient:
    """Wrapper around graphiti-core Graphiti class."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._graphiti: Graphiti | None = None

    async def connect(self) -> None:
        """Initialize Graphiti with Neo4j and OpenAI."""
        llm_config = LLMConfig(
            api_key=self._settings.openai.api_key,
            model=self._settings.openai.llm_model,
        )
        llm_client = OpenAIClient(config=llm_config)
        self._graphiti = Graphiti(
            uri=self._settings.neo4j.uri,
            user=self._settings.neo4j.user,
            password=self._settings.neo4j.password,
            llm_client=llm_client,
        )
        await self._graphiti.build_indices_and_constraints()
        logger.info("Graphiti client connected")

    async def close(self) -> None:
        if self._graphiti:
            await self._graphiti.close()
            self._graphiti = None

    @property
    def graphiti(self) -> Graphiti:
        if not self._graphiti:
            raise RuntimeError("Graphiti client not connected")
        return self._graphiti

    async def add_episode(
        self,
        name: str,
        content: str,
        source: str = "manual",
        reference_time: datetime | None = None,
        episode_type: EpisodeType = EpisodeType.TEXT,
        group_id: str | None = None,
        entity_types: dict[str, Any] | None = None,
        custom_instructions: str | None = None,
    ) -> dict[str, Any]:
        """Add an episode to the knowledge graph.

        This is the primary ingestion method. Graphiti will:
        1. Extract entities from the content
        2. Resolve entities to existing nodes (deduplication)
        3. Extract relationships/edges
        4. Handle temporal invalidation of superseded facts
        """
        if reference_time is None:
            reference_time = datetime.now(UTC)

        graphiti_type = _EPISODE_TYPE_MAP.get(episode_type, GraphitiEpisodeType.text)

        try:
            result = await self.graphiti.add_episode(
                name=name,
                episode_body=content,
                source_description=source,
                reference_time=reference_time,
                source=graphiti_type,
                group_id=group_id,
                entity_types=entity_types,
                custom_extraction_instructions=custom_instructions,
            )
            logger.info(
                "Episode '%s' added (type=%s, source=%s)",
                name, episode_type.value, source,
            )
            return result.model_dump() if hasattr(result, "model_dump") else {}
        except Exception as e:
            raise EpisodeProcessingError(
                f"Failed to add episode '{name}': {e}"
            ) from e

    async def add_episode_bulk(
        self,
        episodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Add multiple episodes in bulk."""
        results = []
        for ep in episodes:
            result = await self.add_episode(**ep)
            results.append(result)
        return results

    async def search(
        self,
        query: str,
        recipe: str = "edge_rrf",
        num_results: int = 10,
        group_ids: list[str] | None = None,
        center_node_uuid: str | None = None,
        search_filter: SearchFilters | None = None,
    ) -> list[dict[str, Any]]:
        """Search the knowledge graph using configurable recipes.

        Recipes:
        - node_rrf: Node hybrid search with Reciprocal Rank Fusion
        - node_mmr: Node hybrid search with Maximal Marginal Relevance
        - edge_rrf: Edge hybrid search with RRF (default, best for facts)
        - edge_mmr: Edge hybrid search with MMR (more diverse results)
        """
        search_config = SEARCH_RECIPES.get(recipe)
        if search_config is None:
            raise SearchError(f"Unknown recipe: {recipe}. Use: {list(SEARCH_RECIPES)}")

        try:
            edges = await self.graphiti.search(
                query=query,
                num_results=num_results,
                group_ids=group_ids,
                center_node_uuid=center_node_uuid,
                search_filter=search_filter,
            )
            return [
                {
                    "uuid": edge.uuid,
                    "name": edge.name,
                    "fact": edge.fact,
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "created_at": str(edge.created_at) if edge.created_at else None,
                    "valid_at": str(edge.valid_at) if edge.valid_at else None,
                    "invalid_at": str(edge.invalid_at) if edge.invalid_at else None,
                    "expired_at": str(edge.expired_at) if edge.expired_at else None,
                }
                for edge in edges
            ]
        except Exception as e:
            raise SearchError(f"Search failed: {e}") from e

    async def retrieve_episodes(
        self,
        reference_time: datetime | None = None,
        last_n: int = 10,
        group_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve stored episodes."""
        if reference_time is None:
            reference_time = datetime.now(UTC)
        try:
            episodes = await self.graphiti.retrieve_episodes(
                reference_time=reference_time,
                last_n=last_n,
                group_ids=[group_id] if group_id else None,
            )
            return [
                {
                    "uuid": ep.uuid,
                    "name": ep.name,
                    "source": ep.source,
                    "created_at": str(ep.created_at) if ep.created_at else None,
                }
                for ep in episodes
            ]
        except Exception as e:
            raise SearchError(f"Retrieve episodes failed: {e}") from e

    async def remove_episode(self, episode_uuid: str) -> None:
        """Remove an episode and its extracted knowledge."""
        try:
            await self.graphiti.remove_episode(episode_uuid)
            logger.info("Episode %s removed", episode_uuid)
        except Exception as e:
            raise EpisodeProcessingError(
                f"Failed to remove episode {episode_uuid}: {e}"
            ) from e
