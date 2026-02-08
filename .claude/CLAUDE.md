# Temporal Knowledge Base

## Обзор

Фреймворк для построения **темпоральной базы знаний** на основе **Graphiti** (Zep AI) + **GraphOS** 16-layer architecture.

- **Graphiti** — execution layer ("руки"): Neo4j client, add_episode, hybrid search
- **GraphOS** — architectural layer ("мозг"): 16 слоёв, intent classification, temporal verification

**Расположение**: `~/temporal-knowledge-base/`
**Создан**: 2026-02-07
**Latest commit**: `b15fffd`
**Тесты**: 117 unit + 30 integration = 147 total
**README**: https://github.com/vpakspace/temporal-knowledge-base

## Технологический стек

- **Python 3.12** (conda)
- **Neo4j 5.x** (Docker: `temporal-kb-neo4j`, порт 7474/7687)
- **graphiti-core 0.26.3** (Zep AI)
- **OpenAI** (gpt-4o-mini для extraction/invalidation, text-embedding-3-small для embeddings)
- **FastAPI** (API сервер, порт 8000)
- **Streamlit** (UI, порт 8501)
- **Pydantic v2** (модели данных)
- **IBM Docling** (document processing: PDF, DOCX, PPTX, XLSX, HTML — tables, images, OCR)

## Архитектура

```
Layers 1-4:  FastAPI + Streamlit (Intent Classification, Query Decomposition)
Layers 12-16: Response Builder + Temporal Verifier (Layer 14)
Layers 8-11: Query Engine (Hybrid Search: RRF/MMR + Temporal Query Engine)
Layer 5:     Ingestion Pipeline (5 stages: load → chunk → extract → resolve → write)
Layers 6-7:  Neo4j (bi-temporal) + Vector Store (OpenAI embeddings)
             └─ Graphiti Core (add_episode, search, invalidation)
```

## Ключевые концепции

### Bi-temporal модель
- **Valid Time** (`valid_at`) — когда факт истинен в реальности
- **Transaction Time** (`created_at`) — когда система узнала о факте
- **Invalidation** (`invalid_at`) — когда факт был заменён новым
- **SUPERSEDED_BY** edges — цепочки эволюции знаний

### Dual-Track Storage
- **Entity Layer**: структурный граф (Entity nodes + RELATES_TO edges)
- **Temporal Event Layer**: атомарные факты с bi-temporal метаданными

### Invalidation Agent (3 фильтра + LLM)
1. Temporal overlap — перекрытие временных периодов
2. Shared entities — общие упомянутые сущности
3. Semantic similarity > 0.5 — cosine similarity embeddings
4. LLM confirmation — финальная проверка через LLM

## Структура проекта

| Модуль | Описание |
|--------|----------|
| `core/` | Config (pydantic-settings), models (13 Pydantic), exceptions, TTL cache, webhooks |
| `storage/` | Neo4j async client (bi-temporal CRUD, point-in-time), vector store |
| `graphiti_adapter/` | Graphiti client wrapper, search recipes (RRF/MMR) |
| `ingestion/` | Pipeline (5 stages), semantic chunker (table-aware), dual-track extractor, DoclingLoader |
| `temporal/` | Invalidation agent, entity resolution |
| `retrieval/` | Query engine (intent-aware search) |
| `generation/` | LLM client, temporal verifier (Layer 14), response builder |
| `api/` | FastAPI server (8 endpoints) |
| `ui/` | Streamlit UI (4 tabs: Ingest, Search, Timeline, Stats) |
| `tests/` | 113 тестов (83 unit + 30 integration) |

## Запуск

```bash
# 1. Neo4j
docker compose up -d

# 2. API (http://localhost:8000)
./run_api.sh

# 3. UI (http://localhost:8501)
./run_streamlit.sh
```

## API Endpoints

