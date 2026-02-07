"""MCP Server for Temporal Knowledge Base.

Provides 6 tools for Claude Code integration:
- tkb_ingest: Add episode to knowledge graph
- tkb_search: Temporal-aware fact search
- tkb_ask: Search + LLM response
- tkb_timeline: Entity timeline
- tkb_evolution: SUPERSEDED_BY chain
- tkb_stats: Graph statistics

Usage:
    python mcp_server.py

    Or configure in ~/.claude.json:
    {
        "mcpServers": {
            "temporal-kb": {
                "command": "python3",
                "args": ["mcp_server.py"],
                "cwd": "/home/vladspace_ubuntu24/temporal-knowledge-base",
                "env": {
                    "NEO4J_URI": "bolt://localhost:7687",
                    "NEO4J_USER": "neo4j",
                    "NEO4J_PASSWORD": "temporal_kb_2026"
                }
            }
        }
    }
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

try:
    from fastmcp import FastMCP
except ImportError:
    raise ImportError("fastmcp is required. Install with: pip install fastmcp")

# Heavy imports are deferred to get_state() so the MCP server starts instantly.
# This prevents Claude Code health-check timeouts.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --- Lazy singleton state ---

class _State:
    """Holds initialized resources. Created once on first tool call."""

    def __init__(self) -> None:
        self.neo4j: Any = None
        self.graphiti: Any = None
        self.vector_store: Any = None
        self.llm: Any = None
        self.pipeline: Any = None
        self.query_engine: Any = None
        self.response_builder: Any = None
        self.settings: Any = None


_state: _State | None = None


async def get_state() -> _State:
    """Lazy-initialize all resources on first call."""
    global _state

    if _state is not None and _state.neo4j is not None:
        return _state

    # Deferred imports — only loaded when first tool is called
    from core.config import get_settings
    from generation.llm_client import LLMClient
    from generation.response_builder import ResponseBuilder
    from generation.temporal_verifier import TemporalVerifier
    from graphiti_adapter.client import GraphitiClient
    from ingestion.pipeline import IngestionPipeline
    from retrieval.query_engine import QueryEngine
    from storage.neo4j_client import Neo4jClient
    from storage.vector_store import VectorStore
    from temporal.invalidation_agent import InvalidationAgent
    from temporal.resolution import EntityResolver

    _state = _State()
    settings = get_settings()
    _state.settings = settings

    if not settings.openai.api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    # Neo4j
    neo4j = Neo4jClient(settings.neo4j)
    await neo4j.connect()
    _state.neo4j = neo4j

    # Vector store & LLM
    vector_store = VectorStore(settings.openai)
    llm = LLMClient(settings.openai)
    _state.vector_store = vector_store
    _state.llm = llm

    # Graphiti
    graphiti = GraphitiClient(settings)
    await graphiti.connect()
    _state.graphiti = graphiti

    # Dependent components
    entity_resolver = EntityResolver(neo4j, vector_store)
    invalidation_agent = InvalidationAgent(neo4j, vector_store, llm, settings)
    verifier = TemporalVerifier(neo4j)

    _state.pipeline = IngestionPipeline(
        graphiti=graphiti,
        neo4j=neo4j,
        vector_store=vector_store,
        llm=llm,
        invalidation_agent=invalidation_agent,
        entity_resolver=entity_resolver,
        settings=settings,
    )
    _state.query_engine = QueryEngine(graphiti, neo4j, llm)
    _state.response_builder = ResponseBuilder(llm, verifier)

    logger.info("Temporal Knowledge Base MCP state initialized")
    return _state


# --- Implementation functions (testable without FastMCP) ---


async def _tkb_ingest_impl(
    content: str,
    source: str = "manual",
    episode_type: str = "text",
    reference_time: str | None = None,
    group_id: str | None = None,
) -> dict[str, Any]:
    """Ingest an episode into the temporal knowledge graph."""
    from core.models import EpisodeType

    state = await get_state()

    try:
        ep_type = EpisodeType(episode_type)
    except ValueError:
        ep_type = EpisodeType.TEXT

    ref_time: datetime | None = None
    if reference_time:
        try:
            ref_time = datetime.fromisoformat(reference_time)
        except ValueError:
            ref_time = None

    result = await state.pipeline.ingest_episode(
        content=content,
        source=source,
        episode_type=ep_type,
        reference_time=ref_time,
        group_id=group_id,
    )
    return result


async def _tkb_search_impl(
    query: str,
    intent: str = "hybrid",
    point_in_time: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search the temporal knowledge graph."""
    from core.models import IntentType, SearchQuery

    state = await get_state()

    try:
        intent_type = IntentType(intent)
    except ValueError:
        intent_type = IntentType.HYBRID

    pit: datetime | None = None
    if point_in_time:
        try:
            pit = datetime.fromisoformat(point_in_time)
        except ValueError:
            pit = None

    search_query = SearchQuery(
        query=query,
        intent=intent_type,
        point_in_time=pit,
        limit=limit,
    )

    response = await state.query_engine.search(search_query)

    return {
        "query": query,
        "intent": response.query.intent.value,
        "results": [
            {
                "id": r.id,
                "content": r.content,
                "type": r.result_type,
                "valid_at": r.temporal.valid_at.isoformat() if r.temporal and r.temporal.valid_at else None,
                "is_current": r.temporal.is_current if r.temporal else True,
            }
            for r in response.results
        ],
        "total_count": response.total_count,
    }


