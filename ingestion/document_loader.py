"""Document loader based on IBM Docling.

Provides unified document processing for PDF, DOCX, PPTX, XLSX, HTML
with table extraction (TableFormer), OCR, and image classification.

Usage:
    loader = DoclingLoader()
    result = loader.load("report.pdf")
    print(result.markdown)      # Full markdown with tables
    print(result.tables)        # Structured table data
    print(result.metadata)      # Page count, format, etc.

    # From bytes (file upload)
    result = loader.load_bytes(raw_bytes, "report.pdf")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter


@dataclass
class DocumentResult:
    """Result of document processing via Docling."""

    markdown: str
    tables: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class DoclingLoader:
    """Document loader based on IBM Docling.

    Supports PDF, DOCX, PPTX, XLSX, HTML, MD, TXT.
    Uses lazy initialization — Docling models (~1-2GB) are loaded on first call.
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".md", ".txt"}

    def __init__(self) -> None:
        self._converter: DocumentConverter | None = None

    def _get_converter(self) -> DocumentConverter:
        """Lazy-initialize Docling converter (models loaded on first call)."""
        if self._converter is None:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions

            pipeline_options = PdfPipelineOptions()
            pipeline_options.generate_picture_images = True

            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        return self._converter

    def load(self, file_path: str | Path) -> DocumentResult:
        """Load a document and extract content.

        For .txt/.md files, reads directly without Docling.
        For all other formats, uses Docling for full extraction.
        """
        path = Path(file_path)

        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format: {path.suffix}. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )

        # Plain text files — no Docling needed
        if path.suffix.lower() in {".txt", ".md"}:
            return DocumentResult(
                markdown=path.read_text(encoding="utf-8"),
                metadata={"format": path.suffix, "pages": 1},
            )

        converter = self._get_converter()
        result = converter.convert(str(path))
        doc = result.document

        # Extract tables
        tables = []
        for item, _level in doc.iterate_items():
            if hasattr(item, "export_to_dataframe"):
                try:
                    df = item.export_to_dataframe()
                    page_num = None
                    if hasattr(item, "prov") and item.prov:
                        page_num = getattr(item.prov[0], "page_no", None)
                    tables.append({
                        "caption": getattr(item, "caption", "") or "",
                        "markdown": df.to_markdown(index=False),
                        "csv": df.to_csv(index=False),
                        "page": page_num,
                    })
                except Exception:
                    pass  # Skip tables that fail to export

        # Extract images
        images = []
        for item, _level in doc.iterate_items():
            if hasattr(item, "get_image"):
                try:
                    img = item.get_image(doc)
                    if img:
                        page_num = None
                        if hasattr(item, "prov") and item.prov:
                            page_num = getattr(item.prov[0], "page_no", None)
                        images.append({
                            "caption": getattr(item, "caption", "") or "",
                            "page": page_num,
                        })
                except Exception:
                    pass  # Skip images that fail to extract

        # Full markdown export
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
        """Load a document from bytes (for file upload handlers).

        Creates a temporary file, processes it, and cleans up.
        """
        import os
        import tempfile

        suffix = Path(filename).suffix
        if suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format: {suffix}. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )

        # For plain text, no need for temp file
        if suffix.lower() in {".txt", ".md"}:
            return DocumentResult(
                markdown=data.decode("utf-8", errors="replace"),
                metadata={"format": suffix, "pages": 1},
            )

        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        path = Path(tmp_path)
        try:
            os.close(fd)
            path.write_bytes(data)
            return self.load(path)
        finally:
            path.unlink(missing_ok=True)
