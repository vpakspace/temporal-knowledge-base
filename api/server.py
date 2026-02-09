"""FastAPI server implementing GraphOS Layers 1-4 (Foundation).

Endpoints:
- POST /api/ingest     — Ingest an episode
- POST /api/ingest/file — Upload & ingest document via Docling
- POST /api/search     — Search the knowledge graph
- POST /api/ask        — Ask question with auto temporal extraction + LLM answer
- GET  /api/timeline/{entity_id} — Get entity timeline
- GET  /api/evolution/{event_id} — Get fact evolution chain
- GET  /api/entities   — List all entities
- GET  /api/graph      — Get graph data for visualization
- GET  /api/cache/stats — Cache hit/miss statistics
- POST /api/cache/clear — Clear all caches
- GET  /api/metrics    — Request/pipeline metrics
- POST /api/clear      — Clear all data from Neo4j (irreversible)
- GET  /api/stats      — Graph statistics
- GET  /health         — Health check
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from api.auth import verify_api_key
from core.config import get_settings
from core.metrics import metrics
from core.models import EpisodeType, IntentType
from core.temporal_hints import extract_temporal_hint
from core.webhooks import WebhookManager
from generation.llm_client import LLMClient
from generation.response_builder import ResponseBuilder
from generation.temporal_verifier import TemporalVerifier
from graphiti_adapter.client import GraphitiClient
from ingestion.chunker import split_large_content
from ingestion.document_loader import DoclingLoader
from ingestion.pipeline import IngestionPipeline
from retrieval.query_engine import QueryEngine
from storage.neo4j_client import Neo4jClient
from storage.vector_store import VectorStore
from temporal.invalidation_agent import InvalidationAgent
from temporal.resolution import EntityResolver

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

    webhook_manager = WebhookManager()
    entity_resolver = EntityResolver(neo4j, vector_store)
    invalidation_agent = InvalidationAgent(
        neo4j, vector_store, llm, settings, webhook_manager=webhook_manager
    )
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
    _state["webhooks"] = webhook_manager
    _state["pipeline"] = pipeline
    _state["query_engine"] = query_engine
    _state["response_builder"] = response_builder
    _state["doc_loader"] = DoclingLoader()
    _state["llm"] = llm
    _state["vector_store"] = vector_store

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


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track request count, latency, and errors per endpoint."""
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000

    path = request.url.path
    metrics.inc("requests_total")
    metrics.timing(f"latency:{path}", duration_ms)

    if response.status_code >= 400:
        metrics.inc("errors_total")
        metrics.inc(f"errors:{response.status_code}")

    return response


# All /api/* endpoints require API key (when APP_API_KEY is set)
_auth = [Depends(verify_api_key)]


# --- Request/Response models ---


class WebhookRequest(BaseModel):
    url: str
    name: str = ""
    events: list[str] | None = None


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


class AskRequest(BaseModel):
    question: str
    include_timeline: bool = False


# --- Endpoints ---


@app.get("/health")
async def health():
    return {"status": "ok", "service": "temporal-knowledge-base"}


