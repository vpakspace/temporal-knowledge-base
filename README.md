# Temporal Knowledge Base

Bi-temporal knowledge graph framework built on [Graphiti](https://github.com/getzep/graphiti) (Zep AI) and the GraphOS 16-layer architecture. Ingest text, documents, and structured data into a Neo4j-backed temporal graph with automatic entity resolution, fact invalidation, and hybrid search.

## Key Features

- **Bi-temporal model** — every fact tracks both *valid time* (when true in reality) and *transaction time* (when the system learned it), with automatic invalidation chains (`SUPERSEDED_BY`)
- **Dual-track storage** — entity layer (structural graph) + temporal event layer (atomic facts with bi-temporal metadata)
- **Hybrid search** — combines vector similarity (OpenAI embeddings) with structural graph traversal, temporal filtering, and RRF/MMR fusion
- **Document processing** — IBM Docling extracts tables, images, and text from PDF, DOCX, PPTX, XLSX, HTML with TableFormer and OCR
- **Table-aware chunking** — markdown tables are treated as atomic units and never split across chunks
- **Auto temporal hints** — natural language questions like "What was OpenAI's valuation in 2023?" automatically extract temporal filters
- **Three interfaces** — REST API (FastAPI), Web UI (Streamlit), and MCP server (Claude Code integration)

## Architecture

```
Layers 1-4:   FastAPI + Streamlit (Intent Classification, Query Decomposition)
Layers 12-16: Response Builder + Temporal Verifier (Layer 14)
Layers 8-11:  Query Engine (Hybrid Search: RRF/MMR + Temporal Query Engine)
Layer 5:      Ingestion Pipeline (5 stages: load → chunk → extract → resolve → write)
Layers 6-7:   Neo4j (bi-temporal) + Vector Store (OpenAI embeddings)
              └─ Graphiti Core (add_episode, search, invalidation)
```

## Project Structure

```
temporal-knowledge-base/
├── core/                    # Config (pydantic-settings), models (13 Pydantic), exceptions
├── storage/                 # Neo4j async client (bi-temporal CRUD), vector store
├── graphiti_adapter/        # Graphiti client wrapper, search recipes (RRF/MMR)
├── ingestion/               # Pipeline (5 stages), semantic chunker, DoclingLoader
├── temporal/                # Invalidation agent (3 filters + LLM), entity resolution
├── retrieval/               # Query engine (intent-aware search)
├── generation/              # LLM client, temporal verifier, response builder
├── api/                     # FastAPI server (8 endpoints)
├── ui/                      # Streamlit UI (4 tabs)
├── tests/                   # 83 unit + 30 integration = 113 tests
├── mcp_server.py            # MCP server (6 tools for Claude Code)
├── mcp_launcher.py          # Lightweight MCP proxy (instant startup)
├── docker-compose.yml       # Neo4j 5-community
├── run_api.sh               # Start FastAPI
├── run_streamlit.sh         # Start Streamlit
└── requirements.txt
```

## Prerequisites

- **Python 3.11+** (tested on 3.12)
- **Docker** and **Docker Compose** (for Neo4j)
- **OpenAI API key** (for embeddings and LLM extraction)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/vpakspace/temporal-knowledge-base.git
cd temporal-knowledge-base
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note on Docling**: The `docling` package downloads ML models (~1-2 GB) to `~/.cache/huggingface/` on first use. This happens automatically when you first process a PDF/DOCX/PPTX/XLSX/HTML file.

### 4. Start Neo4j

```bash
docker compose up -d
```

This starts a Neo4j 5 Community container with APOC plugin:
- **Browser**: http://localhost:7474
- **Bolt**: bolt://localhost:7687
- **Credentials**: `neo4j` / `temporal_kb_2026`

Wait for Neo4j to become healthy:

```bash
docker compose ps   # STATUS should show "healthy"
```

### 5. Configure environment

Create a `.env` file in the project root:

```bash
cat > .env << 'EOF'
# Required
OPENAI_API_KEY=sk-your-openai-api-key

# Optional (defaults shown)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=temporal_kb_2026
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4o-mini
EOF
```

### 6. Verify installation

```bash
# Run unit tests (no external dependencies required)
pytest tests/ -m "not integration" -q

# Run integration tests (requires Neo4j + OpenAI API key)
pytest tests/ -m integration -q
```

## Usage

### Start the API server

```bash
./run_api.sh
# or
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

API available at http://localhost:8000. Interactive docs at http://localhost:8000/docs.

### Start the Web UI

In a separate terminal:

```bash
./run_streamlit.sh
# or
streamlit run ui/streamlit_app.py --server.port 8501
```

UI available at http://localhost:8501 with four tabs:

| Tab | Description |
|-----|-------------|
| **Ingest** | Paste text or upload files (TXT, MD, JSON, PDF, DOCX, PPTX, XLSX, HTML) |
| **Search** | Ask questions with automatic temporal hint extraction |
| **Timeline** | View entity timelines and fact evolution chains |
| **Stats** | Graph statistics (entities, events, episodes) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ingest` | Ingest a text episode into the knowledge graph |
| `POST` | `/api/ingest/file` | Upload and ingest a document via Docling |
| `POST` | `/api/search` | Temporal-aware hybrid search |
| `POST` | `/api/ask` | Ask a question — search + LLM-generated answer |
| `GET` | `/api/timeline/{entity_id}` | Get the timeline of an entity |
| `GET` | `/api/evolution/{event_id}` | Get the SUPERSEDED_BY chain of a fact |
| `GET` | `/api/stats` | Graph statistics |
| `GET` | `/health` | Health check |

### Example: Ingest an episode

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "OpenAI raised $6.6B at a $157B valuation in October 2024.",
    "source": "tech-news",
    "episode_type": "text"
  }'
