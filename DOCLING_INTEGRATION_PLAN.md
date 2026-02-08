# План интеграции Docling в Temporal Knowledge Base

## Цель

Заменить `pypdf` (только текст) на IBM Docling для извлечения таблиц, формул и графиков из PDF и других документов. Docling — AI-powered библиотека с поддержкой TableFormer (распознавание структуры таблиц), OCR и классификации изображений.

## Архитектурное решение

**Новый модуль `ingestion/document_loader.py`** — централизованный загрузчик документов, используемый и в Streamlit UI, и в FastAPI, и (опционально) в MCP server. Это избегает дублирования логики и обеспечивает единообразную обработку.

```
PDF/DOCX/PPTX/XLSX/HTML
         │
    DoclingLoader          ← НОВЫЙ модуль
         │
    DocumentResult         ← markdown + tables + images + metadata
         │
    ┌────┴────┐
    │         │
Pipeline   Streamlit/API   ← существующие компоненты
```

---

## Фаза 1: Новый модуль `ingestion/document_loader.py`

**Файл**: `ingestion/document_loader.py` (новый)

Создать `DoclingLoader` класс и `DocumentResult` dataclass:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

@dataclass
class DocumentResult:
    """Результат обработки документа через Docling."""
    markdown: str                          # Полный текст в markdown (включая таблицы)
    tables: list[dict] = field(default_factory=list)   # [{caption, markdown, csv, page}]
    images: list[dict] = field(default_factory=list)    # [{caption, page, path}]
    metadata: dict = field(default_factory=dict)        # {pages, format, tables_count, ...}


class DoclingLoader:
    """Загрузчик документов на основе IBM Docling."""

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".md", ".txt"}

    def __init__(self):
        self._converter: DocumentConverter | None = None

    def _get_converter(self) -> DocumentConverter:
        """Lazy initialization — Docling загружает модели (~1-2GB) при первом вызове."""
        if self._converter is None:
            from docling.document_converter import DocumentConverter
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import PdfFormatOption

            pipeline_options = PdfPipelineOptions()
            pipeline_options.generate_picture_images = True

            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        return self._converter

    def load(self, file_path: str | Path) -> DocumentResult:
        """Загрузить документ и извлечь содержимое."""
        path = Path(file_path)

        # Для простых текстовых файлов — без Docling
        if path.suffix.lower() in {".txt", ".md"}:
            return DocumentResult(
                markdown=path.read_text(encoding="utf-8"),
                metadata={"format": path.suffix, "pages": 1}
            )

        converter = self._get_converter()
        result = converter.convert(str(path))
        doc = result.document

        # Извлечение таблиц
        tables = []
        for item, _level in doc.iterate_items():
            if hasattr(item, "export_to_dataframe"):
                df = item.export_to_dataframe()
                tables.append({
                    "caption": getattr(item, "caption", ""),
                    "markdown": df.to_markdown(index=False),
                    "csv": df.to_csv(index=False),
                    "page": getattr(item, "prov", [{}])[0].get("page", None) if hasattr(item, "prov") else None,
                })

        # Извлечение изображений
        images = []
        for item, _level in doc.iterate_items():
            if hasattr(item, "get_image"):
                img = item.get_image(doc)
                if img:
                    images.append({
                        "caption": getattr(item, "caption", ""),
                        "page": getattr(item, "prov", [{}])[0].get("page", None) if hasattr(item, "prov") else None,
                    })

        # Полный markdown
        markdown = doc.export_to_markdown()

        metadata = {
            "format": path.suffix,
            "pages": getattr(doc, "num_pages", None),
            "tables_count": len(tables),
            "images_count": len(images),
        }

        return DocumentResult(
            markdown=markdown,
            tables=tables,
            images=images,
            metadata=metadata,
        )

    def load_bytes(self, data: bytes, filename: str) -> DocumentResult:
        """Загрузить документ из bytes (для file upload)."""
        import tempfile
        path = Path(tempfile.mktemp(suffix=Path(filename).suffix))
        try:
            path.write_bytes(data)
            return self.load(path)
        finally:
            path.unlink(missing_ok=True)
