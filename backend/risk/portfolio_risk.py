"""
backend/risk/portfolio_risk.py
================================
FIX #4  Portfolio risk calculation using actual broker pip value
        (was Forex-only: pip_distance * lot * 100_000 * 0.0001)
FIX #6  Fail-closed mode for portfolio check
FIX #7  Removed unused asyncio.Lock

Backward-compatible:
  - OpenTradeRisk constructor signature unchanged (pip_value_per_lot is new optional kwarg)
  - PortfolioRiskManager.check() signature unchanged
  - PortfolioRiskSnapshot unchanged
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .correlation_filter import RollingCorrelationEngine

logger = logging.getLogger("risk.portfolio")


class FailMode(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN   = "FAIL_OPEN"


_PIP_VALUE_TABLE: Dict[str, float] = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDCAD":  7.7, "USDCHF": 10.7, "USDJPY":  6.7,
    "EURGBP": 12.9, "EURJPY":  6.7, "EURAUD": 10.0,
    "EURCHF": 10.7, "EURNZD": 10.0, "EURCAD":  7.7,
    "GBPJPY":  6.7, "GBPAUD": 10.0, "GBPCHF": 10.7,
    "GBPNZD": 10.0, "GBPCAD":  7.7,
    "AUDJPY":  6.7, "AUDCAD":  7.7, "AUDCHF": 10.7, "AUDNZD": 10.0,
    "CADCHF": 10.7, "CADJPY":  6.7, "CHFJPY":  6.7,
    "NZDCAD":  7.7, "NZDCHF": 10.7, "NZDJPY":  6.7,
    "XAUUSD":  1.0,  # Gold  — FIX #4 critical: was 10.0
    "XAGUSD":  5.0, "XPTUSD": 1.0, "XPDUSD": 1.0,
    "USOIL":   1.0, "UKOIL":  1.0, "NATGAS": 1.0,
    "US30":    1.0, "US500":  1.0, "NAS100": 1.0,
    "GER40":   1.0, "UK100":  1.0, "JPN225": 0.1,
    "BTCUSD":  1.0, "ETHUSD": 1.0, "LTCUSD": 1.0, "XRPUSD": 1.0,
}

_STATIC_CORRELATIONS: Dict[Tuple[str, str], float] = {
    ("EURUSD", "GBPUSD"):  0.85, ("EURUSD", "AUDUSD"):  0.72,
    ("EURUSD", "NZDUSD"):  0.68, ("GBPUSD", "AUDUSD"):  0.70,
    ("USDCHF", "EURUSD"): -0.92, ("USDCHF", "GBPUSD"): -0.88,
    ("XAUUSD", "EURUSD"):  0.45, ("XAUUSD", "USDCHF"): -0.55,
    ("USDJPY", "XAUUSD"): -0.40,
}


def _get_pip_value(symbol: str) -> float:
    """FIX #4: broker-aware pip value. NEVER silently returns 10.0 for metals/crypto."""
    sym = symbol.upper().strip()
    if sym in _PIP_VALUE_TABLE:
        return _PIP_VALUE_TABLE[sym]
    if len(sym) == 6 and sym.endswith("USD"):
        logger.warning("pip_value: unknown symbol %s — using Forex 10.0 fallback", sym)
        return 10.0
    logger.error("pip_value: unknown symbol %s, no safe fallback — using 1.0 (conservative)", sym)
    return 1.0


class RiskLevel(str, Enum):
    SAFE     = "SAFE"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"
    BLOCKED  = "BLOCKED"