| Method | Path | Описание |
|--------|------|----------|
| POST | `/api/ingest` | Ingest episode через pipeline |
| POST | `/api/ingest/file` | Upload & ingest document via Docling (PDF/DOCX/PPTX/XLSX/HTML) |
| POST | `/api/ingest/batch` | Batch ingest (JSON array), per-episode error reporting |
| POST | `/api/search` | Temporal-aware search (auto temporal hints) |
| POST | `/api/ask` | Question + LLM answer (mirrors MCP `tkb_ask`) |
| GET | `/api/timeline/{entity_id}` | Timeline сущности |
| GET | `/api/evolution/{event_id}` | Цепочка SUPERSEDED_BY |
| GET | `/api/entities` | Список всех entities (для autocomplete) |
| GET | `/api/entities/{entity_id}` | Детали entity (relationships, event counts) |
| GET | `/api/graph` | Nodes + edges для визуализации графа |
| GET | `/api/communities` | Community nodes or lightweight clusters |
| POST | `/api/communities/build` | Build communities via Graphiti (LLM summarization) |
| GET | `/api/contradictions` | Supersession chains, hotspots, invalidation log |
| GET | `/api/export` | Export full graph data as JSON |
| POST | `/api/import` | Import graph data from JSON export (MERGE by ID) |
| GET | `/api/webhooks` | List registered webhooks |
| POST | `/api/webhooks` | Register webhook URL |
| DELETE | `/api/webhooks?url=` | Remove webhook |
| GET | `/api/metrics` | Request/pipeline metrics (counters, latencies, uptime) |
| GET | `/api/cache/stats` | Cache hit/miss statistics (LLM + embeddings) |
| POST | `/api/cache/clear` | Clear all caches |
| GET | `/api/stats` | Статистика графа |
| GET | `/health` | Health check |

## Конфигурация

`.env` файл:
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` — Neo4j подключение
- `OPENAI_API_KEY` — для embeddings и LLM extraction
- `LLM_MODEL=gpt-4o-mini`, `EMBEDDING_MODEL=text-embedding-3-small`
- `APP_API_KEY` — API authentication (empty = auth disabled)

## Graphiti API

- `graphiti-core 0.26.3` — `Graphiti.__init__` принимает `LLMConfig` (не прямые params)
- `add_episode(name, episode_body, source_description, reference_time, source=EpisodeType)`
- `search(query, num_results, group_ids, search_filter)`
- `retrieve_episodes(reference_time, last_n, group_ids)`
- Типы эпизодов: `message`, `json`, `text`
- SearchFilters: `ComparisonOperator.equals/greater_than_equal/less_than_equal`
- `OpenAIClient(config=LLMConfig(api_key=..., model=...))` — не прямые kwargs

## NotebookLM

Notebook зарегистрирован в библиотеке NotebookLM MCP:
- **ID**: `temporal-knowledge-base-graphi`
- **Name**: "Temporal Knowledge Base (Graphiti + GraphOS)"
- **URL**: `https://notebooklm.google.com/notebook/d751931b-6723-41f4-a071-3c787a2d51d3`
- **Topics**: Graphiti, GraphOS, bi-temporal KG, invalidation agents, Neo4j, hybrid search

## Тестирование

```bash
# Unit тесты только (без внешних зависимостей)
pytest tests/ -m "not integration"

# Integration тесты (требуют Neo4j + OpenAI API key)
pytest tests/ -m integration

# Все тесты
pytest tests/
```

### Integration тесты (30 тестов)

| Файл | Тесты | Что проверяет |
|------|-------|---------------|
| `test_integration_neo4j.py` | 10 | CRUD entities/events, supersession chains, point-in-time, timeline, stats |
| `test_integration_openai.py` | 11 | Embeddings (single/batch/similarity), LLM generation, intent classification, contradiction detection |
| `test_integration_extraction.py` | 5 | Dual-track extraction (entities, relationships, fact types, Russian text) |
| `test_integration_pipeline.py` | 4 | E2E pipeline: ingest → extract → resolve → store → search → respond |

### Bugfixes найденные при тестировании

- **`get_supersession_chain`**: Cypher `UNWIND nodes(path)` возвращал дубликаты при path length 0 → добавлен `WITH DISTINCT te`
- **`GraphitiClient.add_episode`**: `datetime.now()` (naive) → `datetime.now(UTC)` (timezone-aware), Graphiti v0.26.3 требует UTC
- **`EntityResolver.resolve_batch`**: Graphiti nodes с `id: None` проникали через fulltext search → добавлена проверка `existing.get("id")`
- **`IngestionPipeline`**: Graphiti Stage 1 ошибки теперь не блокируют наш temporal layer (stages 2-5)

## MCP Server (Claude Code integration)

MCP server предоставляет 6 tools для прямой работы с TKB из Claude Code.

**Файл**: `mcp_server.py` (корень проекта)
**Запуск**: `python3 mcp_server.py`
**Регистрация**: `~/.claude.json` → `mcpServers.temporal-kb`

### MCP Tools

