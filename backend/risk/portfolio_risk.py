from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
logger = logging.getLogger("risk.portfolio")

# FIX #7: import FailMode from single source of truth (fail_mode.py)
try:
    from backend.risk.fail_mode import FailMode as FailMode  # noqa: F401
except ImportError:
    pass  # local fallback defined below if import fails

# ---------------------------------------------------------------------------
# Pip value table
# FIX #4: XAGUSD 5.0 -> 50.0  (Silver std contract = 5000 troy oz)
_PIP_VALUE_TABLE: Dict[str, float] = {
    # Forex majors (pip = 0.0001, std lot = 100000 units)
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0,
    "NZDUSD": 10.0, "USDCAD": 7.46, "USDCHF": 9.26, "USDJPY": 9.26,
    # Forex minors
    "EURGBP": 13.0, "EURJPY": 9.26, "GBPJPY": 9.26, "EURCHF": 9.26,
    "EURAUD": 7.0,  "EURCAD": 7.46, "GBPCHF": 9.26, "GBPAUD": 7.0,
    "GBPCAD": 7.46, "AUDCAD": 7.46, "AUDCHF": 9.26, "AUDJPY": 9.26,
    "CHFJPY": 9.26, "CADJPY": 9.26, "CADCHF": 9.26,
    "NZDJPY": 9.26, "NZDCAD": 7.46, "NZDCHF": 9.26,
    # Metals
    "XAUUSD": 1.0,   # Gold: $1 per 0.01 price move per oz (100 oz lot)
    "XAGUSD": 50.0,  # Silver: $50/pip (5000 oz * $0.001/oz * 10 ticks)
    "XPTUSD": 1.0,
    # Crypto
    "BTCUSD": 1.0, "ETHUSD": 1.0, "LTCUSD": 1.0, "XRPUSD": 1.0,
    # Equity indices
    "US30":   1.0, "NAS100": 1.0, "US500": 1.0, "GER40": 1.0,
    "UK100":  1.0, "JPN225": 1.0, "AUS200": 1.0,
    # Energy
    "USOIL":  1.0, "UKOIL":  1.0,
}

_SYMBOL_ALIASES: Dict[str, str] = {
    "GOLD": "XAUUSD", "SILVER": "XAGUSD", "PLATINUM": "XPTUSD",
    "BTC":  "BTCUSD", "ETH":   "ETHUSD",  "LTC":     "LTCUSD",
    "XRP":  "XRPUSD", "DAX":   "GER40",   "DAX40":   "GER40",
    "FTSE": "UK100",  "CAC40": "FRA40",   "SP500":   "US500",
    "SPX500": "US500", "DOW":  "US30",    "WTI":     "USOIL",
    "BRENT": "UKOIL", "NIKKEI": "JPN225",
}


def _resolve_canonical(symbol: str):
    sym = symbol.upper().strip()
    if sym in _PIP_VALUE_TABLE:
        return sym, "exact"
    alias = _SYMBOL_ALIASES.get(sym)
    if alias:
        return alias, "alias"
    for trim in range(1, 5):
        candidate = sym[:-trim]
        if candidate in _PIP_VALUE_TABLE:
            return candidate, "suffix"
        alias2 = _SYMBOL_ALIASES.get(candidate)
        if alias2:
            return alias2, "alias"
    return sym, "unknown"


def _get_pip_value(symbol: str, injected: Optional[float] = None) -> float:
    if injected is not None and injected > 0:
        return injected
    canonical, _ = _resolve_canonical(symbol)
    return _PIP_VALUE_TABLE.get(canonical, 1.0)


class PipValueSource(str, Enum):
    INJECTED   = "injected"
    LOT_SIZER  = "lot_sizer"
    TABLE      = "table"
    ALIAS      = "alias"
    SUFFIX     = "suffix"
    FALLBACK_FOREX       = "fallback_forex"
    FALLBACK_CONSERVATIVE = "fallback_conservative"


def _get_pip_value_with_source(symbol: str, injected: Optional[float] = None):
    if injected is not None and injected > 0:
        return injected, PipValueSource.INJECTED.value
    canonical, method = _resolve_canonical(symbol)
    val = _PIP_VALUE_TABLE.get(canonical)
    if val is not None:
        src = PipValueSource.ALIAS.value if method == "alias" else \
              PipValueSource.SUFFIX.value if method == "suffix" else \
              PipValueSource.TABLE.value
        return val, src
    return 1.0, PipValueSource.FALLBACK_CONSERVATIVE.value


