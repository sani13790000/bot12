"""
F4 - connection_health.py
Health check helper for /health endpoint.
"""
from typing import Dict, Any


async def get_connection_status() -> Dict[str, Any]:
    """
    F4 Health check helper - returns DB connection status for /health endpoint.
    """
    try:
        from . import db
        status = await db.health_check()
        return {
            'connected': status.get('healthy', False),
            'status': 'connected' if status.get('healthy') else 'disconnected',
            'latency_ms': status.get('latency_ms'),
        }
    except Exception as exc:
        return {
            'connected': False,
            'status': f'error: {exc}',
            'latency_ms': None,
        }