def _extract_temporal_hint(question: str) -> datetime | None:
    """Extract a temporal reference from a question for point-in-time search.

    Supports patterns like:
    - "в 2023 году", "in 2023", "2023"
    - "в январе 2024", "January 2024"
    - "в 2023-2024" (takes the end of range)
    - "до 2024", "before 2024"

    Returns a datetime at end-of-year/month for the detected period,
    so point-in-time search captures all facts valid up to that moment.
    """
    q = question.lower()

    # "в январе 2024" / "january 2024" / "jan 2024"
    month_ru = {
        "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
        "ма[йя]": 5, "июн": 6, "июл": 7, "август": 8,
        "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
    }
    month_en = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    # Russian month + year
    for pattern, month in month_ru.items():
        m = re.search(rf"{pattern}\w*\s+(\d{{4}})", q)
        if m:
            year = int(m.group(1))
            return datetime(year, month, 28, 23, 59, 59, tzinfo=timezone.utc)

    # English month + year
    for pattern, month in month_en.items():
        m = re.search(rf"{pattern}\w*\s+(\d{{4}})", q)
        if m:
            year = int(m.group(1))
            return datetime(year, month, 28, 23, 59, 59, tzinfo=timezone.utc)

    # Year range "2023-2024" — take end of range
    m = re.search(r"(\d{4})\s*[-–]\s*(\d{4})", q)
    if m:
        year = int(m.group(2))
        return datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    # Standalone year: "в 2023 году", "in 2023", just "2023"
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        year = int(m.group(1))
        return datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    return None


async def _tkb_ask_impl(
    question: str,
    include_timeline: bool = False,
) -> dict[str, Any]:
    """Search the knowledge graph and generate an LLM response.

    Automatically extracts temporal references from the question
    and uses them as point_in_time filters for more accurate results.
    """
    from core.models import IntentType, SearchQuery, SearchResponse, SearchResult

    state = await get_state()

    # Extract temporal hint from question
    temporal_hint = _extract_temporal_hint(question)

    # Primary search: hybrid (semantic + structural)
    search_query = SearchQuery(
        query=question,
        intent=IntentType.HYBRID,
        point_in_time=temporal_hint,
        limit=15,
    )
    search_response = await state.query_engine.search(search_query)

    # If temporal hint detected and few results, do a broader structural search too
    if temporal_hint and len(search_response.results) < 5:
        broad_query = SearchQuery(
            query=question,
            intent=IntentType.STRUCTURAL,
            limit=10,
        )
        broad_response = await state.query_engine.search(broad_query)

        # Merge results, dedup by id
        seen_ids = {r.id for r in search_response.results}
        extra: list[SearchResult] = []
        for r in broad_response.results:
            if r.id not in seen_ids:
                # If temporal hint present, prefer facts from that time period
                if r.temporal and r.temporal.valid_at and temporal_hint:
                    if r.temporal.valid_at <= temporal_hint:
                        extra.append(r)
                        seen_ids.add(r.id)
                else:
                    extra.append(r)
                    seen_ids.add(r.id)

        merged_results = search_response.results + extra
        search_response = SearchResponse(
            query=search_query,
            results=merged_results[:15],
            total_count=len(merged_results),
        )

    result = await state.response_builder.build_response(
        query=question,
        search_response=search_response,
        include_timeline=include_timeline,
    )
    return result