async def _get_pip_value_async(symbol: str, lot_sizer=None, injected: Optional[float] = None) -> float:
    if injected is not None and injected > 0:
        return injected
    if lot_sizer is not None:
        try:
            val = await lot_sizer.get_pip_value(symbol)
            if val and val > 0:
                return float(val)
        except Exception as e:
            logger.warning("LotSizer.get_pip_value failed for %s: %s", symbol, e)
    return _get_pip_value(symbol)


# FIX #7: FailMode imported from backend.risk.fail_mode (single source of truth).
# Inline fallback retained for environments where the package is not installed.
try:
    FailMode  # noqa: F821 - already imported above
except NameError:
    class FailMode(str, Enum):  # type: ignore[no-redef]
        FAIL_CLOSED = "FAIL_CLOSED"
        FAIL_OPEN   = "FAIL_OPEN"


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
    symbol:            str
    direction:         TradeDirection
    lot_size:          float
    entry_price:       float
    stop_loss:         float
    account_balance:   float
    pip_value_per_lot: Optional[float] = None
    risk_percent:      float = field(init=False)
    risk_amount:       float = field(init=False)
    pip_value_used:    float = field(init=False)
    pip_value_source:  str   = field(init=False)
    base_currency:     str   = field(init=False)

    def __post_init__(self) -> None:
        pip_val, source       = _get_pip_value_with_source(self.symbol, self.pip_value_per_lot)
        self.pip_value_used   = pip_val
        self.pip_value_source = source
        price_distance        = abs(self.entry_price - self.stop_loss)
        self.risk_amount      = price_distance * self.lot_size * pip_val
        self.risk_percent     = (
            (self.risk_amount / self.account_balance * 100)
            if self.account_balance > 0 else 0.0
        )
        self.base_currency    = self.symbol[:3] if len(self.symbol) >= 3 else self.symbol


_STATIC_CORRELATION_TABLE: Dict[Tuple[str, str], float] = {
    ("EURUSD", "GBPUSD"): 0.85, ("EURUSD", "AUDUSD"): 0.72,
    ("EURUSD", "NZDUSD"): 0.68, ("GBPUSD", "AUDUSD"): 0.70,
    ("USDCHF", "EURUSD"): -0.92, ("USDCHF", "GBPUSD"): -0.88,
    ("XAUUSD", "EURUSD"): 0.45, ("XAUUSD", "USDCHF"): -0.55,
    ("USDJPY", "XAUUSD"): -0.40, ("BTCUSD", "ETHUSD"): 0.90,
}


@dataclass
class PortfolioRiskConfig:
    max_portfolio_risk_percent:   float    = 5.0
    max_single_trade_risk_percent: float   = 2.0
    max_correlated_exposure:      float    = 3.0
    correlation_threshold:        float    = 0.7
    fail_mode:                    FailMode = FailMode.FAIL_CLOSED


@dataclass
class PortfolioRiskResult:
    can_trade:         bool
    level:             RiskLevel
    reason:            str
    portfolio_risk_pct: float
    new_trade_risk_pct: float
    correlated_risk_pct: float


