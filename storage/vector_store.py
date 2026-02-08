"""Vector store for generating and managing embeddings.

Uses OpenAI text-embedding-3-small for embedding generation.
Embeddings are stored directly in Neo4j nodes (via vector indexes).
"""

from __future__ import annotations

import logging

import numpy as np
from openai import AsyncOpenAI

from core.cache import TTLCache
from core.config import OpenAISettings
from core.exceptions import EmbeddingError

logger = logging.getLogger(__name__)


class VectorStore:
    """Manages embedding generation via OpenAI API."""

    def __init__(self, settings: OpenAISettings) -> None:
        if not settings.api_key:
            raise EmbeddingError("OPENAI_API_KEY is required for embeddings")
        self._client = AsyncOpenAI(api_key=settings.api_key)
        self._model = settings.embedding_model
        self._dimensions = settings.embedding_dimensions
        self.cache = TTLCache(ttl_seconds=3600, max_size=2000)

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Results are cached because the same text always produces the same embedding.
        """
        cache_key = TTLCache._hash_key("embed", self._model, text)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            response = await self._client.embeddings.create(
                input=text,
                model=self._model,
                dimensions=self._dimensions,
            )
            embedding = response.data[0].embedding
            self.cache.set(cache_key, embedding)
            return embedding
        except Exception as e:
            raise EmbeddingError(f"Embedding generation failed: {e}") from e

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []
        try:
            response = await self._client.embeddings.create(
                input=texts,
                model=self._model,
                dimensions=self._dimensions,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            raise EmbeddingError(f"Batch embedding failed: {e}") from e

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        va = np.array(a)
        vb = np.array(b)
        dot = np.dot(va, vb)
        norm_a = np.linalg.norm(va)
        norm_b = np.linalg.norm(vb)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))