@app.post("/api/ingest", dependencies=_auth)
async def ingest_episode(req: IngestRequest):
    """Ingest an episode through the full pipeline."""
    pipeline: IngestionPipeline = _state["pipeline"]
    try:
        ep_type = EpisodeType(req.episode_type)
    except ValueError:
        ep_type = EpisodeType.TEXT

    reference_time = req.reference_time or datetime.now(UTC)

    try:
        result = await pipeline.ingest_episode(
            content=req.content,
            source=req.source,
            episode_type=ep_type,
            reference_time=reference_time,
            group_id=req.group_id,
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.exception("Ingest failed for source=%s", req.source)
        return {"success": False, "error": str(e)}


@app.post("/api/ingest/file", dependencies=_auth)
async def ingest_file(
    file: UploadFile = File(...),
    source: str = Form(None),
    reference_time: str = Form(None),
    group_id: str = Form(None),
):
    """Upload and ingest a document via Docling.

    Supports PDF, DOCX, PPTX, XLSX, HTML, TXT, MD.
    Extracts text (including tables) and runs through the ingestion pipeline.
    """
    pipeline: IngestionPipeline = _state["pipeline"]
    doc_loader: DoclingLoader = _state["doc_loader"]

    data = await file.read()
    try:
        doc_result = doc_loader.load_bytes(data, file.filename or "upload")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Document processing failed")
        raise HTTPException(status_code=500, detail=f"Document processing failed: {e}")

    if not doc_result.markdown.strip():
        raise HTTPException(status_code=400, detail="Document has no extractable text")

    ref_time = None
    if reference_time:
        try:
            ref_time = datetime.fromisoformat(reference_time)
        except ValueError:
            ref_time = None

    # Enrich episode metadata with document info
    episode_metadata = {
        "docling": True,
        "tables_count": doc_result.metadata.get("tables_count", 0),
        "images_count": doc_result.metadata.get("images_count", 0),
        "pages": doc_result.metadata.get("pages"),
        "format": doc_result.metadata.get("format"),
    }

    try:
        src = source or file.filename or "file_upload"
        ref = ref_time or datetime.now(UTC)

        # Split large documents into multiple episodes (Zep recommends <=10K chars)
        parts = split_large_content(doc_result.markdown, src)

        if len(parts) > 1:
            logger.info(
                "Large document split into %d parts (%d chars total)",
                len(parts),
                len(doc_result.markdown),
            )

        results = []
        for part_content, part_source in parts:
            r = await pipeline.ingest_episode(
                content=part_content,
                source=part_source,
                episode_type=EpisodeType.DOCUMENT,
                reference_time=ref,
                group_id=group_id,
                metadata=episode_metadata,
            )
            results.append(r)

        return {
            "success": True,
            "data": results[0] if len(results) == 1 else results,
            "parts": len(parts),
            "document_stats": doc_result.metadata,
        }
    except Exception as e:
        logger.exception("Ingest failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ingest/batch", dependencies=_auth)
async def ingest_batch(episodes: list[IngestRequest]):
    """Ingest multiple episodes in one request.

    Processes sequentially. Returns per-episode results with errors.
    """
    pipeline: IngestionPipeline = _state["pipeline"]
    results: list[dict] = []

    for i, req in enumerate(episodes):
        try:
            ep_type = EpisodeType(req.episode_type)
        except ValueError:
            ep_type = EpisodeType.TEXT

        try:
            result = await pipeline.ingest_episode(
                content=req.content,
                source=req.source,
                episode_type=ep_type,
                reference_time=req.reference_time or datetime.now(UTC),
                group_id=req.group_id,
            )
            results.append({"index": i, "success": True, "data": result})
        except Exception as e:
            logger.exception("Batch ingest failed for episode %d", i)
            results.append({"index": i, "success": False, "error": str(e)})

    succeeded = sum(1 for r in results if r["success"])
    return {
        "success": True,
        "total": len(episodes),
        "succeeded": succeeded,
        "failed": len(episodes) - succeeded,
        "results": results,
    }


@app.post("/api/search", dependencies=_auth)
async def search(req: SearchRequest):
    """Search the temporal knowledge graph.

    Automatically extracts temporal references from the query
    (e.g. '2023', 'в январе 2024') and uses them as point-in-time
    filters when no explicit point_in_time is provided.
    """
    query_engine: QueryEngine = _state["query_engine"]
    response_builder: ResponseBuilder = _state["response_builder"]

    try:
        intent = IntentType(req.intent)
    except ValueError:
        intent = IntentType.HYBRID

    # Auto-extract temporal hint if no explicit point_in_time provided
    point_in_time = req.point_in_time
    if point_in_time is None:
        point_in_time = extract_temporal_hint(req.query)

    try:
        search_response = await query_engine.search_with_fallback(
            query=req.query,
            point_in_time=point_in_time,
            intent=intent,
            limit=req.limit,
        )

        result = await response_builder.build_response(
            query=req.query,
            search_response=search_response,
            include_timeline=req.include_timeline,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ask", dependencies=_auth)
async def ask_question(req: AskRequest):
    """Ask a question with auto temporal extraction and LLM-generated answer.

    Same logic as MCP tkb_ask: extracts temporal hints from the question,
    performs hybrid + broad fallback search, builds LLM response.
    """
    query_engine: QueryEngine = _state["query_engine"]
    response_builder: ResponseBuilder = _state["response_builder"]

    temporal_hint = extract_temporal_hint(req.question)

    try:
        search_response = await query_engine.search_with_fallback(
            query=req.question,
            point_in_time=temporal_hint,
        )

        result = await response_builder.build_response(
            query=req.question,
            search_response=search_response,
            include_timeline=req.include_timeline,
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.exception("Ask failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/timeline/{entity_id}", dependencies=_auth)
async def get_timeline(entity_id: str):
    """Get full timeline for an entity."""
    query_engine: QueryEngine = _state["query_engine"]
    try:
        timeline = await query_engine.get_timeline(entity_id)
        return {"success": True, "data": timeline}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/evolution/{event_id}", dependencies=_auth)
async def get_evolution(event_id: str):
    """Get fact evolution (supersession chain)."""
    query_engine: QueryEngine = _state["query_engine"]
    try:
        chain = await query_engine.get_evolution(event_id)
        return {"success": True, "data": chain}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/entities", dependencies=_auth)
async def list_entities():
    """List all entities in the knowledge graph."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        entities = await neo4j.get_all_entities()
        return {"success": True, "data": entities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/entities/{entity_id}", dependencies=_auth)
async def get_entity_details(entity_id: str):
    """Get entity details with relationships and event counts."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        details = await neo4j.get_entity_details(entity_id)
        if not details:
            raise HTTPException(status_code=404, detail="Entity not found")
        return {"success": True, "data": details}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph", dependencies=_auth)
async def get_graph():
    """Get graph data (nodes + edges) for visualization."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        graph = await neo4j.get_graph_data()
        return {"success": True, "data": graph}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/communities", dependencies=_auth)
async def get_communities():
    """Get existing Community nodes (built by Graphiti) or lightweight clusters."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        communities = await neo4j.get_communities()
        if communities:
            return {"success": True, "source": "graphiti", "data": communities}
        # Fallback to lightweight connected components
        clusters = await neo4j.get_entity_clusters()
        return {"success": True, "source": "clusters", "data": clusters}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/communities/build", dependencies=_auth)
async def build_communities():
    """Build communities using Graphiti label propagation + LLM summarization."""
    graphiti: GraphitiClient = _state["graphiti"]
    try:
        result = await graphiti.build_communities()
        return {"success": True, "data": result}
    except Exception as e:
        logger.exception("Community build failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/contradictions", dependencies=_auth)
async def get_contradictions():
    """Get supersession chains, entity hotspots, and invalidation log."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        data = await neo4j.get_contradictions()
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/webhooks", dependencies=_auth)
async def list_webhooks():
    """List registered webhooks."""
    wm: WebhookManager = _state["webhooks"]
    return {"success": True, "data": wm.list_webhooks()}


@app.post("/api/webhooks", dependencies=_auth)
async def add_webhook(req: WebhookRequest):
    """Register a webhook URL for event notifications."""
    wm: WebhookManager = _state["webhooks"]
    webhook = wm.add_webhook(url=req.url, events=req.events, name=req.name)
    return {"success": True, "data": webhook}


@app.delete("/api/webhooks", dependencies=_auth)
async def remove_webhook(url: str):
    """Remove a webhook by URL."""
    wm: WebhookManager = _state["webhooks"]
    removed = wm.remove_webhook(url)
    if not removed:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"success": True}


@app.get("/api/export", dependencies=_auth)
async def export_graph():
    """Export full graph data as JSON."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        data = await neo4j.export_all()
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/import", dependencies=_auth)
async def import_graph(data: dict):
    """Import graph data from JSON export. Merges by ID (idempotent)."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        counts = await neo4j.import_all(data)
        return {"success": True, "data": counts}
    except Exception as e:
        logger.exception("Import failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics", dependencies=_auth)
async def get_metrics():
    """Get request/pipeline metrics (counters, latencies, uptime)."""
    return {"success": True, "data": metrics.snapshot()}


@app.get("/api/cache/stats", dependencies=_auth)
async def get_cache_stats():
    """Get cache hit/miss statistics for LLM and embedding caches."""
    llm: LLMClient = _state["llm"]
    vs: VectorStore = _state["vector_store"]
    return {
        "success": True,
        "data": {
            "llm": llm.cache.stats(),
            "embeddings": vs.cache.stats(),
        },
    }


@app.post("/api/cache/clear", dependencies=_auth)
async def clear_caches():
    """Clear all caches."""
    llm: LLMClient = _state["llm"]
    vs: VectorStore = _state["vector_store"]
    llm.cache.clear()
    vs.cache.clear()
    return {"success": True}


@app.post("/api/clear", dependencies=_auth)
async def clear_database():
    """Delete ALL nodes and relationships from Neo4j. Irreversible."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        counts = await neo4j.clear_database()
        return {"success": True, "data": counts}
    except Exception as e:
        logger.exception("Clear database failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats", dependencies=_auth)
async def get_stats():
    """Get graph statistics."""
    neo4j: Neo4jClient = _state["neo4j"]
    try:
        stats = await neo4j.get_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
