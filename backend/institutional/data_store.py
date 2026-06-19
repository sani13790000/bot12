"""Institutional Data Store — PostgreSQL/Supabase persistence for all institutional data."""

from __future__ import annotations
import json
import os
import time
from typing import Any, Dict, List, Optional


class InstitutionalDataStore:
    """
    Handles all DB persistence for institutional modules.
    Uses Supabase REST API (no SQLAlchemy dependency).
    Falls back to in-memory if DB unavailable.
    """

    def __init__(self):
        self._url = os.getenv("SUPABASE_URL", "")
        self._key = os.getenv("SUPABASE_SERVICE_KEY", "")
        self._available = bool(self._url and self._key)
        self._memory_store: Dict[str, List[Dict]] = {}

    async def save_backtest_result(self, result: Dict) -> Optional[str]:
        """Save tick backtest result to DB."""
        record = {
            "symbol": result.get("symbol", "XAUUSD"),
            "timeframe": result.get("timeframe", "M15"),
            "initial_balance": result.get("initial_balance"),
            "final_balance": result.get("final_balance"),
            "total_trades": result.get("total_trades"),
            "win_rate": result.get("win_rate"),
            "profit_factor": result.get("profit_factor"),
            "sharpe_ratio": result.get("sharpe_ratio"),
            "sortino_ratio": result.get("sortino_ratio"),
            "max_drawdown_pct": result.get("max_drawdown_pct"),
            "total_commission": result.get("total_commission"),
            "total_spread_cost": result.get("total_spread_cost"),
            "created_at": time.time(),
        }
        return await self._upsert("institutional_backtest_results", record)

    async def save_trade(self, trade: Dict) -> Optional[str]:
        """Save a single backtest trade."""
        record = {
            "trade_id": trade.get("trade_id"),
            "symbol": trade.get("symbol"),
            "direction": trade.get("direction"),
            "open_time": trade.get("open_time"),
            "close_time": trade.get("close_time"),
            "open_price": trade.get("open_price"),
            "close_price": trade.get("close_price"),
            "stop_loss": trade.get("stop_loss"),
            "take_profit": trade.get("take_profit"),
            "lot_size": trade.get("lot_size"),
            "net_profit": trade.get("net_profit"),
            "gross_profit": trade.get("gross_profit"),
            "commission": trade.get("commission"),
            "spread_cost": trade.get("spread_cost"),
            "slippage_cost": trade.get("slippage_cost"),
            "close_reason": trade.get("close_reason"),
            "explanation": json.dumps(trade.get("explanation") or {}),
            "created_at": time.time(),
        }
        return await self._upsert("institutional_trades", record)

    async def save_monte_carlo_result(self, result: Dict) -> Optional[str]:
        record = {
            "n_simulations": result.get("n_simulations"),
            "n_trades": result.get("n_trades"),
            "initial_balance": result.get("initial_balance"),
            "median_final_balance": result.get("median_final_balance"),
            "probability_of_ruin": result.get("probability_of_ruin"),
            "probability_of_profit": result.get("probability_of_profit"),
            "expected_max_drawdown_pct": result.get("expected_max_drawdown_pct"),
            "percentile_5": result.get("percentile_5"),
            "percentile_95": result.get("percentile_95"),
            "created_at": time.time(),
        }
        return await self._upsert("institutional_monte_carlo", record)

    async def save_wfo_result(self, result: Dict) -> Optional[str]:
        record = {
            "n_windows": result.get("n_windows"),
            "avg_is_metric": result.get("avg_is_metric"),
            "avg_oos_metric": result.get("avg_oos_metric"),
            "avg_robustness_ratio": result.get("avg_robustness_ratio"),
            "is_robust": result.get("is_robust"),
            "total_oos_trades": result.get("total_oos_trades"),
            "oos_win_rate": result.get("oos_win_rate"),
            "best_params": json.dumps(result.get("best_params_overall") or {}),
            "created_at": time.time(),
        }
        return await self._upsert("institutional_wfo_results", record)

    async def save_replay_session(self, session: Dict) -> Optional[str]:
        record = {
            "symbol": session.get("symbol"),
            "timeframe": session.get("timeframe"),
            "start_timestamp": session.get("start_timestamp"),
            "end_timestamp": session.get("end_timestamp"),
            "total_candles": session.get("total_candles"),
            "trades_count": session.get("trades_count"),
            "final_equity": session.get("final_equity"),
            "created_at": time.time(),
        }
        return await self._upsert("institutional_replay_sessions", record)

    async def get_backtest_results(
        self, symbol: Optional[str] = None, limit: int = 50
    ) -> List[Dict]:
        key = "institutional_backtest_results"
        records = self._memory_store.get(key, [])
        if symbol:
            records = [r for r in records if r.get("symbol") == symbol]
        return records[-limit:]

    async def get_recent_trades(self, limit: int = 100) -> List[Dict]:
        return self._memory_store.get("institutional_trades", [])[-limit:]

    # ------------------------------------------------------------------ #
    #  Internal                                                             #
    # ------------------------------------------------------------------ #

    async def _upsert(self, table: str, record: Dict) -> Optional[str]:
        """Insert into Supabase. Falls back to in-memory on failure."""
        # In-memory fallback always works
        if table not in self._memory_store:
            self._memory_store[table] = []
        self._memory_store[table].append(record)

        if not self._available:
            return None

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._url}/rest/v1/{table}",
                    headers={
                        "apikey": self._key,
                        "Authorization": f"Bearer {self._key}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation",
                    },
                    json=record,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    if isinstance(data, list) and data:
                        return data[0].get("id")
        except Exception:
            pass
        return None
