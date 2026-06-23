from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("risk.portfolio_risk")

# ---------------------------------------------------------------------------
# Pip-value table  (broker-aware: FIX #4)
# ---------------------------------------------------------------------------

_PIP_VALUE_TABLE: Dict[str, float] = {
    # Forex majors
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDCAD": 10.0, "USDCHF": 10.0,
    "USDJPY": 9.09,  # ~$9.09 per pip at 110
    "EURJPY": 9.09, "GBPJPY": 9.09, "AUDJPY": 9.09,
    "NZDJPY": 9.09, "CADJPY": 9.09, "CHFJPY": 9.09,
    # Forex minors
    "EURGBP": 12.50, "EURAUD": 10.0, "EURCAD": 10.0,
    "EURCHF": 10.0,  "EURNZD": 10.0, "GBPAUD": 10.0,
    "GBPCAD": 10.0,  "GBPCHF": 10.0, "GBPNZD": 10.0,
    "AUDCAD": 10.0,  "AUDCHF": 10.0, "AUDNZD": 10.0,
    "USDMXN": 10.0,  "USDZAR": 10.0,
    # Metals
    "XAUUSD":  1.0,   # Gold: $1 per 0.01 pip (1 cent per point)
    "XAGUSD": 50.0,   # Silver: $50 per pip (5000 oz * $0.01/oz * 10 ticks)
    "XPTUSD":  1.0,
    # Crypto
    "BTCUSD": 1.0, "ETHUSD": 1.0, "LTCUSD": 1.0, "XRPUSD": 1.0,
    # Equity indices
    "US30":   1.0, "NAS100": 1.0, "US500": 1.0,
    "GER40":  1.0, "UK100":  1.0, "JPN225": 1.0, "AUS200": 1.0,
    # Energy
    "USOIL":  1.0, "UKOIL":  1.0,
}

_SYMBOL_ALIASES: Dict[str, str] = {
    "GOLD": "XAUUSD", "SILVER": "XAGUSD", "PLATINUM": "XPTUSD",
    "BTC":  "BTCUSD", "ETH":    "ETHUSD",  "LTC":      "LTCUSD",
    "XRP":  "XRPUSD",
    "DAX":  "GER40",  "DAX40":  "GER40",   "FTSE":     "UK100",
    "DOW":  "US30",   "SP500":  "US500",   "SPX500":   "US500",
    "NIKKEI": "JPN225", "ASX200": "AUS200",
    "WTI":  "USOIL",  "BRENT":  "UKOIL",   "NASDAQ":   "NAS100",
}


def _resolve_canonical(symbol: str):
    """Resolve symbol to (canonical, method) using exact/alias/suffix."""
    s = symbol.upper().strip()
    if s in _PIP_VALUE_TABLE:
        return s, "exact"
    alias = _SYMBOL_ALIASES.get(s)
    if alias and alias in _PIP_VALUE_TABLE:
        return alias, "alias"
    for trim in range(1, 5):
        if len(s) <= trim:
            break
        c = s[:-trim]
        if c in _PIP_VALUE_TABLE:
            return c, "suffix"
        al = _SYMBOL_ALIASES.get(c)
        if al and al in _PIP_VALUE_TABLE:
            return al, "suffix"
    return s, "unknown"


def _get_pip_value(symbol: str) -> float:
    """Return pip value for symbol (backward-compatible float)."""
    canonical, _ = _resolve_canonical(symbol)
    val = _PIP_VALUE_TABLE.get(canonical)
    if val is not None:
        return val
    # Fallback heuristic
    s = symbol.upper()
    if "JPY" in s:
        return 9.09
    if any(x in s for x in ("XAU", "GOLD", "XAG", "SILVER", "XPT",
                             "BTC", "ETH", "US30", "NAS", "GER",
                             "UK1", "JPN", "AUS", "OIL")):
        return 1.0
    return 10.0


class PipValueSource(str, Enum):
    INJECTED             = "INJECTED"
    LOT_SIZER            = "LOT_SIZER"
    TABLE                = "TABLE"
    ALIAS                = "ALIAS"
    SUFFIX               = "SUFFIX"
    FALLBACK_FOREX       = "FALLBACK_FOREX"
    FALLBACK_CONSERVATIVE = "FALLBACK_CONSERVATIVE"


