"""
Phase 8 — Connection Health (updated)
Bridge: imports pool_monitor and query_optimizer for /health endpoint.
"""
from __future__ import annotations
from typing import Any, Dict


async def get_db_health() -> Dict[str, Any]:
    """
    Unified DB health report used by /health endpoint.
    Returns pool status + slow query summary.
    """
    from backend.database.connection import db
    from backend.database.connection_pool_monitor import pool_monitor
    from backend.database.query_optimizer import query_optimizer

    basic = await db.health_check()
    pool_status = await pool_monitor.get_status()
    slow_summary = await query_optimizer.get_stats_summary()

    return {
        "database": basic,
        "pool": pool_status,
        "slow_queries_top5": slow_summary[:5],
    }