| Tool | Описание | Ключевые параметры |
|------|----------|--------------------|
| `tkb_ingest` | Добавить эпизод в граф знаний | `content`, `source`, `episode_type?`, `reference_time?`, `group_id?`, `file_path?` |
| `tkb_search` | Temporal-aware поиск фактов | `query`, `intent?` (hybrid/structural/temporal), `point_in_time?`, `limit?` |
| `tkb_ask` | Поиск + LLM ответ (auto temporal hint extraction) | `question`, `include_timeline?` |
| `tkb_timeline` | Timeline сущности | `entity_id` |
| `tkb_evolution` | Цепочка SUPERSEDED_BY | `event_id` |
| `tkb_stats` | Статистика графа | — |

### Архитектура MCP

- **Lazy singleton**: ресурсы (Neo4j, Graphiti, OpenAI) инициализируются при первом вызове tool
- **Async**: все tools async (Neo4j и OpenAI клиенты async)
- **Reuse**: используются существующие классы (IngestionPipeline, QueryEngine, ResponseBuilder)
- **Testable**: `_impl` функции тестируются отдельно от FastMCP обёрток
- **ENV**: `OPENAI_API_KEY` из .env (python-dotenv), `NEO4J_*` из MCP env config

### Тесты MCP

```bash
PYTHONPATH=. pytest tests/test_mcp_server.py -v
# 25 passed (all _impl functions + _extract_temporal_hint + enhanced ask tests)
```

### Auto Temporal Hint Extraction (2026-02-08)

`tkb_ask` автоматически извлекает даты из вопросов и использует как `point_in_time`:
- `_extract_temporal_hint()` — regex для рус/англ ("в 2023 году", "January 2024", "2023-2024")
- `_tkb_ask_impl()` — передаёт hint в SearchQuery, делает broad search при <5 результатах
- `build_search_filters()` — конвертирует `point_in_time` → `valid_at <= point` для Graphiti edges

**Изменённые файлы**: `mcp_server.py`, `graphiti_adapter/search_recipes.py`, `mcp_launcher.py`

### Graphiti Data Architecture

Факты хранятся в **двух** местах:
- **Graphiti edges** (основное) — через `add_episode()`, поля: `fact`, `valid_at`, `uuid`
- **TemporalEvent nodes** (наш слой) — кастомные ноды для dual-track storage

`point_in_time` фильтрация должна работать на **обоих** уровнях:
- Edges: `build_search_filters()` → `SearchFilters(valid_at=DateFilter(...))`
- TemporalEvent: `neo4j.query_point_in_time()`

### Shared Modules

**`core/temporal_hints.py`** — shared temporal hint extraction (MCP + FastAPI):
- `extract_temporal_hint(question)` → regex рус/англ date extraction
- Used by: `mcp_server.py` (backward-compat wrapper), `api/server.py` (direct import)

### Streamlit UI Features (7 tabs)

- **Ingest tab**: paste text, batch JSON, OR file upload (TXT/MD/JSON/PDF/DOCX/PPTX/XLSX/HTML, max 10MB)
- **Search tab**: calls `/api/ask` with auto temporal hints
- **Entities tab**: entity table with type filter, name search, detail panel (relationships, events)
- **Timeline tab**: entity autocomplete dropdown + fact evolution chains
- **Graph tab**: interactive knowledge graph visualization (`streamlit-agraph`, color-coded by entity type)
- **Contradictions tab**: supersession chains, entity hotspots (most contradicted), invalidation log
- **Stats tab**: graph statistics, export/import (JSON download + upload)

**File upload pipeline**: `st.file_uploader → DoclingLoader.load_bytes() → /api/ingest`
- PDF/DOCX/PPTX/XLSX/HTML: IBM Docling (tables, images, OCR)
- TXT/MD: plain text read (no Docling)
- Auto-detect episode type from extension (.json→json, .pdf/.docx/.pptx/.xlsx/.html→document)
- Shows document stats after upload (tables, images, pages)

### Docling Integration

**Module**: `ingestion/document_loader.py` — `DoclingLoader` + `DocumentResult`

**Supported formats**: PDF, DOCX, PPTX, XLSX, HTML, TXT, MD
**Features**: TableFormer (table extraction), OCR, image classification
**Lazy init**: Models (~1-2GB) downloaded on first call to `_get_converter()`

```python
from ingestion.document_loader import DoclingLoader
loader = DoclingLoader()
result = loader.load("report.pdf")      # From file
result = loader.load_bytes(data, "f.pdf") # From bytes
print(result.markdown)   # Full markdown with tables
print(result.tables)     # [{caption, markdown, csv, page}]
print(result.images)     # [{caption, page}]
print(result.metadata)   # {format, pages, tables_count, images_count}
```

