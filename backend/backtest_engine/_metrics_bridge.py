from __future__ import annotations
import math, statistics
from typing import List

def _load_shared():
    try:
        from backend.research.backtest.engine import SharedBacktestMetrics
        return SharedBacktestMetrics
    except ImportError:
        return None

_SHARED = _load_shared()

def sharpe_ratio(returns: List[float], rfr: float = 0.0, ann: float = 252) -> float:
    if _SHARED is not None:
        return _SHARED.sharpe_ratio(returns, rfr, ann)
    if len(returns) < 2: return 0.0
    try:
        mean_r = statistics.mean(returns) - rfr / ann
        std_r  = statistics.stdev(returns)
        return (mean_r / std_r) * math.sqrt(ann) if std_r > 1e-10 else 0.0
    except Exception: return 0.0

def sortino_ratio(returns: List[float], rfr: float = 0.0, ann: float = 252) -> float:
    if _SHARED is not None:
        return _SHARED.sortino_ratio(returns, rfr, ann)
    if len(returns) < 2: return 0.0
    try:
        mean_r = statistics.mean(returns) - rfr / ann
        downside = [r for r in returns if r < 0]
        if not downside: return float('inf') if mean_r > 0 else 0.0
        ds = statistics.stdev(downside) if len(downside) > 1 else abs(downside[0])
        return (mean_r / ds) * math.sqrt(ann) if ds > 1e-10 else 0.0
    except Exception: return 0.0

def calmar_ratio(ann_return_pct: float, max_dd_pct: float) -> float:
    if _SHARED is not None:
        return _SHARED.calmar_ratio(ann_return_pct, max_dd_pct)
    return ann_return_pct / max_dd_pct if max_dd_pct > 0 else 0.0

def max_drawdown(equity_curve: List[float]) -> float:
    if _SHARED is not None:
        return _SHARED.max_drawdown(equity_curve)
    if not equity_curve: return 0.0
    peak, max_dd = equity_curve[0], 0.0
    for v in equity_curve:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd
    return max_dd
