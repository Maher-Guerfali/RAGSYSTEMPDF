"""API key authentication middleware for FastAPI."""

import hmac
import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_server_api_key() -> str:
    key = os.environ.get("API_KEY", "")
    if not key:
        raise RuntimeError("API_KEY environment variable is not set")
    return key


async def require_api_key(
    api_key: str = Security(_api_key_header),
) -> str:
    """FastAPI dependency that validates the X-API-Key header."""
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    server_key = _get_server_api_key()
    if not hmac.compare_digest(api_key, server_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key
