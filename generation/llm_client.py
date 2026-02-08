"""LLM client abstraction for extraction, invalidation, and generation.

Uses OpenAI with structured output for entity extraction and
temporal fact classification.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from core.cache import TTLCache
from core.config import OpenAISettings
from core.exceptions import LLMError

logger = logging.getLogger(__name__)


class LLMClient:
    """Async LLM client using OpenAI API."""

    def __init__(self, settings: OpenAISettings) -> None:
        if not settings.api_key:
            raise LLMError("OPENAI_API_KEY is required")
        self._client = AsyncOpenAI(api_key=settings.api_key)
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self.cache = TTLCache(ttl_seconds=600, max_size=500)

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate text response."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature or self._temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(f"LLM generation failed: {e}") from e

    async def generate_json(
        self,
        prompt: str,
        system: str | None = None,
    ) -> dict[str, Any]:
        """Generate structured JSON response."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse JSON from LLM: {e}") from e
        except Exception as e:
            raise LLMError(f"LLM JSON generation failed: {e}") from e

    async def classify_intent(self, query: str) -> str:
        """Classify query intent: structural, temporal, or hybrid.

        Results are cached because the same query always produces the same intent.
        """
        cache_key = TTLCache._hash_key("classify_intent", query)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        system = (
            "You classify user queries into exactly one category.\n"
            "Respond with ONLY one word: structural, temporal, or hybrid.\n\n"
            "structural: questions about relationships and structure "
            '(e.g., "Who works for X?", "What departments exist?")\n'
            "temporal: questions about changes over time "
            '(e.g., "What changed in 2024?", "When did X become CEO?")\n'
            "hybrid: questions combining structure and time "
            '(e.g., "Who was CEO when revenue peaked?")'
        )
        result = await self.generate(query, system=system)
        intent = result.strip().lower()
        if intent not in ("structural", "temporal", "hybrid"):
            intent = "hybrid"
        self.cache.set(cache_key, intent)
        return intent

    async def check_contradiction(self, existing_fact: str, new_fact: str) -> dict[str, Any]:
        """Check if two facts contradict each other using LLM.

        Returns: {"contradicts": bool, "explanation": str, "severity": str}
        """
        system = (
            "You are a fact-checking assistant. Analyze if the new fact "
            "contradicts or supersedes the existing fact.\n\n"
            "Respond in JSON with:\n"
            '- "contradicts": true/false\n'
            '- "explanation": brief explanation\n'
            '- "severity": "critical" (direct contradiction), '
            '"warning" (potential conflict), or "info" (minor update)'
        )
        prompt = (
            f"Existing fact: {existing_fact}\n"
            f"New fact: {new_fact}\n\n"
            "Do these facts contradict each other?"
        )
        return await self.generate_json(prompt, system=system)
