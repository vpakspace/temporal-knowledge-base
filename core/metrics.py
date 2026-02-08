"""Lightweight in-process metrics collector.

Tracks request counts, latencies, errors, and domain-specific counters
without external dependencies. Data resets on restart (in-memory only).
"""

from __future__ import annotations

import statistics
import time
from collections import defaultdict
from typing import Any


class MetricsCollector:
    """Collects counters and timing histograms for API and pipeline operations."""

    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._counters: dict[str, int] = defaultdict(int)
        self._timings: dict[str, list[float]] = defaultdict(list)
        self._max_timing_samples = 1000

    def inc(self, name: str, value: int = 1) -> None:
        """Increment a counter."""
        self._counters[name] += value

    def timing(self, name: str, duration_ms: float) -> None:
        """Record a timing sample (milliseconds)."""
        samples = self._timings[name]
        if len(samples) >= self._max_timing_samples:
            # Keep last half to avoid unbounded growth
            self._timings[name] = samples[len(samples) // 2 :]
        self._timings[name].append(duration_ms)

    def get_counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    def get_timing_stats(self, name: str) -> dict[str, float]:
        """Get min/max/avg/p50/p95 for a timing metric."""
        samples = self._timings.get(name, [])
        if not samples:
            return {}
        sorted_s = sorted(samples)
        n = len(sorted_s)
        return {
            "count": n,
            "min_ms": round(sorted_s[0], 2),
            "max_ms": round(sorted_s[-1], 2),
            "avg_ms": round(statistics.mean(sorted_s), 2),
            "p50_ms": round(sorted_s[n // 2], 2),
            "p95_ms": round(sorted_s[int(n * 0.95)], 2),
        }

    def uptime_seconds(self) -> float:
        return round(time.monotonic() - self._start_time, 1)

    def snapshot(self) -> dict[str, Any]:
        """Full metrics snapshot."""
        timings = {}
        for name in self._timings:
            timings[name] = self.get_timing_stats(name)

        return {
            "uptime_seconds": self.uptime_seconds(),
            "counters": dict(self._counters),
            "timings": timings,
        }

    def reset(self) -> None:
        self._counters.clear()
        self._timings.clear()
        self._start_time = time.monotonic()


# Global singleton
metrics = MetricsCollector()
