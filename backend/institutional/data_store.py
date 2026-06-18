"""Galaxy Vast AI Trading Platform — Institutional Data Store.

Persists all trades, backtests, and replay sessions to PostgreSQL / Supabase.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.database.connection import get_db
from backend.research.backtest.engine import BacktestTrade


class InstitutionalDataStore:
    """Async data persistence layer for institutional modules."""

    @staticmethod
    async def save_trade(trade: BacktestTrade, user_id: Optional[str] = None, source: str = "tick_backtest") -> str:
        db = get_db()
        record_id = str(uuid.uuid4())
        data = {
            "id": record_id,
            "user_id": user_id,
            "source": source,
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "direction": trade.direction,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "stop_loss": trade.stop_loss,
            "take_profit": trade.take_profit,
            "lot_size": trade.lot_size,
            "pnl_pips": trade.pnl_pips,
            "pnl_usd": trade.pnl_usd,
            "outcome": trade.outcome,
            "created_at": datetime.utcnow().isoformat(),
        }
        await db.insert("institutional_trades", data, use_admin=True)
        return record_id

    @staticmethod
    async def save_trades_batch(trades: List[BacktestTrade], user_id: Optional[str] = None, source: str = "tick_backtest") -> List[str]:
        ids = []
        for trade in trades:
            trade_id = await InstitutionalDataStore.save_trade(trade, user_id, source)
            ids.append(trade_id)
        return ids

    @staticmethod
    async def save_backtest_result(
        result: Dict[str, Any],
        user_id: Optional[str] = None,
        run_name: str = "institutional_backtest",
    ) -> str:
        db = get_db()
        record_id = str(uuid.uuid4())
        data = {
            "id": record_id,
            "user_id": user_id,
            "run_name": run_name,
            "config": json.dumps(result.get("config", {})),
            "final_balance": result.get("final_balance"),
            "total_return_pct": result.get("total_return_pct"),
            "total_trades": result.get("total_trades"),
            "metrics": json.dumps(result.get("metrics", {})),
            "equity_curve": json.dumps(result.get("equity_curve", [])),
            "created_at": datetime.utcnow().isoformat(),
        }
        await db.insert("institutional_backtests", data, use_admin=True)
        return record_id

    @staticmethod
    async def save_replay_session(
        session_state: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> str:
        db = get_db()
        record_id = str(uuid.uuid4())
        data = {
            "id": record_id,
            "user_id": user_id,
            "state": json.dumps(session_state),
            "created_at": datetime.utcnow().isoformat(),
        }
        await db.insert("institutional_replay_sessions", data, use_admin=True)
        return record_id

    @staticmethod
    async def list_backtests(user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        db = get_db()
        filters = {"user_id": user_id} if user_id else {}
        rows = await db.select_many("institutional_backtests", filters=filters, order_by="created_at", order_desc=True, limit=limit, use_admin=True)
        for row in rows:
            for key in ("config", "metrics", "equity_curve"):
                if row.get(key):
                    try:
                        row[key] = json.loads(row[key])
                    except Exception:
                        pass
        return rows