```

**Ключевые решения**:
- Lazy initialization (модели Docling загружаются при первом вызове)
- `load_bytes()` для работы с uploaded files (Streamlit, FastAPI)
- Fallback на простое чтение для `.txt`/`.md` (не нужен Docling)
- `DocumentResult` содержит и markdown, и структурированные таблицы/изображения

---

## Фаза 2: Обновление Streamlit UI

**Файл**: `ui/streamlit_app.py`

1. Заменить функцию `extract_text_from_file()` на использование `DoclingLoader`:

```python
from ingestion.document_loader import DoclingLoader, DocumentResult

_loader = DoclingLoader()

def extract_from_file(uploaded_file) -> DocumentResult | None:
    """Извлечение контента через Docling."""
    try:
        raw = uploaded_file.read()
        return _loader.load_bytes(raw, uploaded_file.name)
    except Exception as e:
        st.error(f"Ошибка обработки файла: {e}")
        return None
```

2. Расширить список поддерживаемых форматов в `st.file_uploader`:
```python
type=["txt", "md", "json", "pdf", "docx", "pptx", "xlsx", "html"]
```

3. Показывать метаданные документа (кол-во таблиц, страниц) в UI после загрузки.

4. Передавать `result.markdown` в API для ingestion (вместо простого text).

---

## Фаза 3: Новый API endpoint для file upload

**Файл**: `api/server.py`

Добавить endpoint `POST /api/ingest/file` для загрузки файлов:

```python
from fastapi import UploadFile, File, Form
from ingestion.document_loader import DoclingLoader

_doc_loader = DoclingLoader()

@app.post("/api/ingest/file")
async def ingest_file(
    file: UploadFile = File(...),
    source: str = Form(None),
    reference_time: str = Form(None),
    group_id: str = Form(None),
):
    """Загрузка и ingestion документа."""
    data = await file.read()
    result = _doc_loader.load_bytes(data, file.filename)

    # Ingestion через существующий pipeline
    episode_result = await pipeline.ingest_episode(
        content=result.markdown,
        source=source or file.filename,
        episode_type="document",
        reference_time=reference_time,
        group_id=group_id,
    )

    return {
        "status": "ok",
        "episode": episode_result,
        "document_stats": result.metadata,
    }
```

---

## Фаза 4: Обновление зависимостей

**Файл**: `requirements.txt`

```diff
- pypdf>=4.0.0
+ docling>=2.0.0
+ python-multipart>=0.0.6
```

- `docling` заменяет `pypdf` (Docling умеет всё что pypdf + таблицы/формулы/изображения)
- `python-multipart` нужен для FastAPI `UploadFile`

---

## Фаза 5: Table-aware chunking

**Файл**: `ingestion/chunker.py`

Обновить `SemanticChunker` для корректной обработки markdown-таблиц — таблица не должна разрезаться на куски:

```python
import re

def _split_preserving_tables(self, text: str) -> list[str]:
    """Разбивает текст на блоки, сохраняя таблицы как атомарные единицы."""
    # Паттерн: блок строк, начинающихся с |
    table_pattern = re.compile(r'((?:^\|.*\|$\n?)+)', re.MULTILINE)

    parts = []
    last_end = 0
    for match in table_pattern.finditer(text):
        # Текст до таблицы
        before = text[last_end:match.start()].strip()
        if before:
            parts.append(before)
        # Таблица целиком
        parts.append(match.group(0).strip())
        last_end = match.end()

    # Текст после последней таблицы
    after = text[last_end:].strip()
    if after:
        parts.append(after)

    return parts