class PortfolioRiskManager:
    def __init__(
        self,
        config:       Optional[PortfolioRiskConfig] = None,
        fail_mode:    Optional[FailMode] = None,
        lot_sizer:    Optional[object]  = None,
    ) -> None:
        self._cfg = config or PortfolioRiskConfig()
        if fail_mode is not None:
            try:
                from backend.risk.fail_mode import coerce as _c
                self._fail_mode = _c(fail_mode)
            except ImportError:
                self._fail_mode = FailMode(str(fail_mode).upper())
        else:
            self._fail_mode = self._cfg.fail_mode
        self._lot_sizer = lot_sizer

    def check(
        self,
        new_trade:     OpenTradeRisk,
        open_trades:   List[OpenTradeRisk],
    ) -> PortfolioRiskResult:
        try:
            return self._check_inner(new_trade, open_trades)
        except Exception as exc:
            logger.exception("PortfolioRiskManager.check() raised %s: %s",
                             type(exc).__name__, exc, exc_info=True)
            if self._fail_mode is FailMode.FAIL_CLOSED:
                return PortfolioRiskResult(
                    can_trade=False, level=RiskLevel.BLOCKED,
                    reason=f"FAIL_CLOSED:PORTFOLIO_RISK_ERROR:{type(exc).__name__}",
                    portfolio_risk_pct=0.0, new_trade_risk_pct=0.0, correlated_risk_pct=0.0,
                )
            return PortfolioRiskResult(
                can_trade=True, level=RiskLevel.WARNING,
                reason=f"FAIL_OPEN:PORTFOLIO_RISK_ERROR:{type(exc).__name__}",
                portfolio_risk_pct=0.0, new_trade_risk_pct=0.0, correlated_risk_pct=0.0,
            )

    async def check_async(
        self,
        new_trade:   OpenTradeRisk,
        open_trades: List[OpenTradeRisk],
    ) -> PortfolioRiskResult:
        if self._lot_sizer is not None:
            try:
                live_pip = await _get_pip_value_async(new_trade.symbol, self._lot_sizer)
                if abs(live_pip - new_trade.pip_value_used) > 0.01:
                    proxy = _UpdatedTradeProxy(new_trade, live_pip)
                    return self._check_inner(proxy, open_trades)
            except Exception as e:
                logger.warning("check_async LotSizer fallback: %s", e)
        return self._check_inner(new_trade, open_trades)

    def _check_inner(
        self,
        new_trade:   object,
        open_trades: List[OpenTradeRisk],
    ) -> PortfolioRiskResult:
        current_total = sum(t.risk_percent for t in open_trades)
        new_risk      = getattr(new_trade, "risk_percent", 0.0)
        projected     = current_total + new_risk

        if new_risk > self._cfg.max_single_trade_risk_percent:
            return PortfolioRiskResult(
                can_trade=False, level=RiskLevel.BLOCKED,
                reason=(
                    f"SINGLE_TRADE_RISK_TOO_HIGH: {new_risk:.2f}% > "
                    f"{self._cfg.max_single_trade_risk_percent:.2f}%"
                ),
                portfolio_risk_pct=projected, new_trade_risk_pct=new_risk,
                correlated_risk_pct=0.0,
            )

        if projected > self._cfg.max_portfolio_risk_percent:
            return PortfolioRiskResult(
                can_trade=False, level=RiskLevel.BLOCKED,
                reason=(
                    f"PORTFOLIO_RISK_TOO_HIGH: {projected:.2f}% > "
                    f"{self._cfg.max_portfolio_risk_percent:.2f}%"
                ),
                portfolio_risk_pct=projected, new_trade_risk_pct=new_risk,
                correlated_risk_pct=0.0,
            )

        new_sym = getattr(new_trade, "symbol", "").upper()
        corr_risk = 0.0
        for t in open_trades:
            key  = (min(new_sym, t.symbol.upper()), max(new_sym, t.symbol.upper()))
            corr = abs(_STATIC_CORRELATION_TABLE.get(key, 0.0))
            if corr >= self._cfg.correlation_threshold:
                corr_risk += t.risk_percent * corr

        if corr_risk > self._cfg.max_correlated_exposure:
            return PortfolioRiskResult(
                can_trade=False, level=RiskLevel.CRITICAL,
                reason=(
                    f"CORRELATED_RISK_TOO_HIGH: {corr_risk:.2f}% > "
                    f"{self._cfg.max_correlated_exposure:.2f}%"
                ),
                portfolio_risk_pct=projected, new_trade_risk_pct=new_risk,
                correlated_risk_pct=corr_risk,
            )

        level = RiskLevel.WARNING if projected > self._cfg.max_portfolio_risk_percent * 0.8 \
                else RiskLevel.SAFE
        return PortfolioRiskResult(
            can_trade=True, level=level,
            reason="",
            portfolio_risk_pct=projected, new_trade_risk_pct=new_risk,
            correlated_risk_pct=corr_risk,
        )


class _UpdatedTradeProxy:
    def __init__(self, trade: OpenTradeRisk, new_pip: float) -> None:
        self._trade   = trade
        self._new_pip = new_pip
        price_dist    = abs(trade.entry_price - trade.stop_loss)
        self.risk_amount  = price_dist * trade.lot_size * new_pip
        self.risk_percent = (
            (self.risk_amount / trade.account_balance * 100)
            if trade.account_balance > 0 else 0.0
        )

    def __getattr__(self, name: str):
        return getattr(self._trade, name)


def get_portfolio_risk_manager(
    config: Optional[PortfolioRiskConfig] = None,
    lot_sizer=None,
) -> PortfolioRiskManager:
    return PortfolioRiskManager(config=config, lot_sizer=lot_sizer)