def _get_pip_value_with_source(symbol: str, injected: Optional[float] = None):
    """Return (pip_value, PipValueSource) for audit trail."""
    if injected and injected > 0:
        return injected, PipValueSource.INJECTED
    canonical, method = _resolve_canonical(symbol)
    val = _PIP_VALUE_TABLE.get(canonical)
    if val is not None:
        source = (PipValueSource.TABLE  if method == "exact"  else
                  PipValueSource.ALIAS  if method == "alias"  else PipValueSource.SUFFIX)
        return val, source
    s = symbol.upper()
    if "JPY" in s:
        return 9.09, PipValueSource.FALLBACK_FOREX
    return 1.0, PipValueSource.FALLBACK_CONSERVATIVE


async def _get_pip_value_async(
    symbol: str,
    lot_sizer=None,
    injected: Optional[float] = None,
):
    """Async pip value: injected > LotSizer > table."""
    if injected and injected > 0:
        return injected, PipValueSource.INJECTED
    if lot_sizer is not None:
        try:
            ls_val, ls_src = await lot_sizer.get_pip_value(symbol)
            if ls_val and ls_val > 0:
                return ls_val, PipValueSource.LOT_SIZER
        except Exception as exc:
            logger.warning("LotSizer.get_pip_value(%s) failed: %s", symbol, exc)
    val, src = _get_pip_value_with_source(symbol)
    return val, src


# ---------------------------------------------------------------------------
# Correlation table
# ---------------------------------------------------------------------------

_STATIC_CORRELATIONS: Dict[Tuple[str, str], float] = {
    ("EURUSD", "GBPUSD"): 0.85,
    ("EURUSD", "AUDUSD"): 0.72,
    ("EURUSD", "NZDUSD"): 0.68, ("GBPUSD", "AUDUSD"): 0.70,
    ("USDCHF", "EURUSD"): -0.92, ("USDCHF", "GBPUSD"): -0.88,
    ("XAUUSD", "EURUSD"): 0.45, ("XAUUSD", "USDCHF"): -0.55,
    ("USDJPY", "XAUUSD"): -0.40, ("BTCUSD", "ETHUSD"): 0.90,
}


# FIX #7: canonical FailMode from single source of truth
try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce_fail_mode
except ImportError:  # pragma: no cover
    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = "FAIL_CLOSED"
        FAIL_OPEN   = "FAIL_OPEN"

    def _coerce_fail_mode(v) -> "FailMode":  # type: ignore[misc]
        return v if isinstance(v, FailMode) else FailMode(str(v).upper())


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
    """Single open trade risk record."""
    symbol:           str
    direction:        TradeDirection
    lot_size:         float
    entry_price:      float
    stop_loss:        float
    account_balance:  float
    risk_percent:     float = field(init=False)
    risk_amount:      float = field(init=False)
    pip_value_source: str   = field(init=False)
    timestamp:        str   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        pip_val, source = _get_pip_value_with_source(self.symbol)
        pip_distance     = abs(self.entry_price - self.stop_loss)
        self.risk_amount  = pip_distance * self.lot_size * pip_val
        self.risk_percent = (
            (self.risk_amount / self.account_balance) * 100
            if self.account_balance > 0 else 0.0
        )
        self.pip_value_source = source.value


@dataclass
class PortfolioRiskConfig:
    max_portfolio_risk_pct:  float    = 6.0
    max_single_symbol_pct:   float    = 2.0
    max_currency_exposure_pct: float  = 4.0
    correlation_penalty_mult: float   = 0.5
    fail_mode: FailMode               = FailMode.FAIL_CLOSED


@dataclass(frozen=True)
class PortfolioCheckResult:
    can_trade:       bool
    risk_level:      RiskLevel
    reason:          str
    total_risk_pct:  float
    new_risk_pct:    float
    remaining_cap:   float
    metadata:        Dict = field(default_factory=dict)


