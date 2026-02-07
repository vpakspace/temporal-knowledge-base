# Temporal Knowledge Base

## Обзор

Фреймворк для построения **темпоральной базы знаний** на основе **Graphiti** (Zep AI) + **GraphOS** 16-layer architecture.

- **Graphiti** — execution layer ("руки"): Neo4j client, add_episode, hybrid search
- **GraphOS** — architectural layer ("мозг"): 16 слоёв, intent classification, temporal verification

**Расположение**: `~/temporal-knowledge-base/`
**Создан**: 2026-02-07
**Commit**: `dba99d4`
**Тесты**: 33 passed

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
| `tests/` | 33 unit тестов |

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

## Следующие шаги

- [ ] Integration test с реальным Neo4j + OpenAI API
- [ ] Document loaders (PDF, HTML, JSON files)
- [ ] Community detection (Graphiti `build_communities`)
- [ ] MCP server для интеграции с Claude Code
- [ ] GitHub repository
