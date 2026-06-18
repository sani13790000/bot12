"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Exposure Control Engine
- Total portfolio exposure
- Per-currency exposure
- Per-symbol limits
- Max simultaneous trades
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ExposureControlConfig:
    max_total_exposure_percent: float = 5.0     # total risk all open trades
    max_per_currency_percent: float = 3.0       # risk in one currency (USD, EUR…)
    max_per_symbol_percent: float = 2.0         # risk in one symbol
    max_simultaneous_trades: int = 5
    max_buy_trades: int = 3
    max_sell_trades: int = 3
    block_same_symbol_same_direction: bool = True


@dataclass
class ExposurePosition:
    symbol: str
    direction: str          # BUY / SELL
    risk_percent: float
    risk_usd: float


@dataclass
class ExposureSnapshot:
    total_risk_percent: float
    per_currency: Dict[str, float]
    per_symbol: Dict[str, float]
    open_trades: int
    buy_trades: int
    sell_trades: int
    can_open_new: bool
    block_reason: str


@dataclass
class ExposureCheckResult:
    can_trade: bool
    reason: str
    snapshot: ExposureSnapshot
    projected_total_risk: float


class ExposureControlEngine:
    """
    Real-time exposure controller:
    - Aggregates risk across all open positions
    - Enforces per-currency + per-symbol limits
    - Tracks BUY/SELL direction counts
    - Blocks new trades when limits exceeded
    """

    # Currency contained in each symbol
    _SYMBOL_CURRENCIES: Dict[str, List[str]] = {
        "EURUSD": ["EUR", "USD"], "GBPUSD": ["GBP", "USD"],
        "AUDUSD": ["AUD", "USD"], "NZDUSD": ["NZD", "USD"],
        "USDCHF": ["USD", "CHF"], "USDJPY": ["USD", "JPY"],
        "USDCAD": ["USD", "CAD"], "EURGBP": ["EUR", "GBP"],
        "EURJPY": ["EUR", "JPY"], "GBPJPY": ["GBP", "JPY"],
        "XAUUSD": ["XAU", "USD"], "XAGUSD": ["XAG", "USD"],
        "BTCUSD": ["BTC", "USD"], "ETHUSD": ["ETH", "USD"],
    }

    def __init__(self, config: Optional[ExposureControlConfig] = None):
        self._cfg = config or ExposureControlConfig()

    def check(
        self,
        new_symbol: str,
        new_direction: str,
        new_risk_percent: float,
        open_positions: List[ExposurePosition],
        balance: float,
    ) -> ExposureCheckResult:
        snapshot = self._build_snapshot(open_positions, balance)

        # ① Max simultaneous trades
        if snapshot.open_trades >= self._cfg.max_simultaneous_trades:
            snapshot.can_open_new = False
            snapshot.block_reason = f"MAX_TRADES {snapshot.open_trades}/{self._cfg.max_simultaneous_trades}"
            return ExposureCheckResult(
                can_trade=False, reason=snapshot.block_reason,
                snapshot=snapshot, projected_total_risk=0.0,
            )

        # ② Direction limits
        if new_direction == "BUY" and snapshot.buy_trades >= self._cfg.max_buy_trades:
            snapshot.can_open_new = False
            snapshot.block_reason = f"MAX_BUY_TRADES {snapshot.buy_trades}"
            return ExposureCheckResult(
                can_trade=False, reason=snapshot.block_reason,
                snapshot=snapshot, projected_total_risk=0.0,
            )
        if new_direction == "SELL" and snapshot.sell_trades >= self._cfg.max_sell_trades:
            snapshot.can_open_new = False
            snapshot.block_reason = f"MAX_SELL_TRADES {snapshot.sell_trades}"
            return ExposureCheckResult(
                can_trade=False, reason=snapshot.block_reason,
                snapshot=snapshot, projected_total_risk=0.0,
            )

        # ③ Duplicate: same symbol + same direction
        if self._cfg.block_same_symbol_same_direction:
            for pos in open_positions:
                if pos.symbol == new_symbol and pos.direction == new_direction:
                    snapshot.can_open_new = False
                    snapshot.block_reason = f"DUPLICATE {new_symbol} {new_direction}"
                    return ExposureCheckResult(
                        can_trade=False, reason=snapshot.block_reason,
                        snapshot=snapshot, projected_total_risk=0.0,
                    )

        # ④ Total exposure
        projected_total = snapshot.total_risk_percent + new_risk_percent
        if projected_total > self._cfg.max_total_exposure_percent:
            snapshot.can_open_new = False
            snapshot.block_reason = f"MAX_EXPOSURE {projected_total:.1f}%>{self._cfg.max_total_exposure_percent}%"
            return ExposureCheckResult(
                can_trade=False, reason=snapshot.block_reason,
                snapshot=snapshot, projected_total_risk=projected_total,
            )

        # ⑤ Per-symbol exposure
        sym_risk = snapshot.per_symbol.get(new_symbol, 0.0) + new_risk_percent
        if sym_risk > self._cfg.max_per_symbol_percent:
            snapshot.can_open_new = False
            snapshot.block_reason = f"MAX_SYMBOL_EXPOSURE {new_symbol} {sym_risk:.1f}%"
            return ExposureCheckResult(
                can_trade=False, reason=snapshot.block_reason,
                snapshot=snapshot, projected_total_risk=projected_total,
            )

        # ⑥ Per-currency exposure
        currencies = self._SYMBOL_CURRENCIES.get(new_symbol.upper(), [])
        for ccy in currencies:
            ccy_risk = snapshot.per_currency.get(ccy, 0.0) + new_risk_percent
            if ccy_risk > self._cfg.max_per_currency_percent:
                snapshot.can_open_new = False
                snapshot.block_reason = f"MAX_CURRENCY_EXPOSURE {ccy} {ccy_risk:.1f}%"
                return ExposureCheckResult(
                    can_trade=False, reason=snapshot.block_reason,
                    snapshot=snapshot, projected_total_risk=projected_total,
                )

        # ✅ PASSED
        snapshot.can_open_new = True
        snapshot.block_reason = ""
        return ExposureCheckResult(
            can_trade=True,
            reason=f"EXPOSURE_OK total={projected_total:.1f}%",
            snapshot=snapshot,
            projected_total_risk=projected_total,
        )

    def _build_snapshot(self, positions: List[ExposurePosition],
                        balance: float) -> ExposureSnapshot:
        total_risk = sum(p.risk_percent for p in positions)
        per_ccy: Dict[str, float] = {}
        per_sym: Dict[str, float] = {}
        buys = sells = 0

        for p in positions:
            per_sym[p.symbol] = per_sym.get(p.symbol, 0.0) + p.risk_percent
            for ccy in self._SYMBOL_CURRENCIES.get(p.symbol.upper(), []):
                per_ccy[ccy] = per_ccy.get(ccy, 0.0) + p.risk_percent
            if p.direction == "BUY":
                buys += 1
            else:
                sells += 1

        return ExposureSnapshot(
            total_risk_percent=round(total_risk, 3),
            per_currency={k: round(v, 3) for k, v in per_ccy.items()},
            per_symbol={k: round(v, 3) for k, v in per_sym.items()},
            open_trades=len(positions),
            buy_trades=buys,
            sell_trades=sells,
            can_open_new=True,
            block_reason="",
        )


_exposure_engine: Optional[ExposureControlEngine] = None

def get_exposure_control() -> ExposureControlEngine:
    global _exposure_engine
    if _exposure_engine is None:
        _exposure_engine = ExposureControlEngine()
    return _exposure_engine
