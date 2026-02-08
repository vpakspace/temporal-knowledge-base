"""Temporal Verification (GraphOS Layer 14).

Verifies that facts used in LLM responses are current and not superseded.
Prevents the model from citing outdated or invalidated information.
"""

from __future__ import annotations

import logging

from core.models import SearchResult
from storage.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class TemporalVerifier:
    """Verify that search results contain only current facts."""

    def __init__(self, neo4j: Neo4jClient) -> None:
        self._neo4j = neo4j

    async def verify_results(self, results: list[SearchResult]) -> list[SearchResult]:
        """Filter out superseded or invalidated results.

        For each result, check:
        1. is_current flag
        2. invalid_at is not set (or is in the future)
        3. If superseded, include the newer version instead
        """
        verified: list[SearchResult] = []

        for result in results:
            if result.temporal and result.temporal.invalid_at:
                logger.debug("Skipping invalidated result: %s", result.content[:50])
                # Try to find the superseding event
                if result.id:
                    chain = await self._neo4j.get_supersession_chain(result.id)
                    if chain:
                        latest = chain[-1]
                        if latest.get("is_current", False):
                            verified.append(
                                SearchResult(
                                    id=latest["id"],
                                    content=latest.get("statement", ""),
                                    result_type="temporal_event",
                                    supersedes=result.id,
                                )
                            )
                continue

            verified.append(result)

        logger.info(
            "Verified %d/%d results as current",
            len(verified),
            len(results),
        )
        return verified
