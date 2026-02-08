"""API key authentication dependency.

When APP_API_KEY is set in the environment, all /api/* endpoints
require a matching X-API-Key header.  If the env var is empty,
authentication is disabled (open access).
"""

from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from core.config import get_settings

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(_header)) -> None:
    """Validate the X-API-Key header against APP_API_KEY.

    Raises 401 if the key is missing or wrong.
    Does nothing when APP_API_KEY is empty (auth disabled).
    """
    expected = get_settings().api_key
    if not expected:
        return  # auth disabled
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
