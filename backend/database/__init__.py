"""Database package for Galaxy Vast AI Trading Platform."""
from backend.database.connection import get_db_client

__all__ = ["get_db_client"]