async def _tkb_timeline_impl(entity_id: str) -> dict[str, Any]:
    """Get the full timeline of events for an entity."""
    state = await get_state()
    timeline = await state.neo4j.get_entity_timeline(entity_id)
    return {
        "entity_id": entity_id,
        "events": timeline,
        "total": len(timeline),
    }


async def _tkb_evolution_impl(event_id: str) -> dict[str, Any]:
    """Get the SUPERSEDED_BY chain showing how a fact evolved."""
    state = await get_state()
    chain = await state.neo4j.get_supersession_chain(event_id)
    return {
        "event_id": event_id,
        "chain": chain,
        "total": len(chain),
    }


async def _tkb_stats_impl() -> dict[str, Any]:
    """Get graph statistics."""
    state = await get_state()
    stats = await state.neo4j.get_stats()
    return stats


# --- FastMCP server ---

mcp = FastMCP("TemporalKnowledgeBase")


@mcp.tool()
async def tkb_ingest(
    content: str,
    source: str = "manual",
    episode_type: str = "text",
    reference_time: str | None = None,
    group_id: str | None = None,
) -> dict[str, Any]:
    """Add an episode to the temporal knowledge graph.

    Runs the full 5-stage pipeline: chunk → extract entities/events →
    resolve → store in Neo4j → run invalidation agent.

    Args:
        content: Text content to ingest
        source: Source identifier (e.g. document name, URL)
        episode_type: One of: text, json, chat, document
        reference_time: ISO datetime when the content was created (optional)
        group_id: Group/namespace for organizing episodes (optional)
    """
    return await _tkb_ingest_impl(
        content=content,
        source=source,
        episode_type=episode_type,
        reference_time=reference_time,
        group_id=group_id,
    )


@mcp.tool()
async def tkb_search(
    query: str,
    intent: str = "hybrid",
    point_in_time: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search the temporal knowledge graph for facts.

    Supports three search intents:
    - structural: relationships and structure ("Who works for X?")
    - temporal: changes over time ("What changed in 2024?")
    - hybrid: both combined (default)

    Args:
        query: Natural language search query
        intent: Search intent - structural, temporal, or hybrid
        point_in_time: ISO datetime for point-in-time snapshot (optional)
        limit: Maximum number of results (default 10)
    """
    return await _tkb_search_impl(
        query=query,
        intent=intent,
        point_in_time=point_in_time,
        limit=limit,
    )


@mcp.tool()
async def tkb_ask(
    question: str,
    include_timeline: bool = False,
) -> dict[str, Any]:
    """Ask a question and get an LLM-generated answer grounded in the knowledge graph.

    Performs search + temporal verification + LLM response generation.
    Only uses verified, current facts for the answer.

    Args:
        question: Natural language question
        include_timeline: Include chronological timeline in response
    """
    return await _tkb_ask_impl(
        question=question,
        include_timeline=include_timeline,
    )


@mcp.tool()
async def tkb_timeline(entity_id: str) -> dict[str, Any]:
    """Get the full timeline of events mentioning an entity.

    Shows all temporal events (current and superseded) in chronological order.

    Args:
        entity_id: ID of the entity to get timeline for
    """
    return await _tkb_timeline_impl(entity_id)


@mcp.tool()
async def tkb_evolution(event_id: str) -> dict[str, Any]:
    """Get the SUPERSEDED_BY chain showing how a fact evolved over time.

    Follows the chain from the given event through all its supersessions.

    Args:
        event_id: ID of the starting temporal event
    """
    return await _tkb_evolution_impl(event_id)


@mcp.tool()
async def tkb_stats() -> dict[str, Any]:
    """Get statistics about the temporal knowledge graph.

    Returns counts of entities, temporal events, current events, and episodes.
    """
    return await _tkb_stats_impl()


def main():
    """Entry point for MCP server."""
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

    logger.info("Starting Temporal Knowledge Base MCP Server...")
    mcp.run()


if __name__ == "__main__":
    main()
