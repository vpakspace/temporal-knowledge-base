# Temporal Knowledge Base

## Обзор

Фреймворк для построения **темпоральной базы знаний** на основе **Graphiti** (Zep AI) + **GraphOS** 16-layer architecture.

- **Graphiti** — execution layer ("руки"): Neo4j client, add_episode, hybrid search
- **GraphOS** — architectural layer ("мозг"): 16 слоёв, intent classification, temporal verification

**Расположение**: `~/temporal-knowledge-base/`
**Создан**: 2026-02-07
**Commit**: `dba99d4`
**Тесты**: 63 passed (33 unit + 30 integration)

## Технологический стек

- **Python 3.12** (conda)
- **Neo4j 5.x** (Docker: `temporal-kb-neo4j`, порт 7474/7687)
- **graphiti-core 0.26.3** (Zep AI)
- **OpenAI** (gpt-4o-mini для extraction/invalidation, text-embedding-3-small для embeddings)
- **FastAPI** (API сервер, порт 8000)
- **Streamlit** (UI, порт 8501)
- **Pydantic v2** (модели данных)

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
| `core/` | Config (pydantic-settings), models (13 Pydantic), exceptions |
| `storage/` | Neo4j async client (bi-temporal CRUD, point-in-time), vector store |
| `graphiti_adapter/` | Graphiti client wrapper, search recipes (RRF/MMR) |
| `ingestion/` | Pipeline (5 stages), semantic chunker, dual-track extractor |
| `temporal/` | Invalidation agent, entity resolution |
| `retrieval/` | Query engine (intent-aware search) |
| `generation/` | LLM client, temporal verifier (Layer 14), response builder |
| `api/` | FastAPI server (6 endpoints) |
| `ui/` | Streamlit UI (4 tabs: Ingest, Search, Timeline, Stats) |
| `tests/` | 63 тестов (33 unit + 30 integration) |

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
| POST | `/api/search` | Temporal-aware search |
| GET | `/api/timeline/{entity_id}` | Timeline сущности |
| GET | `/api/evolution/{event_id}` | Цепочка SUPERSEDED_BY |
| GET | `/api/stats` | Статистика графа |
| GET | `/health` | Health check |

## Конфигурация

`.env` файл:
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` — Neo4j подключение
- `OPENAI_API_KEY` — для embeddings и LLM extraction
- `LLM_MODEL=gpt-4o-mini`, `EMBEDDING_MODEL=text-embedding-3-small`

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
| `tkb_ingest` | Добавить эпизод в граф знаний | `content`, `source`, `episode_type?`, `reference_time?`, `group_id?` |
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

## Следующие шаги

- [x] Integration test с реальным Neo4j + OpenAI API ✅ (30 тестов)
- [x] GitHub repository ✅ (https://github.com/vpakspace/temporal-knowledge-base)
- [x] API + UI тестирование ✅ (Ingest, Search, Stats работают через Streamlit)
- [x] MCP server для интеграции с Claude Code ✅ (6 tools, 25 unit тестов)
- [x] Auto temporal hint extraction для tkb_ask ✅ (2026-02-08)
- [ ] Document loaders (PDF, HTML, JSON files)
- [ ] Community detection (Graphiti `build_communities`)
