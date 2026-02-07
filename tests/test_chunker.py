"""Tests for semantic chunker."""

from ingestion.chunker import SemanticChunker


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