**Table-aware chunking**: `SemanticChunker` preserves markdown tables (`| ... |`) as atomic units — never splits tables across chunks.

## Следующие шаги

- [x] Integration test с реальным Neo4j + OpenAI API ✅ (30 тестов)
- [x] GitHub repository ✅ (https://github.com/vpakspace/temporal-knowledge-base)
- [x] API + UI тестирование ✅ (Ingest, Search, Stats работают через Streamlit)
- [x] MCP server для интеграции с Claude Code ✅ (6 tools, 25 unit тестов)
- [x] Auto temporal hint extraction для tkb_ask ✅ (2026-02-08)
- [x] File upload (TXT/MD/JSON/PDF) ✅ `827bda3`
- [x] `/api/ask` endpoint (MCP parity) ✅ `827bda3`
- [x] Shared `core/temporal_hints.py` ✅ `827bda3`
- [x] Docling integration (PDF, DOCX, PPTX, XLSX, HTML) ✅ `957ff0a`
- [x] Table-aware chunking ✅
- [x] POST /api/ingest/file endpoint ✅
- [x] MCP tkb_ingest file_path parameter ✅
- [x] Document metadata enrichment ✅
- [x] Docling installed and tested (PDF with table + chart) ✅ `4a6ecdc`
- [x] README.md with installation guide ✅ `b15fffd`
- [x] Community detection (Graphiti `build_communities` + lightweight clusters) ✅

## План улучшений (2026-02-08)

### Высокий приоритет

| # | Задача | Усилие | Описание |
|---|--------|--------|----------|
| ~~1~~ | ~~Graph Visualization в UI~~ | ~~1-2ч~~ | ~~DONE~~ Entity autocomplete в Timeline tab, Graph tab (`streamlit-agraph`) |
| ~~2~~ | ~~Рефакторинг дубликата search/ask~~ | ~~30мин~~ | ~~DONE~~ `QueryEngine.search_with_fallback()` — дубликат из 3 мест устранён |
| ~~3~~ | ~~CI/CD Pipeline~~ | ~~30мин~~ | ~~DONE~~ `.github/workflows/ci.yml` — pytest + black + isort |
| ~~4~~ | ~~API Authentication~~ | ~~1ч~~ | ~~DONE~~ `api/auth.py`, `X-API-Key` header, `APP_API_KEY` env var |

### Средний приоритет

| # | Задача | Усилие | Описание |
|---|--------|--------|----------|
| ~~5~~ | ~~Batch Ingestion~~ | ~~2ч~~ | ~~DONE~~ `POST /api/ingest/batch`, per-episode errors, Batch JSON tab in UI |
| ~~6~~ | ~~Entity Explorer tab~~ | ~~2-3ч~~ | ~~DONE~~ Entities tab: table + type filter + name search + detail panel (relationships, events) |
| ~~7~~ | ~~Export / Import~~ | ~~2ч~~ | ~~DONE~~ `GET /api/export`, `POST /api/import` (MERGE by ID), Export/Import UI в Stats tab |
| ~~8~~ | ~~Contradiction Dashboard~~ | ~~2ч~~ | ~~DONE~~ Contradictions tab: chains, entity hotspots, invalidation log + `/api/contradictions` |
| ~~9~~ | ~~Docker Compose full stack~~ | ~~1ч~~ | ~~DONE~~ Dockerfile + api/ui services, healthchecks, env_file |

### Низкий приоритет

| # | Задача | Описание |
|---|--------|----------|
| ~~10~~ | ~~Community Detection~~ | ~~DONE~~ Graphiti `build_communities` + lightweight BFS clusters, `/api/communities`, Graph tab UI |
| ~~11~~ | ~~Webhook Notifications~~ | ~~DONE~~ `core/webhooks.py`, auto-fire on supersession, CRUD API, UI в Stats tab |
| ~~12~~ | ~~Multi-language Hints~~ | ~~SKIP~~ Английский + русский уже поддерживаются в `core/temporal_hints.py` |
| ~~13~~ | ~~Caching Layer~~ | ~~DONE~~ TTLCache for LLM intent + embeddings, `/api/cache/stats`, UI stats |
| ~~14~~ | ~~Metrics / Monitoring~~ | ~~DONE~~ `core/metrics.py`, middleware latency tracking, pipeline/search counters, `/api/metrics`, UI |

### Рекомендуемый порядок
`~~#2~~ → ~~#1~~ → #3 → #4 → #6 → #9 → #5 → #7`
