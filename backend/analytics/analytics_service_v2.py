"""Analytics Service v2 - Phase Q-21..Q-27 fixes."""
from __future__ import annotations
import asyncio, logging, time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
logger = logging.getLogger(__name__)

@dataclass
class _CacheEntry:
    data: Any
    expires_at: float

class MetricsCache:
    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._store: Dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            e = self._store.get(key)
            return e.data if e and time.monotonic() < e.expires_at else None
    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._store[key] = _CacheEntry(data=value, expires_at=time.monotonic() + self._ttl)
    async def invalidate(self, prefix: str = "") -> None:
        async with self._lock:
            for k in [k for k in self._store if k.startswith(prefix)]:
                del self._store[k]

_cache = MetricsCache(30.0)

def sharpe_ratio(returns: List[float], risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    if len(returns) < 2: return 0.0
    import statistics as _s
    mean = _s.mean(returns) - risk_free / periods_per_year
    std = _s.stdev(returns)
    if std < 1e-10: return 0.0
    return round(mean / std * (periods_per_year ** 0.5), 4)

def max_drawdown(equity_curve: List[float]) -> Tuple[float, int, int]:
    if len(equity_curve) < 2: return 0.0, 0, 0
    peak = equity_curve[0]; peak_i = 0; mdd = 0.0; bp = 0; bt = 0
    for i, eq in enumerate(equity_curve):
        if eq > peak: peak = eq; peak_i = i
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > mdd: mdd = dd; bp = peak_i; bt = i
    return round(mdd * 100, 4), bp, bt

def win_rate(wins: int, total: int) -> float:
    return 0.0 if total <= 0 else round(wins / total * 100, 2)

def profit_factor(gross_profit: float, gross_loss: float) -> float:
    if abs(gross_loss) < 1e-9: return 0.0 if gross_profit <= 0 else 999.9
    return round(gross_profit / abs(gross_loss), 4)

class AnalyticsServiceV2:
    async def aggregate_metrics(self, user_id: str, since: Optional[datetime] = None) -> Dict[str, Any]:
        ck = f"metrics:{user_id}:{since.isoformat() if since else 'all'}"
        cached = await _cache.get(ck)
        if cached: return cached
        try:
            from ..database import db
            r = await db.client.rpc("get_trade_metrics", {
                "p_user_id": user_id,
                "p_since": (since or datetime(1970,1,1,tzinfo=timezone.utc)).isoformat()
            }).execute()
            d = r.data[0] if r.data else {}
        except Exception as e:
            logger.warning("[AnalyticsV2] aggregate_metrics: %s", e); d = {}
        w = int(d.get("wins", 0)); tot = int(d.get("total_trades", 0))
        gp = float(d.get("gross_profit", 0)); gl = float(d.get("gross_loss", 0))
        result = {"total_trades": tot, "wins": w, "losses": int(d.get("losses", 0)),
                  "gross_profit": gp, "gross_loss": gl,
                  "win_rate": win_rate(w, tot), "profit_factor": profit_factor(gp, gl)}
        await _cache.set(ck, result)
        return result

    async def pnl_by_symbol(self, user_id: str, since: Optional[datetime] = None, until: Optional[datetime] = None) -> Dict[str, float]:
        now = datetime.now(timezone.utc)
        since = since or (now - timedelta(days=30)); until = until or now
        ck = f"pnl:{user_id}:{since.date()}:{until.date()}"
        cached = await _cache.get(ck)
        if cached: return cached
        try:
            from ..database import db
            r = await db.client.from_("trades").select("symbol,pnl").eq("user_id", user_id).eq("status", "CLOSED").gte("closed_at", since.isoformat()).lte("closed_at", until.isoformat()).execute()
            res: Dict[str, float] = defaultdict(float)
            for row in (r.data or []): res[row["symbol"]] += float(row.get("pnl") or 0)
            result = dict(res)
        except Exception as e:
            logger.warning("[AnalyticsV2] pnl_by_symbol: %s", e); result = {}
        await _cache.set(ck, result)
        return result

    async def equity_metrics(self, user_id: str, since: Optional[datetime] = None) -> Dict[str, Any]:
        since = since or (datetime.now(timezone.utc) - timedelta(days=90))
        ck = f"equity:{user_id}:{since.date()}"
        cached = await _cache.get(ck)
        if cached: return cached
        try:
            from ..database import db
            r = await db.client.from_("trades").select("closed_at,pnl").eq("user_id", user_id).eq("status", "CLOSED").gte("closed_at", since.isoformat()).order("closed_at", desc=False).execute()
            daily: Dict[str, float] = defaultdict(float)
            eq = 10000.0; curve = [eq]
            for row in (r.data or []): daily[row["closed_at"][:10]] += float(row.get("pnl") or 0)
            rets = []
            for day in sorted(daily):
                eq += daily[day]; curve.append(eq)
                if len(curve) >= 2: prev = curve[-2]; rets.append((eq - prev) / prev if prev > 0 else 0.0)
        except Exception as e:
            logger.warning("[AnalyticsV2] equity_metrics: %s", e); rets = []; curve = [10000.0]
        mdd, pi, ti = max_drawdown(curve); sr = sharpe_ratio(rets)
        result = {"sharpe_ratio": sr, "max_drawdown_pct": mdd, "peak_idx": pi, "trough_idx": ti, "equity_points": len(curve)}
        await _cache.set(ck, result)
        return result

    async def get_trade_report_paginated(self, user_id: str, page: int = 1, page_size: int = 100, since: Optional[datetime] = None) -> Dict[str, Any]:
        page_size = min(page_size, 500); offset = (page - 1) * page_size
        since = since or (datetime.now(timezone.utc) - timedelta(days=30))
        try:
            from ..database import db
            r = await db.client.from_("trades").select("*").eq("user_id", user_id).gte("created_at", since.isoformat()).order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
            cr = await db.client.from_("trades").select("id", count="exact").eq("user_id", user_id).gte("created_at", since.isoformat()).execute()
            data = r.data or []; total = cr.count or len(data)
        except Exception as e:
            logger.warning("[AnalyticsV2] paginated: %s", e); data = []; total = 0
        return {"page": page, "page_size": page_size, "total": total, "pages": max(1, -(-total // page_size)), "trades": data}
