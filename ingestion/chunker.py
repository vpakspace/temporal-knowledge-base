"""Adaptive semantic chunker for temporal knowledge base.

Splits text into semantically coherent chunks, preserving
temporal context within each chunk (no mid-sentence splits
on temporal markers).
"""

from __future__ import annotations

import re


class SemanticChunker:
    """Chunk text into semantically coherent pieces."""

    def __init__(
        self,
        max_chunk_size: int = 1000,
        min_chunk_size: int = 100,
        overlap: int = 50,
    ) -> None:
        self._max_size = max_chunk_size
        self._min_size = min_chunk_size
        self._overlap = overlap

    def chunk(self, text: str) -> list[str]:
        """Split text into semantic chunks.

        Strategy:
        1. Split into blocks preserving markdown tables as atomic units
        2. Split non-table blocks on paragraph boundaries
        3. If paragraphs are too large, split on sentence boundaries
        4. Merge small chunks to meet minimum size
        """
        if len(text) <= self._max_size:
            return [text.strip()] if text.strip() else []

        # First, split preserving tables as atomic units
        blocks = self._split_preserving_tables(text)
        chunks: list[str] = []

        for block in blocks:
            if self._is_table(block):
                # Tables are atomic — never split them
                chunks.append(block)
            elif len(block) <= self._max_size:
                chunks.append(block)
            else:
                paragraphs = self._split_paragraphs(block)
                for para in paragraphs:
                    if len(para) <= self._max_size:
                        chunks.append(para)
                    else:
                        sentences = self._split_sentences(para)
                        chunks.extend(self._merge_sentences(sentences))

        return self._merge_small_chunks(chunks)

    def _split_preserving_tables(self, text: str) -> list[str]:
        """Split text into blocks, preserving markdown tables as atomic units.

        A markdown table is a contiguous block of lines starting with |.
        Tables are never split across chunks.
        """
        table_pattern = re.compile(r"((?:^\|.*\|$\n?)+)", re.MULTILINE)

        parts: list[str] = []
        last_end = 0
        for match in table_pattern.finditer(text):
            before = text[last_end : match.start()].strip()
            if before:
                parts.append(before)
            parts.append(match.group(0).strip())
            last_end = match.end()

        after = text[last_end:].strip()
        if after:
            parts.append(after)

        return parts if parts else [text.strip()]

    @staticmethod
    def _is_table(text: str) -> bool:
        """Check if text block is a markdown table."""
        lines = text.strip().split("\n")
        return len(lines) >= 2 and all(line.strip().startswith("|") for line in lines)

    def _split_paragraphs(self, text: str) -> list[str]:
        """Split on double newlines (paragraph boundaries)."""
        parts = re.split(r"\n\s*\n", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_sentences(self, text: str) -> list[str]:
        """Split on sentence boundaries, preserving temporal markers."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _merge_sentences(self, sentences: list[str]) -> list[str]:
        """Merge sentences into chunks respecting max size."""
        chunks: list[str] = []
        current = ""

        for sent in sentences:
            if len(current) + len(sent) + 1 <= self._max_size:
                current = f"{current} {sent}".strip() if current else sent
            else:
                if current:
                    chunks.append(current)
                current = sent

        if current:
            chunks.append(current)
        return chunks

    def _merge_small_chunks(self, chunks: list[str]) -> list[str]:
        """Merge chunks that are below minimum size."""
        if not chunks:
            return []

        merged: list[str] = []
        current = chunks[0]

        for chunk in chunks[1:]:
            if len(current) < self._min_size:
                current = f"{current}\n\n{chunk}"
            else:
                merged.append(current)
                current = chunk

        merged.append(current)
        return merged
