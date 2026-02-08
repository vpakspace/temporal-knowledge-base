"""Response builder with temporal context (GraphOS Layers 13, 15-16).

Generates LLM responses grounded in verified temporal facts,
with optional timeline generation.
"""

from __future__ import annotations

import logging
from typing import Any

from core.models import SearchResponse, SearchResult
from generation.llm_client import LLMClient
from generation.temporal_verifier import TemporalVerifier

logger = logging.getLogger(__name__)

RESPONSE_SYSTEM_PROMPT = """\
You are a knowledge assistant powered by a temporal knowledge graph.
Answer the user's question using ONLY the provided facts.

Rules:
- Only use facts from the context below
- If a fact has a valid_at date, mention when it became true
- If facts show an evolution (superseded facts), explain the timeline
- If you don't have enough information, say so
- Be concise and factual
"""


class ResponseBuilder:
    """Build LLM responses from verified search results."""

    def __init__(
        self,
        llm: LLMClient,
        verifier: TemporalVerifier,
    ) -> None:
        self._llm = llm
        self._verifier = verifier

    async def build_response(
        self,
        query: str,
        search_response: SearchResponse,
        include_timeline: bool = False,
    ) -> dict[str, Any]:
        """Build a grounded response from search results.

        1. Verify all facts are current
        2. Build context from verified facts
        3. Generate response via LLM
        4. Optionally include timeline
        """
        # Step 1: Verify
        verified = await self._verifier.verify_results(search_response.results)

        if not verified:
            return {
                "answer": "I don't have enough information to answer this question.",
                "facts_used": 0,
                "timeline": None,
            }

        # Step 2: Build context
        context = self._build_context(verified)

        # Step 3: Generate
        prompt = f"Context:\n{context}\n\nQuestion: {query}"
        answer = await self._llm.generate(prompt, system=RESPONSE_SYSTEM_PROMPT)

        # Step 4: Timeline
        timeline = None
        if include_timeline:
            timeline = self._build_timeline(verified)

        return {
            "answer": answer,
            "facts_used": len(verified),
            "sources": [
                {
                    "id": r.id,
                    "content": r.content,
                    "valid_at": (
                        str(r.temporal.valid_at) if r.temporal and r.temporal.valid_at else None
                    ),
                }
                for r in verified
            ],
            "timeline": timeline,
        }

    def _build_context(self, results: list[SearchResult]) -> str:
        """Format verified results as LLM context."""
        lines = []
        for i, r in enumerate(results, 1):
            temporal_info = ""
            if r.temporal and r.temporal.valid_at:
                temporal_info = f" [valid since: {r.temporal.valid_at.strftime('%Y-%m-%d')}]"
            if r.supersedes:
                temporal_info += " [updated fact]"
            lines.append(f"{i}. {r.content}{temporal_info}")
        return "\n".join(lines)

    def _build_timeline(self, results: list[SearchResult]) -> list[dict[str, Any]]:
        """Build a chronological timeline from results."""
        timed = [r for r in results if r.temporal and r.temporal.valid_at]
        timed.sort(key=lambda r: r.temporal.valid_at)
        return [
            {
                "date": r.temporal.valid_at.isoformat(),
                "fact": r.content,
                "is_current": r.temporal.is_current if r.temporal else True,
            }
            for r in timed
        ]