```

### Example: Ask a question

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was OpenAI valuation in 2024?"
  }'
```

The temporal hint ("2024") is automatically extracted and used as a `point_in_time` filter.

### Example: Upload a document

```bash
curl -X POST http://localhost:8000/api/ingest/file \
  -F "file=@report.pdf" \
  -F "source=quarterly-report"
```

Supports PDF, DOCX, PPTX, XLSX, and HTML via IBM Docling.

## MCP Server (Claude Code Integration)

The project includes an MCP server providing 6 tools for direct use from Claude Code.

### Tools

| Tool | Description |
|------|-------------|
| `tkb_ingest` | Add an episode to the knowledge graph (text or file) |
| `tkb_search` | Temporal-aware fact search |
| `tkb_ask` | Ask a question — search + LLM answer with auto temporal hints |
| `tkb_timeline` | Get the timeline of an entity |
| `tkb_evolution` | Get the SUPERSEDED_BY chain |
| `tkb_stats` | Graph statistics |

### Setup

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "temporal-kb": {
      "command": "python3",
      "args": ["mcp_launcher.py"],
      "cwd": "/path/to/temporal-knowledge-base",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "temporal_kb_2026"
      }
    }
  }
}
```

> **Why `mcp_launcher.py`?** The launcher is a lightweight proxy (~0.02s startup) that responds to health checks instantly and lazy-loads the real FastMCP server in the background. This prevents Claude Code timeouts caused by heavy imports (Graphiti, OpenAI, Neo4j).

## Bi-Temporal Model

Every fact in the knowledge graph has three temporal dimensions:

| Dimension | Field | Description |
|-----------|-------|-------------|
| **Valid Time** | `valid_at` | When the fact is true in reality |
| **Transaction Time** | `created_at` | When the system learned about the fact |
| **Invalidation** | `invalid_at` | When the fact was superseded by a newer one |

### Invalidation Agent

When a new fact contradicts an existing one, the invalidation agent applies three filters plus LLM confirmation:

1. **Temporal overlap** — do the time periods overlap?
2. **Shared entities** — do they mention the same entities?
3. **Semantic similarity** > 0.5 — cosine similarity of embeddings
4. **LLM confirmation** — final check via LLM

Old facts are linked to their replacements via `SUPERSEDED_BY` edges, creating evolution chains.

## Document Processing (Docling)

IBM Docling provides AI-powered document understanding:

| Format | Features |
|--------|----------|
| PDF | TableFormer (table structure recognition), OCR, image classification |
| DOCX | Full text + table extraction |
| PPTX | Slide text + tables |
| XLSX | Spreadsheet → markdown tables |
| HTML | Structured content extraction |
| TXT, MD | Direct read (no Docling needed) |

### Programmatic usage

```python
from ingestion.document_loader import DoclingLoader

