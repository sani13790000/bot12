"""
backend/risk/portfolio_risk.py
FIX #4: Broker-aware pip value (not Forex-only formula)
FIX #5: Exposure uses real risk_percent (not hardcoded 1.0)
FIX #6: Fail-closed mode
FIX #7: Removed unused asyncio.Lock
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("risk.portfolio")


class FailMode(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN   = "FAIL_OPEN"


# FIX #4: Broker-aware pip value table (38 symbols)
# Replaces the Forex-only formula: pip_distance * lot * 100_000 * 0.0001
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
    # Metals (FIX #4 CRITICAL: XAUUSD was 10.0)
    "XAUUSD":  1.0,
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
    ("USDJPY", "XAUUSD"): -0.40, ("BTCUSD", "ETHUSD"):  0.90,
}


def _get_pip_value(symbol: str, injected: Optional[float] = None) -> Tuple[float, str]:
    """FIX #4: Returns (pip_value_per_lot, source). NEVER silently wrong."""
    if injected is not None and injected > 0:
        return injected, "injected"
    sym = symbol.upper().strip()
    if sym in _PIP_VALUE_TABLE:
        return _PIP_VALUE_TABLE[sym], "table"
    if len(sym) == 6 and sym.endswith("USD"):
        logger.warning("pip_value: unknown Forex symbol %s — using 10.0", sym)
        return 10.0, "fallback_forex"
    logger.error("pip_value: unknown symbol %s — using 1.0 (conservative)", sym)
    return 1.0, "fallback_conservative"


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
    """
    FIX #4: risk_amount uses broker-aware pip value.
    Old (Forex-only): pip_distance * lot_size * 100_000 * 0.0001
    New: price_distance * lot_size * pip_value_per_lot
    """
    symbol:            str
    direction:         TradeDirection
    lot_size:          float
    entry_price:       float
    stop_loss:         float
    account_balance:   float
    pip_value_per_lot: Optional[float] = None

    risk_percent:     float = field(init=False)
    risk_amount:      float = field(init=False)
    pip_value_used:   float = field(init=False)
    pip_value_source: str   = field(init=False)
    base_currency:    str   = field(init=False)

    def __post_init__(self) -> None:
        pip_val, source       = _get_pip_value(self.symbol, self.pip_value_per_lot)
        self.pip_value_used   = pip_val
        self.pip_value_source = source
        pip_distance          = abs(self.entry_price - self.stop_loss)
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
    """
    FIX #4: Broker-aware pip value for all asset classes.
    FIX #6: Fail-closed by default.
    FIX #7: No unused asyncio.Lock.
    """
    MAX_TOTAL_RISK_PCT = 5.0
    WARNING_RISK_PCT   = 3.0
    CRITICAL_RISK_PCT  = 4.0

    def __init__(self, fail_mode: FailMode = FailMode.FAIL_CLOSED, corr_engine=None) -> None:
        self._fail_mode   = fail_mode
        self._corr_engine = corr_engine

    def add_price_tick(self, symbol: str, price: float) -> None:
        if self._corr_engine is not None:
            try:
                self._corr_engine.add_price(symbol, price)
            except Exception as exc:
                logger.warning("add_price_tick error %s: %s", symbol, exc)

    def _get_correlation(self, sym_a: str, sym_b: str) -> Tuple[float, str]:
        if self._corr_engine is not None:
            try:
                rolling = self._corr_engine.get_correlation(sym_a, sym_b)
                if rolling is not None:
                    return rolling, "rolling"
            except Exception as exc:
                logger.warning("Rolling corr error %s/%s: %s", sym_a, sym_b, exc)
        key = (sym_a, sym_b)
        rev = (sym_b, sym_a)
        val = _STATIC_CORRELATIONS.get(key) or _STATIC_CORRELATIONS.get(rev)
        if val is not None:
            return val, "static"
        return 0.0, "none"

    def check(self, new_trade: OpenTradeRisk, open_trades: List[OpenTradeRisk]) -> PortfolioRiskSnapshot:
        """FIX #6: exception → FAIL_CLOSED block. Signature unchanged."""
        try:
            return self._check_inner(new_trade, open_trades)
        except Exception as exc:
            logger.exception("portfolio_risk.check() error %s: %s — mode=%s",
                             new_trade.symbol, exc, self._fail_mode)
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return PortfolioRiskSnapshot(
                    total_risk_percent=0.0, risk_level=RiskLevel.BLOCKED,
                    correlated_risk=0.0, open_trades=len(open_trades),
                    can_add_new=False,
                    block_reason=f"INTERNAL_ERROR:{type(exc).__name__}",
                    correlation_source="error",
                )
            logger.critical("portfolio_risk FAIL_OPEN — trade allowed despite error for %s", new_trade.symbol)
            return PortfolioRiskSnapshot(
                total_risk_percent=0.0, risk_level=RiskLevel.SAFE,
                correlated_risk=0.0, open_trades=len(open_trades),
                can_add_new=True, block_reason="FAIL_OPEN_EXCEPTION_IGNORED",
                correlation_source="error",
            )

    def _check_inner(self, new_trade: OpenTradeRisk, open_trades: List[OpenTradeRisk]) -> PortfolioRiskSnapshot:
        total_existing  = sum(t.risk_percent for t in open_trades)
        projected_total = total_existing + new_trade.risk_percent
        corr_risk = new_trade.risk_percent
        corr_source = "none"
        for existing in open_trades:
            corr, src = self._get_correlation(new_trade.symbol, existing.symbol)
            corr_risk += abs(corr) * existing.risk_percent
            if src != "none":
                corr_source = src
        if projected_total >= self.MAX_TOTAL_RISK_PCT:
            return PortfolioRiskSnapshot(
                total_risk_percent=round(projected_total, 4),
                risk_level=RiskLevel.BLOCKED, correlated_risk=round(corr_risk, 4),
                open_trades=len(open_trades), can_add_new=False,
                block_reason=f"TOTAL_RISK_EXCEEDED:{projected_total:.2f}%>={self.MAX_TOTAL_RISK_PCT}%",
                correlation_source=corr_source,
            )
        level = (RiskLevel.CRITICAL if projected_total >= self.CRITICAL_RISK_PCT
                 else RiskLevel.WARNING if projected_total >= self.WARNING_RISK_PCT
                 else RiskLevel.SAFE)
        return PortfolioRiskSnapshot(
            total_risk_percent=round(projected_total, 4),
            risk_level=level, correlated_risk=round(corr_risk, 4),
            open_trades=len(open_trades), can_add_new=True, block_reason="",
            correlation_source=corr_source,
        )
