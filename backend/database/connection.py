"""Supabase async database connection — singleton pattern.

Provides a single shared client instance for the entire application.
Raises RuntimeError on failure so /health correctly reports degraded.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client: Optional[Any] = None


async def get_db_client() -> Any:
    """Return the shared Supabase client, initialising on first call.

    Raises
    ------
    RuntimeError
        If the required environment variables are missing or the client
        cannot be created.
    """
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
            "before the database client can be initialised."
        )

    try:
        from supabase import create_client  # type: ignore

        _client = create_client(url, key)
        logger.info("Supabase client initialised successfully.")
        return _client
    except Exception as exc:
        raise RuntimeError(f"Failed to create Supabase client: {exc}") from exc


def reset_client() -> None:
    """Reset the singleton (for testing)."""
    global _client
    _client = None