class PortfolioRiskManager:
    """Broker-aware portfolio risk manager (FIX #4)."""

    def __init__(
        self,
        config: Optional[PortfolioRiskConfig] = None,
        lot_sizer=None,
        fail_mode=None,
    ) -> None:
        self._cfg       = config or PortfolioRiskConfig()
        self._lot_sizer = lot_sizer
        fm = fail_mode if fail_mode is not None else self._cfg.fail_mode
        self._fail_mode = _coerce_fail_mode(fm)

    def check(
        self,
        trade: OpenTradeRisk,
        open_trades: List[OpenTradeRisk],
    ) -> PortfolioCheckResult:
        """Synchronous check (uses static table pip values)."""
        try:
            return self._check_inner(trade, open_trades)
        except Exception as exc:
            logger.exception("PortfolioRiskManager.check error: %s", exc)
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return PortfolioCheckResult(
                    can_trade=False, risk_level=RiskLevel.BLOCKED,
                    reason=f"PORTFOLIO_CHECK_ERROR: {exc}",
                    total_risk_pct=0.0, new_risk_pct=0.0, remaining_cap=0.0,
                )
            logger.critical("FAIL_OPEN: portfolio check exception swallowed: %s", exc)
            return PortfolioCheckResult(
                can_trade=True, risk_level=RiskLevel.WARNING,
                reason="FAIL_OPEN:PORTFOLIO_CHECK_ERROR",
                total_risk_pct=0.0, new_risk_pct=trade.risk_percent, remaining_cap=0.0,
            )

    async def check_async(
        self,
        trade: OpenTradeRisk,
        open_trades: List[OpenTradeRisk],
    ) -> PortfolioCheckResult:
        """Async check — uses LotSizer pip value if injected."""
        try:
            if self._lot_sizer is not None:
                pip_val, source = await _get_pip_value_async(
                    trade.symbol, lot_sizer=self._lot_sizer
                )
                table_val = _get_pip_value(trade.symbol)
                if abs(pip_val - table_val) > 0.01:
                    # Use live pip value without mutating the frozen-ish dataclass
                    pip_distance = abs(trade.entry_price - trade.stop_loss)
                    risk_amount  = pip_distance * trade.lot_size * pip_val
                    risk_pct     = (risk_amount / trade.account_balance * 100
                                    if trade.account_balance > 0 else 0.0)
                    object.__setattr__(trade, "risk_amount",      risk_amount)
                    object.__setattr__(trade, "risk_percent",     risk_pct)
                    object.__setattr__(trade, "pip_value_source", source.value)
            return self._check_inner(trade, open_trades)
        except Exception as exc:
            logger.exception("PortfolioRiskManager.check_async error: %s", exc)
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return PortfolioCheckResult(
                    can_trade=False, risk_level=RiskLevel.BLOCKED,
                    reason=f"PORTFOLIO_ASYNC_ERROR: {exc}",
                    total_risk_pct=0.0, new_risk_pct=0.0, remaining_cap=0.0,
                )
            return PortfolioCheckResult(
                can_trade=True, risk_level=RiskLevel.WARNING,
                reason="FAIL_OPEN:PORTFOLIO_ASYNC_ERROR",
                total_risk_pct=0.0, new_risk_pct=trade.risk_percent, remaining_cap=0.0,
            )

    def _check_inner(
        self,
        trade: OpenTradeRisk,
        open_trades: List[OpenTradeRisk],
    ) -> PortfolioCheckResult:
        existing_risk = sum(t.risk_percent for t in open_trades)
        new_risk      = trade.risk_percent
        total_risk    = existing_risk + new_risk
        remaining_cap = max(0.0, self._cfg.max_portfolio_risk_pct - existing_risk)

        if new_risk > self._cfg.max_single_symbol_pct:
            return PortfolioCheckResult(
                can_trade=False, risk_level=RiskLevel.BLOCKED,
                reason=f"SINGLE_TRADE_RISK {new_risk:.2f}% > {self._cfg.max_single_symbol_pct}%",
                total_risk_pct=total_risk, new_risk_pct=new_risk,
                remaining_cap=remaining_cap,
            )
        if total_risk > self._cfg.max_portfolio_risk_pct:
            return PortfolioCheckResult(
                can_trade=False, risk_level=RiskLevel.BLOCKED,
                reason=f"PORTFOLIO_RISK {total_risk:.2f}% > {self._cfg.max_portfolio_risk_pct}%",
                total_risk_pct=total_risk, new_risk_pct=new_risk,
                remaining_cap=remaining_cap,
            )
        level = (
            RiskLevel.CRITICAL if total_risk >= self._cfg.max_portfolio_risk_pct * 0.8
            else RiskLevel.WARNING if total_risk >= self._cfg.max_portfolio_risk_pct * 0.6
            else RiskLevel.SAFE
        )
        return PortfolioCheckResult(
            can_trade=True, risk_level=level,
            reason="PORTFOLIO_OK",
            total_risk_pct=total_risk, new_risk_pct=new_risk,
            remaining_cap=remaining_cap,
        )
