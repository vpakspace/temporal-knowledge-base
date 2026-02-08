"""Tests for ingestion.document_loader module.

Tests DocumentResult dataclass and DoclingLoader with:
- Plain text files (.txt, .md) — no Docling needed
- Unsupported formats — ValueError
- load_bytes() for file upload simulation
- Docling integration (mocked to avoid downloading ~1-2GB models in CI)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.document_loader import DoclingLoader, DocumentResult

# --- DocumentResult tests ---


class TestDocumentResult:
    """Tests for DocumentResult dataclass."""

    def test_defaults(self):
        r = DocumentResult(markdown="test content")
        assert r.markdown == "test content"
        assert r.tables == []
        assert r.images == []
        assert r.metadata == {}

    def test_with_tables(self):
        r = DocumentResult(
            markdown="# Report",
            tables=[{"caption": "Table 1", "markdown": "| a | b |", "csv": "a,b", "page": 1}],
            metadata={"tables_count": 1},
        )
        assert len(r.tables) == 1
        assert r.tables[0]["caption"] == "Table 1"
        assert r.metadata["tables_count"] == 1

    def test_with_images(self):
        r = DocumentResult(
            markdown="# Report",
            images=[{"caption": "Figure 1", "page": 2}],
            metadata={"images_count": 1},
        )
        assert len(r.images) == 1
        assert r.images[0]["page"] == 2

    def test_with_all_fields(self):
        r = DocumentResult(
            markdown="# Full doc",
            tables=[{"caption": "T1", "markdown": "| x |", "csv": "x", "page": 1}],
            images=[{"caption": "I1", "page": 3}],
            metadata={"format": ".pdf", "pages": 5, "tables_count": 1, "images_count": 1},
        )
        assert r.metadata["pages"] == 5
        assert r.metadata["format"] == ".pdf"


# --- DoclingLoader tests ---


class TestDoclingLoader:
    """Tests for DoclingLoader class."""

    def test_supported_extensions(self):
        loader = DoclingLoader()
        assert ".pdf" in loader.SUPPORTED_EXTENSIONS
        assert ".docx" in loader.SUPPORTED_EXTENSIONS
        assert ".pptx" in loader.SUPPORTED_EXTENSIONS
        assert ".xlsx" in loader.SUPPORTED_EXTENSIONS
        assert ".html" in loader.SUPPORTED_EXTENSIONS
        assert ".md" in loader.SUPPORTED_EXTENSIONS
        assert ".txt" in loader.SUPPORTED_EXTENSIONS
        # Unsupported
        assert ".exe" not in loader.SUPPORTED_EXTENSIONS
        assert ".zip" not in loader.SUPPORTED_EXTENSIONS

    def test_load_txt(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("Hello world", encoding="utf-8")

        loader = DoclingLoader()
        result = loader.load(f)

        assert result.markdown == "Hello world"
        assert result.metadata["format"] == ".txt"
        assert result.metadata["pages"] == 1
        assert result.tables == []
        assert result.images == []

    def test_load_md(self, tmp_path: Path):
        f = tmp_path / "readme.md"
        f.write_text("# Title\n\nSome **content**.", encoding="utf-8")

        loader = DoclingLoader()
        result = loader.load(f)

        assert "# Title" in result.markdown
        assert "**content**" in result.markdown
        assert result.metadata["format"] == ".md"

    def test_load_unsupported_format(self, tmp_path: Path):
        f = tmp_path / "archive.zip"
        f.write_bytes(b"PK\x03\x04")

        loader = DoclingLoader()
        with pytest.raises(ValueError, match="Unsupported format"):
            loader.load(f)

    def test_load_bytes_txt(self):
        loader = DoclingLoader()
        result = loader.load_bytes(b"Hello from bytes", "note.txt")

        assert result.markdown == "Hello from bytes"
        assert result.metadata["format"] == ".txt"

    def test_load_bytes_md(self):
        loader = DoclingLoader()
        result = loader.load_bytes(b"# Heading\nParagraph", "doc.md")

        assert "# Heading" in result.markdown
        assert result.metadata["format"] == ".md"

    def test_load_bytes_unsupported(self):
        loader = DoclingLoader()
        with pytest.raises(ValueError, match="Unsupported format"):
            loader.load_bytes(b"data", "file.exe")

    def test_load_txt_unicode(self, tmp_path: Path):
        f = tmp_path / "unicode.txt"
        f.write_text("Привет мир! 日本語テスト", encoding="utf-8")

        loader = DoclingLoader()
        result = loader.load(f)

        assert "Привет мир!" in result.markdown
        assert "日本語テスト" in result.markdown

    def test_load_empty_txt(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")

        loader = DoclingLoader()
        result = loader.load(f)

        assert result.markdown == ""

    def test_converter_not_initialized_for_txt(self):
        loader = DoclingLoader()
        loader.load_bytes(b"text", "file.txt")
        assert loader._converter is None  # Docling not needed for .txt


# --- Docling integration tests (mocked) ---


class TestDoclingLoaderWithMock:
    """Tests using mocked Docling converter."""

    def _make_mock_converter(self, markdown="# Mocked", tables=None, images=None, num_pages=3):
        """Create a mock DocumentConverter that returns specified content."""
        mock_converter = MagicMock()

        # Mock document
        mock_doc = MagicMock()
        mock_doc.export_to_markdown.return_value = markdown
        mock_doc.num_pages = num_pages

        # Build items list for iterate_items
        items = []
        if tables:
            for t in tables:
                mock_table = MagicMock()
                mock_table.export_to_dataframe.return_value = t["df"]
                mock_table.caption = t.get("caption", "")
                mock_table.prov = [MagicMock(page_no=t.get("page", 1))]
                # Ensure get_image is not present
                del mock_table.get_image
                items.append((mock_table, 0))

        if images:
            for img in images:
                mock_img = MagicMock()
                # Ensure export_to_dataframe is not present
                del mock_img.export_to_dataframe
                mock_img.get_image.return_value = True
                mock_img.caption = img.get("caption", "")
                mock_img.prov = [MagicMock(page_no=img.get("page", 1))]
                items.append((mock_img, 0))

        mock_doc.iterate_items.return_value = items

        # Mock convert result
        mock_result = MagicMock()
        mock_result.document = mock_doc
        mock_converter.convert.return_value = mock_result

        return mock_converter

    def test_load_pdf_with_tables(self, tmp_path: Path):
        """Test PDF loading extracts tables."""
        import pandas as pd

        f = tmp_path / "report.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        df = pd.DataFrame({"Name": ["Alice", "Bob"], "Score": [90, 85]})
        mock_conv = self._make_mock_converter(
            markdown="# Report\n\n| Name | Score |\n|---|---|\n| Alice | 90 |\n| Bob | 85 |",
            tables=[{"df": df, "caption": "Scores", "page": 1}],
        )

        loader = DoclingLoader()
        loader._converter = mock_conv

        result = loader.load(f)

        assert "Report" in result.markdown
        assert len(result.tables) == 1
        assert result.tables[0]["caption"] == "Scores"
        assert "Alice" in result.tables[0]["csv"]
        assert result.metadata["tables_count"] == 1
        assert result.metadata["pages"] == 3

    def test_load_pdf_with_images(self, tmp_path: Path):
        """Test PDF loading extracts image metadata."""
        f = tmp_path / "with_images.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        mock_conv = self._make_mock_converter(
            markdown="# Doc with image",
            images=[{"caption": "Figure 1", "page": 2}],
        )

        loader = DoclingLoader()
        loader._converter = mock_conv

        result = loader.load(f)

        assert len(result.images) == 1
        assert result.images[0]["caption"] == "Figure 1"
        assert result.images[0]["page"] == 2
        assert result.metadata["images_count"] == 1

    def test_load_pdf_no_content(self, tmp_path: Path):
        """Test PDF with no extractable content."""
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        mock_conv = self._make_mock_converter(markdown="", num_pages=1)
        loader = DoclingLoader()
        loader._converter = mock_conv

        result = loader.load(f)
        assert result.markdown == ""

    def test_load_docx(self, tmp_path: Path):
        """Test DOCX loading."""
        f = tmp_path / "doc.docx"
        f.write_bytes(b"PK\x03\x04 fake docx")

        mock_conv = self._make_mock_converter(
            markdown="# Word Document\n\nParagraph text.",
            num_pages=2,
        )
        loader = DoclingLoader()
        loader._converter = mock_conv

        result = loader.load(f)
        assert "Word Document" in result.markdown
        assert result.metadata["format"] == ".docx"

    def test_load_bytes_pdf(self, tmp_path: Path):
        """Test load_bytes with PDF content."""
        mock_conv = self._make_mock_converter(markdown="# PDF from bytes")

        loader = DoclingLoader()
        loader._converter = mock_conv

        result = loader.load_bytes(b"%PDF-1.4 fake", "upload.pdf")
        assert "PDF from bytes" in result.markdown

    def test_lazy_initialization(self):
        """Test that converter is None until first non-txt call."""
        loader = DoclingLoader()
        assert loader._converter is None

    def test_metadata_completeness(self, tmp_path: Path):
        """Test that metadata contains all expected fields."""
        import pandas as pd

        f = tmp_path / "full.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        df = pd.DataFrame({"col": [1, 2]})
        mock_conv = self._make_mock_converter(
            markdown="content",
            tables=[{"df": df, "caption": "", "page": 1}],
            images=[{"caption": "", "page": 2}],
            num_pages=5,
        )
        loader = DoclingLoader()
        loader._converter = mock_conv

        result = loader.load(f)

        assert result.metadata["format"] == ".pdf"
        assert result.metadata["pages"] == 5
        assert result.metadata["tables_count"] == 1
        assert result.metadata["images_count"] == 1


# --- Chunker table-awareness tests ---


class TestChunkerTableAwareness:
    """Test that SemanticChunker preserves markdown tables."""

    def test_table_not_split(self):
        from ingestion.chunker import SemanticChunker

        table = (
            "| Name | Score |\n"
            "|------|-------|\n"
            "| Alice | 90 |\n"
            "| Bob | 85 |\n"
            "| Charlie | 92 |"
        )
        text = f"Some intro text that is long enough.\n\n{table}\n\nSome outro text."

        chunker = SemanticChunker(max_chunk_size=50, min_chunk_size=10)
        chunks = chunker.chunk(text)

        # Table should appear as one chunk, not split
        table_chunks = [c for c in chunks if "|" in c and "Name" in c]
        assert len(table_chunks) == 1
        assert "Alice" in table_chunks[0]
        assert "Charlie" in table_chunks[0]

    def test_text_around_table_split_normally(self):
        from ingestion.chunker import SemanticChunker

        long_text = "A" * 200
        table = "| a | b |\n|---|---|\n| 1 | 2 |"
        text = f"{long_text}\n\n{table}\n\n{long_text}"

        chunker = SemanticChunker(max_chunk_size=100, min_chunk_size=10)
        chunks = chunker.chunk(text)

        # Should have multiple chunks
        assert len(chunks) >= 3

    def test_is_table_detection(self):
        from ingestion.chunker import SemanticChunker

        assert SemanticChunker._is_table("| a | b |\n|---|---|\n| 1 | 2 |")
        assert not SemanticChunker._is_table("regular text")
        assert not SemanticChunker._is_table("| single line |")

    def test_no_tables_works_as_before(self):
        from ingestion.chunker import SemanticChunker

        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunker = SemanticChunker(max_chunk_size=1000)
        chunks = chunker.chunk(text)

        assert len(chunks) == 1
        assert "First" in chunks[0]
