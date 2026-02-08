"""Extract temporal references from natural language queries.

Shared between FastAPI server and MCP server to avoid duplication.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone


def extract_temporal_hint(question: str) -> datetime | None:
    """Extract a temporal reference from a question for point-in-time search.

    Supports patterns like:
    - "в 2023 году", "in 2023", "2023"
    - "в январе 2024", "January 2024"
    - "в 2023-2024" (takes the end of range)
    - "до 2024", "before 2024"

    Returns a datetime at end-of-year/month for the detected period,
    so point-in-time search captures all facts valid up to that moment.
    """
    q = question.lower()

    # "в январе 2024" / "january 2024" / "jan 2024"
    month_ru = {
        "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
        "ма[йя]": 5, "июн": 6, "июл": 7, "август": 8,
        "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
    }
    month_en = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    # Russian month + year
    for pattern, month in month_ru.items():
        m = re.search(rf"{pattern}\w*\s+(\d{{4}})", q)
        if m:
            year = int(m.group(1))
            return datetime(year, month, 28, 23, 59, 59, tzinfo=timezone.utc)

    # English month + year
    for pattern, month in month_en.items():
        m = re.search(rf"{pattern}\w*\s+(\d{{4}})", q)
        if m:
            year = int(m.group(1))
            return datetime(year, month, 28, 23, 59, 59, tzinfo=timezone.utc)

    # Year range "2023-2024" — take end of range
    m = re.search(r"(\d{4})\s*[-–]\s*(\d{4})", q)
    if m:
        year = int(m.group(2))
        return datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    # Standalone year: "в 2023 году", "in 2023", just "2023"
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        year = int(m.group(1))
        return datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    return None
