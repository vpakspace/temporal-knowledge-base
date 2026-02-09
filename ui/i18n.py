"""Internationalization (i18n) for Temporal Knowledge Base UI.

Supports: English (en), Russian (ru).
"""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    # --- Page ---
    "page_title": {
        "en": "Temporal Knowledge Base",
        "ru": "Темпоральная База Знаний",
    },
    "page_caption": {
        "en": "Graphiti + GraphOS | Bi-temporal Knowledge Graph",
        "ru": "Graphiti + GraphOS | Би-темпоральный Граф Знаний",
    },
    "lang_label": {
        "en": "Language / Язык",
        "ru": "Язык / Language",
    },
    # --- Tab names ---
    "tab_ingest": {"en": "Ingest", "ru": "Загрузка"},
    "tab_search": {"en": "Search", "ru": "Поиск"},
    "tab_entities": {"en": "Entities", "ru": "Сущности"},
    "tab_timeline": {"en": "Timeline", "ru": "Хронология"},
    "tab_graph": {"en": "Graph", "ru": "Граф"},
    "tab_contradictions": {"en": "Contradictions", "ru": "Противоречия"},
    "tab_stats": {"en": "Stats", "ru": "Статистика"},
    # --- Common ---
    "api_not_running": {
        "en": "API server not running. Start with: uvicorn api.server:app",
        "ru": "API сервер не запущен. Запустите: uvicorn api.server:app",
    },
    "api_error": {"en": "API error: {e}", "ru": "Ошибка API: {e}"},
    "invalid_json": {"en": "Invalid JSON", "ru": "Некорректный JSON"},
    "invalid_json_file": {"en": "Invalid JSON file", "ru": "Некорректный JSON файл"},
    "loading": {"en": "Loading...", "ru": "Загрузка..."},
    # --- Tab 1: Ingest ---
    "ingest_header": {"en": "Ingest Episode", "ru": "Загрузка эпизода"},
    "input_method": {"en": "Input method", "ru": "Способ ввода"},
    "paste_text": {"en": "Paste text", "ru": "Вставить текст"},
    "upload_file": {"en": "Upload file", "ru": "Загрузить файл"},
    "batch_json": {"en": "Batch (JSON)", "ru": "Пакетный (JSON)"},
    "batch_json_help": {
        "en": (
            "Paste a JSON array of episodes. Each item: "
            '`{"content": "...", "source": "...", "episode_type": "text"}`'
        ),
        "ru": (
            "Вставьте JSON-массив эпизодов. Каждый элемент: "
            '`{"content": "...", "source": "...", "episode_type": "text"}`'
        ),
    },
    "batch_json_label": {"en": "Batch JSON", "ru": "Пакетный JSON"},
    "ingest_batch_btn": {"en": "Ingest Batch", "ru": "Загрузить пакет"},
    "json_must_be_array": {
        "en": "JSON must be an array of objects",
        "ru": "JSON должен быть массивом объектов",
    },
    "starting_batch": {
        "en": "Starting batch ingestion...",
        "ru": "Запуск пакетной загрузки...",
    },
    "done": {"en": "Done!", "ru": "Готово!"},
    "total": {"en": "Total", "ru": "Всего"},
    "succeeded": {"en": "Succeeded", "ru": "Успешно"},
    "failed": {"en": "Failed", "ru": "Ошибок"},
    "content_label": {"en": "Content", "ru": "Содержание"},
    "content_placeholder": {
        "en": "Paste text, JSON, or document content...",
        "ru": "Вставьте текст, JSON или содержимое документа...",
    },
    "source_label": {"en": "Source", "ru": "Источник"},
    "type_label": {"en": "Type", "ru": "Тип"},
    "group_id_label": {"en": "Group ID (optional)", "ru": "ID группы (опционально)"},
    "upload_file_label": {"en": "Upload file", "ru": "Загрузить файл"},
    "upload_help": {
        "en": "Supported: TXT, MD, JSON, PDF, DOCX, PPTX, XLSX, HTML (max {max_mb} MB)",
        "ru": "Поддерживаются: TXT, MD, JSON, PDF, DOCX, PPTX, XLSX, HTML (макс. {max_mb} МБ)",
    },
    "file_too_large": {
        "en": "File too large ({size:.1f} MB). Max: {max_mb} MB",
        "ru": "Файл слишком большой ({size:.1f} МБ). Макс.: {max_mb} МБ",
    },
    "extracted_chars": {
        "en": "Extracted {count:,} characters from {name}",
        "ru": "Извлечено {count:,} символов из {name}",
    },
    "tables": {"en": "tables", "ru": "таблиц"},
    "images": {"en": "images", "ru": "изображений"},
    "pages": {"en": "pages", "ru": "страниц"},
    "preview_content": {"en": "Preview content", "ru": "Предпросмотр"},
    "no_extractable_text": {
        "en": "Document has no extractable text (may be image-based)",
        "ru": "В документе нет извлекаемого текста (возможно, только изображения)",
    },
    "doc_processing_failed": {
        "en": "Document processing failed: {e}",
        "ru": "Ошибка обработки документа: {e}",
    },
    "ingest_btn": {"en": "Ingest", "ru": "Загрузить"},
    "processing_episode": {
        "en": "Processing episode...",
        "ru": "Обработка эпизода...",
    },
    "episode_ingested": {
        "en": "Episode ingested!",
        "ru": "Эпизод загружен!",
    },
    "entities": {"en": "Entities", "ru": "Сущности"},
    "events": {"en": "Events", "ru": "События"},
    "relations": {"en": "Relations", "ru": "Связи"},
    "invalidated": {"en": "Invalidated", "ru": "Устарело"},
    # --- Tab 2: Search ---
    "search_header": {"en": "Temporal Search", "ru": "Темпоральный поиск"},
    "query_label": {"en": "Query", "ru": "Запрос"},
    "query_placeholder": {
        "en": "What changed in 2024?",
        "ru": "Что изменилось в 2024?",
    },
    "intent_label": {"en": "Intent", "ru": "Интент"},
    "results_label": {"en": "Results", "ru": "Результатов"},
    "include_timeline": {"en": "Include timeline", "ru": "Включить хронологию"},
    "search_btn": {"en": "Search", "ru": "Поиск"},
    "searching": {"en": "Searching...", "ru": "Поиск..."},
    "answer": {"en": "Answer", "ru": "Ответ"},
    "no_answer": {"en": "No answer", "ru": "Нет ответа"},
    "based_on_facts": {
        "en": "Based on {count} verified facts",
        "ru": "На основе {count} проверенных фактов",
    },
    "sources": {"en": "Sources", "ru": "Источники"},
    "timeline": {"en": "Timeline", "ru": "Хронология"},
    # --- Tab 3: Entities ---
    "entity_explorer": {"en": "Entity Explorer", "ru": "Обозреватель сущностей"},
    "no_entities_yet": {
        "en": "No entities yet. Ingest some data first.",
        "ru": "Сущностей пока нет. Сначала загрузите данные.",
    },
    "search_by_name": {"en": "Search by name", "ru": "Поиск по имени"},
    "type_to_filter": {"en": "Type to filter...", "ru": "Введите для фильтрации..."},
    "filter_by_type": {"en": "Filter by type", "ru": "Фильтр по типу"},
    "x_of_y_entities": {
        "en": "{filtered} of {total} entities",
        "ru": "{filtered} из {total} сущностей",
    },
    "entity_details": {"en": "Entity Details", "ru": "Детали сущности"},
    "select_entity_inspect": {
        "en": "Select entity to inspect",
        "ru": "Выберите сущность для просмотра",
    },
    "loading_details": {"en": "Loading details...", "ru": "Загрузка деталей..."},
    "total_events": {"en": "Total Events", "ru": "Всего событий"},
    "current_events": {"en": "Current Events", "ru": "Текущие события"},
    "relationships": {"en": "Relationships", "ru": "Связи"},
    "canonical_name": {"en": "Canonical name", "ru": "Каноническое имя"},
    "valid_at": {"en": "Valid at", "ru": "Действительно с"},
    "no_relationships": {
        "en": "No relationships found",
        "ru": "Связи не найдены",
    },
    # --- Tab 4: Timeline ---
    "entity_timeline": {"en": "Entity Timeline", "ru": "Хронология сущности"},
    "select_entity": {"en": "Select entity", "ru": "Выберите сущность"},
    "choose_entity": {"en": "Choose an entity...", "ru": "Выберите сущность..."},
    "or_enter_id": {"en": "Or enter ID", "ru": "Или введите ID"},
    "uuid_placeholder": {"en": "UUID", "ru": "UUID"},
    "get_timeline_btn": {"en": "Get Timeline", "ru": "Показать хронологию"},
    "loading_timeline": {"en": "Loading timeline...", "ru": "Загрузка хронологии..."},
    "superseded": {"en": "superseded", "ru": "устарело"},
    "no_events_entity": {
        "en": "No events found for this entity",
        "ru": "Событий для этой сущности не найдено",
    },
    "fact_evolution": {"en": "Fact Evolution", "ru": "Эволюция факта"},
    "event_id_label": {"en": "Event ID", "ru": "ID события"},
    "enter_event_uuid": {
        "en": "Enter event UUID",
        "ru": "Введите UUID события",
    },
    "get_evolution_btn": {"en": "Get Evolution", "ru": "Показать эволюцию"},
    "loading_evolution": {
        "en": "Loading evolution chain...",
        "ru": "Загрузка цепочки эволюции...",
    },
    "current_status": {"en": "CURRENT", "ru": "ТЕКУЩИЙ"},
    "superseded_status": {"en": "Superseded", "ru": "Устарело"},
    "step_n": {"en": "Step {n}", "ru": "Шаг {n}"},
    # --- Tab 5: Graph ---
    "knowledge_graph": {"en": "Knowledge Graph", "ru": "Граф знаний"},
    "load_graph_btn": {"en": "Load Graph", "ru": "Загрузить граф"},
    "loading_graph": {"en": "Loading graph data...", "ru": "Загрузка данных графа..."},
    "no_entities_graph": {
        "en": "No entities in the graph yet. Ingest some data first.",
        "ru": "В графе пока нет сущностей. Сначала загрузите данные.",
    },
    "n_entities_m_rels": {
        "en": "{nodes} entities, {edges} relationships",
        "ru": "{nodes} сущностей, {edges} связей",
    },
    "legend": {"en": "Legend", "ru": "Легенда"},
    "communities_clusters": {
        "en": "Communities / Clusters",
        "ru": "Сообщества / Кластеры",
    },
    "detect_clusters_btn": {"en": "Detect Clusters", "ru": "Найти кластеры"},
    "detecting_communities": {
        "en": "Detecting communities...",
        "ru": "Поиск сообществ...",
    },
    "no_clusters": {
        "en": "No clusters found. Ingest more data to form connections.",
        "ru": "Кластеры не найдены. Загрузите больше данных для формирования связей.",
    },
    "source_clusters": {
        "en": "Source: {source} | {count} clusters",
        "ru": "Источник: {source} | {count} кластеров",
    },
    "graphiti_communities": {
        "en": "Graphiti Communities",
        "ru": "Сообщества Graphiti",
    },
    "connected_components": {
        "en": "Connected Components",
        "ru": "Связные компоненты",
    },
    "n_members": {"en": "{n} members", "ru": "{n} участников"},
    "build_communities_caption": {
        "en": "Build Graphiti communities (uses LLM for summarization)",
        "ru": "Построить сообщества Graphiti (использует LLM для резюмирования)",
    },
    "build_communities_btn": {
        "en": "Build Communities (LLM)",
        "ru": "Построить сообщества (LLM)",
    },
    "building_communities": {
        "en": "Building communities via Graphiti (may take a minute)...",
        "ru": "Построение сообществ через Graphiti (может занять минуту)...",
    },
    "built_communities": {
        "en": "Built {communities} communities with {edges} membership edges",
        "ru": "Построено {communities} сообществ с {edges} связями участия",
    },
    # --- Tab 6: Contradictions ---
    "contradiction_dashboard": {
        "en": "Contradiction Dashboard",
        "ru": "Панель противоречий",
    },
    "contradiction_caption": {
        "en": "Supersession chains, entity hotspots, and invalidation log",
        "ru": "Цепочки замены, горячие точки сущностей и журнал устаревания",
    },
    "load_contradictions_btn": {
        "en": "Load Contradictions",
        "ru": "Загрузить противоречия",
    },
    "loading_contradictions": {
        "en": "Loading contradiction data...",
        "ru": "Загрузка данных о противоречиях...",
    },
    "supersession_chains": {
        "en": "Supersession Chains",
        "ru": "Цепочки замены",
    },
    "entity_hotspots": {"en": "Entity Hotspots", "ru": "Горячие точки"},
    "invalidated_facts": {
        "en": "Invalidated Facts",
        "ru": "Устаревшие факты",
    },
    "entities_most_superseded": {
        "en": "Entities with the most superseded facts",
        "ru": "Сущности с наибольшим числом заменённых фактов",
    },
    "old_facts_replaced": {
        "en": "Old facts replaced by new facts",
        "ru": "Старые факты, заменённые новыми",
    },
    "old_superseded": {"en": "Old (superseded):", "ru": "Старый (заменённый):"},
    "new_replacement": {"en": "New (replacement):", "ru": "Новый (замена):"},
    "current_yes": {"en": "Yes", "ru": "Да"},
    "current_no": {"en": "No", "ru": "Нет"},
    "current_label": {"en": "Current", "ru": "Текущий"},
    "no_supersession_chains": {
        "en": "No supersession chains found. All facts are current.",
        "ru": "Цепочек замены не найдено. Все факты актуальны.",
    },
    "invalidation_log": {
        "en": "Invalidation Log",
        "ru": "Журнал устаревания",
    },
    "recent_invalidations": {
        "en": "Recent fact invalidations (newest first)",
        "ru": "Недавние устаревания фактов (сначала новые)",
    },
    "replaced_by": {"en": "Replaced by", "ru": "Заменён на"},
    "no_replacement": {"en": "(no replacement)", "ru": "(без замены)"},
    # --- Tab 7: Stats ---
    "graph_statistics": {"en": "Graph Statistics", "ru": "Статистика графа"},
    "refresh_stats_btn": {"en": "Refresh Stats", "ru": "Обновить"},
    "episodes": {"en": "Episodes", "ru": "Эпизоды"},
    "current_superseded_progress": {
        "en": "{current} current / {superseded} superseded",
        "ru": "{current} текущих / {superseded} устаревших",
    },
    "cache_statistics": {"en": "Cache Statistics", "ru": "Статистика кэша"},
    "cache_caption": {
        "en": "In-memory TTL cache for OpenAI API calls (LLM intent classification, embeddings)",
        "ru": "TTL-кэш в памяти для вызовов OpenAI API (классификация интентов, эмбеддинги)",
    },
    "refresh_cache_btn": {"en": "Refresh Cache Stats", "ru": "Обновить кэш"},
    "llm_cache": {
        "en": "LLM Cache (intent classification)",
        "ru": "LLM кэш (классификация интентов)",
    },
    "embedding_cache": {"en": "Embedding Cache", "ru": "Кэш эмбеддингов"},
    "entries": {"en": "Entries", "ru": "Записей"},
    "hit_rate": {"en": "Hit Rate", "ru": "Попаданий"},
    "hits_misses": {
        "en": "Hits: {hits}, Misses: {misses}",
        "ru": "Попаданий: {hits}, Промахов: {misses}",
    },
    "clear_caches_btn": {"en": "Clear Caches", "ru": "Очистить кэш"},
    "caches_cleared": {"en": "Caches cleared", "ru": "Кэш очищен"},
    "api_metrics": {"en": "API Metrics", "ru": "Метрики API"},
    "metrics_caption": {
        "en": "Request counts, latencies, pipeline throughput (resets on API restart)",
        "ru": "Счётчики запросов, задержки, пропускная способность (сброс при перезапуске API)",
    },
    "refresh_metrics_btn": {"en": "Refresh Metrics", "ru": "Обновить метрики"},
    "uptime": {"en": "Uptime", "ru": "Время работы"},
    "total_requests": {"en": "Total Requests", "ru": "Всего запросов"},
    "errors": {"en": "Errors", "ru": "Ошибки"},
    "ingestions": {"en": "Ingestions", "ru": "Загрузок"},
    "entities_extracted": {
        "en": "Entities Extracted",
        "ru": "Извлечено сущностей",
    },
    "events_extracted": {
        "en": "Events Extracted",
        "ru": "Извлечено событий",
    },
    "searches": {"en": "Searches", "ru": "Поисков"},
    "results_returned": {
        "en": "Results Returned",
        "ru": "Результатов возвращено",
    },
    "latency_ms": {"en": "Latency (ms)", "ru": "Задержка (мс)"},
    "export_import": {"en": "Export / Import", "ru": "Экспорт / Импорт"},
    "export_btn": {"en": "Export Graph Data", "ru": "Экспортировать граф"},
    "exporting": {"en": "Exporting...", "ru": "Экспорт..."},
    "download_json_btn": {"en": "Download JSON", "ru": "Скачать JSON"},
    "import_json_label": {"en": "Import JSON", "ru": "Импортировать JSON"},
    "unknown_version": {
        "en": "Unknown export version, may not be compatible",
        "ru": "Неизвестная версия экспорта, возможна несовместимость",
    },
    "confirm_import_btn": {"en": "Confirm Import", "ru": "Подтвердить импорт"},
    "importing": {"en": "Importing...", "ru": "Импорт..."},
    "imported_counts": {
        "en": "Imported: {entities} entities, {events} events, {episodes} episodes, {rels} relationships",
        "ru": "Импортировано: {entities} сущностей, {events} событий, {episodes} эпизодов, {rels} связей",
    },
    "webhook_notifications": {
        "en": "Webhook Notifications",
        "ru": "Уведомления (Webhooks)",
    },
    "webhook_caption": {
        "en": "Get notified when facts are superseded (contradictions detected)",
        "ru": "Получайте уведомления при замене фактов (обнаружении противоречий)",
    },
    "remove_btn": {"en": "Remove", "ru": "Удалить"},
    "no_webhooks": {
        "en": "No webhooks configured.",
        "ru": "Вебхуки не настроены.",
    },
    "add_webhook": {"en": "Add Webhook", "ru": "Добавить вебхук"},
    "webhook_url_label": {"en": "Webhook URL", "ru": "URL вебхука"},
    "webhook_name_label": {"en": "Name (optional)", "ru": "Название (опционально)"},
    "register_webhook_btn": {
        "en": "Register Webhook",
        "ru": "Зарегистрировать вебхук",
    },
    "webhook_registered": {
        "en": "Webhook registered: {url}",
        "ru": "Вебхук зарегистрирован: {url}",
    },
    "enter_webhook_url": {
        "en": "Please enter a webhook URL",
        "ru": "Пожалуйста, введите URL вебхука",
    },
    # --- DataFrame column headers ---
    "col_name": {"en": "Name", "ru": "Имя"},
    "col_type": {"en": "Type", "ru": "Тип"},
    "col_id": {"en": "ID", "ru": "ID"},
    "col_superseded_facts": {
        "en": "Superseded Facts",
        "ru": "Заменённые факты",
    },
    "col_endpoint": {"en": "Endpoint", "ru": "Эндпоинт"},
    "col_count": {"en": "Count", "ru": "Кол-во"},
    "col_avg": {"en": "Avg", "ru": "Среднее"},
    # --- Clear Database ---
    "clear_database": {"en": "Clear Database", "ru": "Очистить базу данных"},
    "clear_database_caption": {
        "en": "Permanently delete ALL nodes and relationships from Neo4j",
        "ru": "Безвозвратно удалить ВСЕ узлы и связи из Neo4j",
    },
    "clear_confirm_text": {
        "en": "Type DELETE to confirm",
        "ru": "Введите DELETE для подтверждения",
    },
    "clear_btn": {"en": "Clear All Data", "ru": "Удалить все данные"},
    "clearing_database": {
        "en": "Clearing database...",
        "ru": "Очистка базы данных...",
    },
    "database_cleared": {
        "en": "Deleted {nodes} nodes and {rels} relationships",
        "ru": "Удалено {nodes} узлов и {rels} связей",
    },
    "clear_confirm_wrong": {
        "en": "Please type DELETE to confirm",
        "ru": "Пожалуйста, введите DELETE для подтверждения",
    },
}


def get_translator(lang: str):
    """Return a translator function for the given language."""

    def t(key: str, **kwargs) -> str:
        entry = TRANSLATIONS.get(key, {})
        text = entry.get(lang, entry.get("en", key))
        if kwargs:
            text = text.format(**kwargs)
        return text

    return t
