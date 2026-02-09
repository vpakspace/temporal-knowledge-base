"""Tests for semantic chunker."""

from ingestion.chunker import SemanticChunker, split_large_content


def test_short_text_no_split():
    chunker = SemanticChunker(max_chunk_size=1000)
    result = chunker.chunk("Short text.")
    assert result == ["Short text."]


def test_empty_text():
    chunker = SemanticChunker()
    assert chunker.chunk("") == []
    assert chunker.chunk("   ") == []


def test_paragraph_split():
    chunker = SemanticChunker(max_chunk_size=50, min_chunk_size=10)
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    result = chunker.chunk(text)
    assert len(result) >= 2


def test_sentence_split():
    chunker = SemanticChunker(max_chunk_size=40, min_chunk_size=10)
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    result = chunker.chunk(text)
    assert len(result) >= 2
    for chunk in result:
        assert len(chunk) <= 80  # Account for merged small chunks


def test_merge_small_chunks():
    chunker = SemanticChunker(max_chunk_size=200, min_chunk_size=50)
    text = "A.\n\nB.\n\nC."
    result = chunker.chunk(text)
    # Small chunks should be merged
    assert len(result) <= 2


def test_large_paragraph_split():
    chunker = SemanticChunker(max_chunk_size=100, min_chunk_size=20)
    text = "This is a sentence. " * 20  # ~400 chars
    result = chunker.chunk(text)
    assert len(result) >= 2
    for chunk in result:
        assert len(chunk) <= 200  # Reasonable bound


# --- Tests for split_large_content ---


def test_split_small_content_no_split():
    parts = split_large_content("Short text", "src")
    assert len(parts) == 1
    assert parts[0] == ("Short text", "src")


def test_split_empty_content():
    parts = split_large_content("", "src")
    assert len(parts) == 1
    assert parts[0] == ("", "src")


def test_split_large_content_basic():
    # Create content that exceeds 8000 chars
    para = "This is a paragraph with some content. " * 20  # ~780 chars
    text = "\n\n".join([para] * 15)  # ~12,700 chars (exceeds 8000)
    parts = split_large_content(text, "doc")
    assert len(parts) >= 2
    for content, name in parts:
        assert name.startswith("doc_part_")
        assert len(content) <= 8500  # Some margin for paragraph boundary


def test_split_preserves_all_content():
    para = "Paragraph number {i}."
    text = "\n\n".join([f"Paragraph number {i}." for i in range(200)])
    parts = split_large_content(text, "test")
    # All parts combined should contain all paragraphs
    combined = " ".join(content for content, _ in parts)
    for i in range(200):
        assert f"Paragraph number {i}." in combined


def test_split_custom_max_chars():
    text = "Hello world. " * 100  # ~1300 chars
    parts = split_large_content(text, "src", max_chars=500)
    assert len(parts) >= 2
    for content, name in parts:
        assert len(content) <= 600  # Some margin


def test_split_source_naming():
    text = "A" * 10000 + "\n\n" + "B" * 10000
    parts = split_large_content(text, "myfile.pdf", max_chars=5000)
    assert len(parts) >= 2
    for _, name in parts:
        assert name.startswith("myfile.pdf_part_")


def test_split_long_paragraph():
    # Single paragraph exceeding limit — should split at sentence boundaries
    text = "This is sentence one. " * 500  # ~11,000 chars, no paragraph breaks
    parts = split_large_content(text, "src", max_chars=5000)
    assert len(parts) >= 2