class TradeDirection(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


@dataclass
class OpenTradeRisk:
    symbol:          str
    direction:       TradeDirection
    lot_size:        float
    entry_price:     float
    stop_loss:       float
    account_balance: float
    pip_value_per_lot: Optional[float] = None  # FIX #4: inject broker pip_value directly

    risk_percent: float = field(init=False)
    risk_amount:  float = field(init=False)
    base_currency: str  = field(init=False)

    def __post_init__(self) -> None:
        pip_distance = abs(self.entry_price - self.stop_loss)
        pip_val = self.pip_value_per_lot if self.pip_value_per_lot is not None else _get_pip_value(self.symbol)
        self.risk_amount  = pip_distance * self.lot_size * pip_val
        self.risk_percent = (self.risk_amount / self.account_balance * 100) if self.account_balance > 0 else 0.0
        self.base_currency = self.symbol[:3] if len(self.symbol) >= 3 else self.symbol


@dataclass
class PortfolioRiskSnapshot:
    total_risk_percent: float
    risk_level:         RiskLevel
    correlated_risk:    float
    open_trades:        int
    can_add_new:        bool
    block_reason:       str
    correlation_source: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PortfolioRiskManager:
    MAX_TOTAL_RISK_PCT = 5.0
    WARNING_RISK_PCT   = 3.0
    CRITICAL_RISK_PCT  = 4.0

    def __init__(self, fail_mode: FailMode = FailMode.FAIL_CLOSED) -> None:
        self._corr_engine = RollingCorrelationEngine(window=50, cache_ttl=60)
        # FIX #7: removed unused asyncio.Lock
        self._fail_mode = fail_mode

    def add_price_tick(self, symbol: str, price: float) -> None:
        self._corr_engine.add_price(symbol, price)

    def _get_correlation(self, sym_a: str, sym_b: str) -> Tuple[float, str]:
        try:
            rolling = self._corr_engine.get_correlation(sym_a, sym_b)
            if rolling is not None:
                return rolling, "rolling"
        except Exception as exc:
            logger.warning("Rolling corr error %s/%s: %s", sym_a, sym_b, exc)
        key, rev = (sym_a, sym_b), (sym_b, sym_a)
        if key in _STATIC_CORRELATIONS: return _STATIC_CORRELATIONS[key], "static"
        if rev in _STATIC_CORRELATIONS: return _STATIC_CORRELATIONS[rev], "static"
        return 0.0, "unknown"

    def check(self, new_trade: OpenTradeRisk, open_trades: List[OpenTradeRisk]) -> PortfolioRiskSnapshot:
        try:
            return self._check_inner(new_trade, open_trades)
        except Exception as exc:
            logger.error("PortfolioRiskManager.check exception: %s", exc, exc_info=True)
            if self._fail_mode == FailMode.FAIL_CLOSED:
                return PortfolioRiskSnapshot(
                    total_risk_percent=0.0, risk_level=RiskLevel.BLOCKED,
                    correlated_risk=0.0, open_trades=len(open_trades),
                    can_add_new=False, block_reason=f"FAIL_CLOSED: internal error — {exc}",
                    correlation_source="error",
                )
            return PortfolioRiskSnapshot(
                total_risk_percent=0.0, risk_level=RiskLevel.SAFE,
                correlated_risk=0.0, open_trades=len(open_trades),
                can_add_new=True, block_reason="", correlation_source="error_ignored",
            )

    def _check_inner(self, new_trade: OpenTradeRisk, open_trades: List[OpenTradeRisk]) -> PortfolioRiskSnapshot:
        all_trades  = open_trades + [new_trade]
        base_risk   = sum(t.risk_percent for t in all_trades)
        corr_risk   = 0.0; corr_source = "none"; seen: set = set()
        for i, t1 in enumerate(all_trades):
            for t2 in all_trades[i + 1:]:
                pair = tuple(sorted([t1.symbol, t2.symbol]))
                if pair in seen: continue
                seen.add(pair)
                corr, src = self._get_correlation(t1.symbol, t2.symbol)
                if corr_source == "none": corr_source = src
                if abs(corr) >= 0.6:
                    sign  = 1 if (t1.direction == t2.direction) else -1
                    corr_risk += abs(corr) * min(t1.risk_percent, t2.risk_percent) * sign
        total = base_risk + max(0.0, corr_risk)
        if total >= self.MAX_TOTAL_RISK_PCT:   level, can_add, br = RiskLevel.BLOCKED,   False, f"total_risk {total:.2f}% >= {self.MAX_TOTAL_RISK_PCT}%"
        elif total >= self.CRITICAL_RISK_PCT:  level, can_add, br = RiskLevel.CRITICAL,  False, f"total_risk {total:.2f}% >= {self.CRITICAL_RISK_PCT}%"
        elif total >= self.WARNING_RISK_PCT:   level, can_add, br = RiskLevel.WARNING,   True,  ""
        else:                                  level, can_add, br = RiskLevel.SAFE,       True,  ""
        return PortfolioRiskSnapshot(
            total_risk_percent=round(total, 4), risk_level=level,
            correlated_risk=round(corr_risk, 4), open_trades=len(all_trades),
            can_add_new=can_add, block_reason=br, correlation_source=corr_source,
        )
