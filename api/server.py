"""FastAPI server implementing GraphOS Layers 1-4 (Foundation).

Endpoints:
- POST /api/ingest     — Ingest an episode
- POST /api/search     — Search the knowledge graph
- GET  /api/timeline/{entity_id} — Get entity timeline
- GET  /api/evolution/{event_id} — Get fact evolution chain
- GET  /api/stats      — Graph statistics
- GET  /health         — Health check
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

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
from core.models import EpisodeType, IntentType, SearchQuery

logger = logging.getLogger(__name__)

# Global state
_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down all components."""
    settings = get_settings()

    neo4j = Neo4jClient(settings.neo4j)
    await neo4j.connect()

    vector_store = VectorStore(settings.openai)
    llm = LLMClient(settings.openai)
    graphiti = GraphitiClient(settings)
    await graphiti.connect()

    entity_resolver = EntityResolver(neo4j, vector_store)
    invalidation_agent = InvalidationAgent(neo4j, vector_store, llm, settings)
    verifier = TemporalVerifier(neo4j)

    pipeline = IngestionPipeline(
        graphiti=graphiti,
        neo4j=neo4j,
        vector_store=vector_store,
        llm=llm,
        invalidation_agent=invalidation_agent,
        entity_resolver=entity_resolver,
        settings=settings,
    )
    query_engine = QueryEngine(graphiti, neo4j, llm)
    response_builder = ResponseBuilder(llm, verifier)

    _state["neo4j"] = neo4j
    _state["graphiti"] = graphiti
    _state["pipeline"] = pipeline
    _state["query_engine"] = query_engine
    _state["response_builder"] = response_builder

    logger.info("Temporal Knowledge Base API started")
    yield

    await graphiti.close()
    await neo4j.close()
    logger.info("Temporal Knowledge Base API stopped")


app = FastAPI(
    title="Temporal Knowledge Base",
    description="Temporal knowledge graph API based on Graphiti + GraphOS",
    version="0.1.0",
    lifespan=lifespan,
)


# --- Request/Response models ---

class IngestRequest(BaseModel):
    content: str
    source: str = "manual"
    episode_type: str = "text"
    reference_time: datetime | None = None
    group_id: str | None = None


class SearchRequest(BaseModel):
    query: str
    intent: str = "hybrid"
    point_in_time: datetime | None = None
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None
    entity_types: list[str] | None = None
    limit: int = 10
    include_timeline: bool = False


# --- Endpoints ---

@app.get("/health")
async def health():
    return {"status": "ok", "service": "temporal-knowledge-base"}


@app.post("/api/ingest")
async def ingest_episode(req: IngestRequest):
    """Ingest an episode through the full pipeline."""
    pipeline: IngestionPipeline = _state["pipeline"]
    try:
        ep_type = EpisodeType(req.episode_type)
    except ValueError:
        ep_type = EpisodeType.TEXT

    try:
        result = await pipeline.ingest_episode(
            content=req.content,
            source=req.source,
            episode_type=ep_type,
            reference_time=req.reference_time,
            group_id=req.group_id,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search")
async def search(req: SearchRequest):
    """Search the temporal knowledge graph."""
    query_engine: QueryEngine = _state["query_engine"]
    response_builder: ResponseBuilder = _state["response_builder"]

    try:
        intent = IntentType(req.intent)
    except ValueError:
        intent = IntentType.HYBRID

    search_query = SearchQuery(
        query=req.query,
        intent=intent,
        point_in_time=req.point_in_time,
        time_range_start=req.time_range_start,
        time_range_end=req.time_range_end,
        entity_types=req.entity_types,
        limit=req.limit,
    )

    try:
        search_response = await query_engine.search(search_query)
        result = await response_builder.build_response(
            query=req.query,
            search_response=search_response,
            include_timeline=req.include_timeline,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/timeline/{entity_id}")
async def get_timeline(entity_id: str):
    """Get full timeline for an entity."""
    query_engine: QueryEngine = _state["query_engine"]
    try:
        timeline = await query_engine.get_timeline(entity_id)
        return {"success": True, "data": timeline}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/evolution/{event_id}")
async def get_evolution(event_id: str):
    """Get fact evolution (supersession chain)."""
    query_engine: QueryEngine = _state["query_engine"]
    try:
        chain = await query_engine.get_evolution(event_id)
        return {"success": True, "data": chain}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Get graph statistics."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        stats = await neo4j.get_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
