"""
Galaxy Vast AI Trading Platform
AnalyticsService — DB-backed analytics with caching and snapshots
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import asdict

from .metrics_engine import MetricsEngine, TradeRecord, AnalyticsResult

logger = logging.getLogger("galaxy_vast.analytics")


class AnalyticsService:
    """
    Orchestrates analytics calculation + persistence.

    Responsibilities:
      - Load trades from DB (via asyncpg pool)
      - Delegate calculation to MetricsEngine
      - Cache results (in-memory + DB snapshot)
      - Provide period-filtered queries
    """

    CACHE_TTL_SECONDS: int = 300    # 5 minutes
    SNAPSHOT_INTERVAL: int = 3600   # write DB snapshot every 1 hour

    def __init__(self, db_pool=None):
        self._pool = db_pool
        self._engine = MetricsEngine()
        self._cache: Dict[str, dict] = {}          # key → {result, expires_at}
        self._last_snapshot: Dict[str, datetime] = {}

    # ── Public API ───────────────────────────────────────────────────────────

    async def get_analytics(
        self,
        symbol: Optional[str] = None,
        period: str = "ALL",           # ALL | TODAY | WEEK | MONTH | YEAR
        initial_balance: float = 10_000.0,
        risk_free_rate: float = 0.05,
        use_cache: bool = True,
    ) -> AnalyticsResult:
        """
        Return full AnalyticsResult for the given filter.
        Uses in-memory cache to avoid repeated computation.
        """
        cache_key = f"{symbol or 'ALL'}:{period}"

        if use_cache and cache_key in self._cache:
            entry = self._cache[cache_key]
            if datetime.utcnow() < entry["expires_at"]:
                logger.debug(f"Analytics cache hit: {cache_key}")
                return entry["result"]

        trades = await self._load_trades(symbol=symbol, period=period)
        result = self._engine.calculate(
            trades=trades,
            initial_balance=initial_balance,
            risk_free_rate=risk_free_rate,
        )

        self._cache[cache_key] = {
            "result":     result,
            "expires_at": datetime.utcnow() + timedelta(seconds=self.CACHE_TTL_SECONDS),
        }

        await self._maybe_save_snapshot(cache_key, result)
        return result

    async def get_summary(
        self,
        symbol: Optional[str] = None,
        period: str = "MONTH",
    ) -> dict:
        """Lightweight summary dict (no equity curve)."""
        result = await self.get_analytics(symbol=symbol, period=period)
        d = result.to_dict()
        d.pop("equity_curve", None)
        d.pop("drawdown_curve", None)
        return d

    async def get_equity_curve(
        self,
        symbol: Optional[str] = None,
        period: str = "ALL",
        initial_balance: float = 10_000.0,
    ) -> List[dict]:
        result = await self.get_analytics(
            symbol=symbol, period=period, initial_balance=initial_balance
        )
        return result.equity_curve

    async def get_metrics_comparison(
        self,
        symbol: str,
        periods: List[str] = ("WEEK", "MONTH", "YEAR"),
    ) -> dict:
        """Compare metrics across multiple periods."""
        comparison = {}
        for period in periods:
            r = await self.get_analytics(symbol=symbol, period=period)
            comparison[period] = {
                "sharpe_ratio":   round(r.sharpe_ratio, 4),
                "sortino_ratio":  round(r.sortino_ratio, 4),
                "calmar_ratio":   round(r.calmar_ratio, 4),
                "win_rate":       round(r.win_rate, 4),
                "profit_factor":  round(r.profit_factor, 4),
                "max_drawdown":   round(r.max_drawdown_pct * 100, 2),
                "net_profit":     round(r.net_profit, 2),
                "total_trades":   r.total_trades,
                "expectancy_r":   round(r.expectancy_r, 4),
            }
        return comparison

    async def invalidate_cache(self, symbol: Optional[str] = None) -> None:
        """Force cache invalidation after new trades arrive."""
        if symbol:
            keys = [k for k in self._cache if k.startswith(f"{symbol}:")]
        else:
            keys = list(self._cache.keys())
        for k in keys:
            del self._cache[k]
        logger.info(f"Analytics cache invalidated: {len(keys)} keys")

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _load_trades(
        self,
        symbol: Optional[str],
        period: str,
    ) -> List[TradeRecord]:
        """Load trades from DB; fallback to empty list if no DB."""
        if self._pool is None:
            return []

        where_clauses = ["status = 'CLOSED'"]
        params = []

        if symbol:
            params.append(symbol)
            where_clauses.append(f"symbol = ${len(params)}")

        since = self._period_to_since(period)
        if since:
            params.append(since)
            where_clauses.append(f"close_time >= ${len(params)}")

        where = " AND ".join(where_clauses)
        sql = f"""
            SELECT
                ticket, symbol, direction,
                entry_price, exit_price, stop_loss, lot_size,
                profit_loss, pips, risk_amount, reward_amount,
                confidence_score, session, strategy_tags,
                open_time, close_time
            FROM analytics_trades
            WHERE {where}
            ORDER BY open_time ASC
        """

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)
            return [self._row_to_record(r) for r in rows]
        except Exception as exc:
            logger.error(f"Failed to load trades from DB: {exc}")
            return []

    def _row_to_record(self, row) -> TradeRecord:
        tags = row["strategy_tags"] or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        return TradeRecord(
            ticket=row["ticket"],
            symbol=row["symbol"],
            direction=row["direction"],
            entry_price=float(row["entry_price"]),
            exit_price=float(row["exit_price"]),
            stop_loss=float(row["stop_loss"]),
            lot_size=float(row["lot_size"]),
            profit_loss=float(row["profit_loss"]),
            pips=float(row["pips"] or 0),
            risk_amount=float(row["risk_amount"] or 0),
            reward_amount=float(row["reward_amount"] or 0),
            confidence_score=float(row["confidence_score"] or 0),
            session=row["session"] or "UNKNOWN",
            strategy_tags=tags,
            open_time=row["open_time"],
            close_time=row["close_time"],
        )

    def _period_to_since(self, period: str) -> Optional[datetime]:
        now = datetime.utcnow()
        mapping = {
            "TODAY":  now.replace(hour=0, minute=0, second=0, microsecond=0),
            "WEEK":   now - timedelta(days=7),
            "MONTH":  now - timedelta(days=30),
            "YEAR":   now - timedelta(days=365),
            "ALL":    None,
        }
        return mapping.get(period.upper())

    async def _maybe_save_snapshot(self, key: str, result: AnalyticsResult) -> None:
        if self._pool is None:
            return
        last = self._last_snapshot.get(key, datetime.min)
        if (datetime.utcnow() - last).total_seconds() < self.SNAPSHOT_INTERVAL:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO analytics_snapshots
                        (snapshot_key, metrics_json, created_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (snapshot_key)
                    DO UPDATE SET metrics_json = EXCLUDED.metrics_json,
                                  created_at   = NOW()
                """, key, json.dumps(result.to_dict()))
            self._last_snapshot[key] = datetime.utcnow()
        except Exception as exc:
            logger.warning(f"Snapshot save failed: {exc}")