loader = DoclingLoader()

# From file path
result = loader.load("report.pdf")
print(result.markdown)   # Full markdown with tables
print(result.tables)     # [{"caption": ..., "markdown": ..., "csv": ..., "page": ...}]
print(result.images)     # [{"caption": ..., "page": ...}]
print(result.metadata)   # {"format": ".pdf", "pages": 12, "tables_count": 3, "images_count": 2}

# From bytes (file upload)
result = loader.load_bytes(raw_bytes, "report.pdf")
```

## Testing

```bash
# Unit tests only (no external dependencies)
pytest tests/ -m "not integration" -q

# Integration tests (requires running Neo4j + OpenAI API key)
pytest tests/ -m integration -q

# All tests
pytest tests/ -q

# With coverage
pytest tests/ -m "not integration" --cov=. --cov-report=term-missing
```

### Test breakdown

| File | Tests | What it covers |
|------|-------|----------------|
| `test_models.py` | 13 | Pydantic models, enums, serialization |
| `test_mcp_server.py` | 25 | MCP tool implementations, temporal hint extraction |
| `test_document_loader.py` | 25 | DoclingLoader, DocumentResult, format support |
| `test_chunker.py` | 8 | Semantic chunking, table-aware splitting |
| `test_vector_store.py` | 5 | Vector store operations |
| `test_resolution.py` | 7 | Entity resolution |
| `test_integration_neo4j.py` | 10 | Neo4j CRUD, supersession chains, point-in-time |
| `test_integration_openai.py` | 11 | Embeddings, LLM generation, intent classification |
| `test_integration_extraction.py` | 5 | Dual-track extraction pipeline |
| `test_integration_pipeline.py` | 4 | End-to-end: ingest → extract → search → respond |

## Configuration Reference

All settings can be configured via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `temporal_kb_2026` | Neo4j password |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `OPENAI_LLM_MODEL` | `gpt-4o-mini` | LLM model for extraction/generation |
| `OPENAI_LLM_TEMPERATURE` | `0.0` | LLM temperature |
| `APP_INVALIDATION_SIMILARITY_THRESHOLD` | `0.5` | Min similarity for invalidation |
| `APP_DEFAULT_SEARCH_LIMIT` | `10` | Default search result limit |

## Tech Stack

- **[Graphiti](https://github.com/getzep/graphiti)** 0.26+ — temporal knowledge graph engine (Zep AI)
- **[Neo4j](https://neo4j.com/)** 5.x — graph database (Community Edition, Docker)
- **[OpenAI](https://platform.openai.com/)** — `gpt-4o-mini` for extraction/generation, `text-embedding-3-small` for embeddings
- **[IBM Docling](https://github.com/DS4SD/docling)** — AI-powered document conversion (PDF, DOCX, PPTX, XLSX, HTML)
- **[FastAPI](https://fastapi.tiangolo.com/)** — async REST API
- **[Streamlit](https://streamlit.io/)** — web UI
- **[FastMCP](https://github.com/jlowin/fastmcp)** — MCP server for Claude Code
- **[Pydantic](https://docs.pydantic.dev/) v2** — data models and settings

## License

MIT
