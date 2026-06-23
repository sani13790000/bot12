"""backend/backtest_engine/walk_forward_advanced.py
Phase Q Fix Q-15: efficiency = OOS/IS fitness — ZeroDivisionError guarded with _safe_div.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Q-15: safe division — returns default when denominator is zero or near-zero."""
    if abs(denominator) < 1e-10:
        return default
    return numerator / denominator


@dataclass
class WalkForwardWindow:
    window_id: int; is_start: datetime; is_end: datetime
    oos_start: datetime; oos_end: datetime
    best_params: Dict[str, Any] = field(default_factory=dict)
    is_result: Optional[Any] = None; oos_result: Optional[Any] = None
    passed: bool = False; fitness_is: float = 0.0; fitness_oos: float = 0.0
    efficiency: float = 0.0  # Q-15: safe_div guarded

    def to_dict(self) -> dict:
        def _s(r):
            if r is None: return None
            return {"sharpe": getattr(r,"sharpe_ratio",0.0), "pf": getattr(r,"profit_factor",0.0), "wr": round(getattr(r,"win_rate",0.0)*100,1), "net_pct": getattr(r,"net_profit_pct",0.0), "trades": getattr(r,"total_trades",0), "mdd": getattr(r,"max_drawdown_pct",0.0)}
        return {"window_id": self.window_id, "is_period": f"{self.is_start.date()} \u2192 {self.is_end.date()}", "oos_period": f"{self.oos_start.date()} \u2192 {self.oos_end.date()}", "best_params": self.best_params, "passed": self.passed, "fitness_is": round(self.fitness_is,3), "fitness_oos": round(self.fitness_oos,3), "efficiency": round(self.efficiency,3), "is_result": _s(self.is_result), "oos_result": _s(self.oos_result)}


@dataclass
class WalkForwardResult:
    windows: List[WalkForwardWindow] = field(default_factory=list)
    stability_score: float = 0.0; avg_efficiency: float = 0.0
    passing_windows: int = 0; total_windows: int = 0
    is_robust: bool = False; robustness_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"stability_score": round(self.stability_score,3), "avg_efficiency": round(self.avg_efficiency,3), "passing_windows": self.passing_windows, "total_windows": self.total_windows, "is_robust": self.is_robust, "robustness_notes": self.robustness_notes, "windows": [w.to_dict() for w in self.windows]}


class WalkForwardAdvanced:
    def __init__(self, is_months: int = 12, oos_months: int = 3, step_months: int = 3, min_fitness_is: float = 0.3, min_efficiency: float = 0.4, mode: str = "rolling") -> None:
        self.is_months = is_months; self.oos_months = oos_months; self.step_months = step_months
        self.min_fitness_is = min_fitness_is; self.min_efficiency = min_efficiency; self.mode = mode

    def _add_months(self, dt: datetime, months: int) -> datetime:
        m = dt.month - 1 + months; year = dt.year + m // 12; mon = m % 12 + 1
        day = min(dt.day, [31,28,31,30,31,30,31,31,30,31,30,31][mon-1])
        return dt.replace(year=year, month=mon, day=day)

    def _build_windows(self, start: datetime, end: datetime) -> List[WalkForwardWindow]:
        windows: List[WalkForwardWindow] = []; idx = 0
        if self.mode == "anchored":
            anchor = start; oos_s = self._add_months(anchor, self.is_months)
            while oos_s < end:
                oos_e = min(self._add_months(oos_s, self.oos_months), end)
                windows.append(WalkForwardWindow(window_id=idx, is_start=anchor, is_end=oos_s, oos_start=oos_s, oos_end=oos_e))
                oos_s = self._add_months(oos_s, self.step_months); idx += 1
        else:
            is_s = start
            while True:
                is_e = self._add_months(is_s, self.is_months); oos_s = is_e; oos_e = self._add_months(oos_s, self.oos_months)
                if oos_e > end: break
                windows.append(WalkForwardWindow(window_id=idx, is_start=is_s, is_end=is_e, oos_start=oos_s, oos_end=oos_e))
                is_s = self._add_months(is_s, self.step_months); idx += 1
        return windows

    def _fitness(self, result: Optional[Any]) -> float:
        if result is None: return 0.0
        sharpe = max(0.0, getattr(result, "sharpe_ratio", 0.0))
        pf = max(0.0, getattr(result, "profit_factor", 0.0))
        return round(0.6 * sharpe + 0.4 * min(pf, 5.0), 4)

    async def run(self, start: datetime, end: datetime, run_backtest_fn) -> WalkForwardResult:
        windows = self._build_windows(start, end)
        if not windows:
            return WalkForwardResult(robustness_notes=["No windows generated"])
        for w in windows:
            try:
                is_res, oos_res = await run_backtest_fn(w.is_start, w.is_end, w.oos_start, w.oos_end)
                w.is_result = is_res; w.oos_result = oos_res
            except Exception:
                w.is_result = None; w.oos_result = None
            w.fitness_is = self._fitness(w.is_result); w.fitness_oos = self._fitness(w.oos_result)
            w.efficiency = _safe_div(w.fitness_oos, w.fitness_is, default=0.0)  # Q-15
            w.passed = w.fitness_is >= self.min_fitness_is and w.efficiency >= self.min_efficiency
        passing = [w for w in windows if w.passed]; pass_count = len(passing); total = len(windows)
        avg_eff = sum(w.efficiency for w in windows) / total if total else 0.0
        stable_count = sum(1 for w in windows if 0.5 <= w.efficiency <= 2.0)
        stability = _safe_div(stable_count, total, 0.0)
        notes: list = []
        if total == 0: notes.append("No windows evaluated")
        elif pass_count == 0: notes.append("No windows passed")
        elif _safe_div(pass_count, total) < 0.5: notes.append(f"Only {pass_count}/{total} windows passed")
        if avg_eff > 2.0: notes.append("Avg efficiency > 2.0 — possible look-ahead bias")
        if avg_eff < 0.3 and total > 0: notes.append("Avg efficiency < 0.3 — OOS worse than IS")
        is_robust = pass_count >= max(1, total // 2) and avg_eff >= self.min_efficiency
        return WalkForwardResult(windows=windows, stability_score=round(stability,3), avg_efficiency=round(avg_eff,3), passing_windows=pass_count, total_windows=total, is_robust=is_robust, robustness_notes=notes)