```

Интегрировать `_split_preserving_tables` в метод `chunk()` перед разбивкой на параграфы.

---

## Фаза 6 (опциональная): MCP enhancement

**Файл**: `mcp_server.py`

Добавить опциональный параметр `file_path` в tool `tkb_ingest`:

```python
@mcp.tool()
async def tkb_ingest(
    content: str = "",
    source: str = "unknown",
    episode_type: str = "text",
    reference_time: str | None = None,
    group_id: str | None = None,
    file_path: str | None = None,  # NEW
) -> str:
    """Ingest episode. If file_path is provided, extract content via Docling."""
    if file_path:
        from ingestion.document_loader import DoclingLoader
        loader = DoclingLoader()
        result = loader.load(file_path)
        content = result.markdown
        source = source or file_path
        episode_type = "document"
    # ... existing logic ...
```

Также обновить `mcp_launcher.py` — добавить `file_path` в описание tool.

---

## Фаза 7: Тесты

**Файл**: `tests/test_document_loader.py` (новый)

```python
import pytest
from ingestion.document_loader import DoclingLoader, DocumentResult

class TestDocumentResult:
    def test_defaults(self):
        r = DocumentResult(markdown="test")
        assert r.tables == []
        assert r.images == []
        assert r.metadata == {}

class TestDoclingLoader:
    def test_supported_extensions(self):
        loader = DoclingLoader()
        assert ".pdf" in loader.SUPPORTED_EXTENSIONS
        assert ".docx" in loader.SUPPORTED_EXTENSIONS

    def test_load_txt(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello world")
        loader = DoclingLoader()
        result = loader.load(f)
        assert result.markdown == "Hello world"
        assert result.metadata["format"] == ".txt"

    def test_load_md(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\nContent")
        loader = DoclingLoader()
        result = loader.load(f)
        assert "# Title" in result.markdown

    def test_load_bytes_txt(self):
        loader = DoclingLoader()
        result = loader.load_bytes(b"Hello", "test.txt")
        assert result.markdown == "Hello"
```

Тесты для PDF/DOCX потребуют mock'ов Docling (чтобы не скачивать модели в CI).

---

## Фаза 8 (опциональная): Enrichment metadata в Episode

**Файл**: `core/models.py`

Расширить `metadata` в Episode для хранения информации о таблицах/изображениях:

```python
# При ingestion:
metadata = {
    "docling": True,
    "tables_count": len(result.tables),
    "images_count": len(result.images),
    "pages": result.metadata.get("pages"),
    "format": result.metadata.get("format"),
}
```

Это позволит в будущем фильтровать/искать по типу контента.

---

## Фаза 9: Обновление документации

**Файл**: `.claude/CLAUDE.md`

Добавить секцию о Docling:
- Поддерживаемые форматы
- Архитектура DocumentLoader
- Первый запуск (загрузка моделей)
- Связь с pipeline

---

## Порядок выполнения

| # | Фаза | Файлы | Зависимости |
|---|------|-------|-------------|
| 1 | DocumentLoader модуль | `ingestion/document_loader.py` | — |
| 2 | Streamlit UI | `ui/streamlit_app.py` | Фаза 1 |
| 3 | API endpoint | `api/server.py` | Фаза 1 |
| 4 | Dependencies | `requirements.txt` | — |
| 5 | Table-aware chunking | `ingestion/chunker.py` | — |
| 6 | MCP enhancement | `mcp_server.py`, `mcp_launcher.py` | Фаза 1 |
| 7 | Tests | `tests/test_document_loader.py` | Фаза 1 |
| 8 | Metadata enrichment | `core/models.py` | Фаза 1 |
| 9 | Documentation | `.claude/CLAUDE.md` | Все фазы |

Фазы 1, 4, 5 можно выполнить параллельно. Фазы 6, 8 — опциональные.

## Оценка изменений

- **Новые файлы**: 2 (`document_loader.py`, `test_document_loader.py`)
- **Изменённые файлы**: 5 (`streamlit_app.py`, `server.py`, `requirements.txt`, `chunker.py`, `CLAUDE.md`)
- **Опционально**: 2 (`mcp_server.py`, `mcp_launcher.py`, `models.py`)
- **Обратная совместимость**: Полная — существующий text ingestion не затронут
