"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dynamic Lot Sizing & ATR Position Sizing Engine
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class LotSizingMethod(str, Enum):
    FIXED_PERCENT   = "FIXED_PERCENT"    # % of balance
    ATR_BASED       = "ATR_BASED"        # ATR-normalised risk
    FIXED_LOT       = "FIXED_LOT"        # static lot
    KELLY           = "KELLY"            # Kelly Criterion (capped)
    VOLATILITY_ADJ  = "VOLATILITY_ADJ"   # scaled by realised vol


@dataclass
class LotSizingConfig:
    method: LotSizingMethod = LotSizingMethod.ATR_BASED
    risk_percent: float = 1.0           # % of balance per trade
    fixed_lot: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 5.0
    lot_step: float = 0.01
    atr_multiplier: float = 1.5         # SL = ATR × multiplier
    kelly_fraction: float = 0.25        # fractional Kelly
    max_risk_percent: float = 2.0       # hard cap per trade
    pip_value_usd: float = 10.0         # per standard lot per pip
    contract_size: float = 100_000.0    # standard lot size


@dataclass
class LotSizingResult:
    lot_size: float
    method_used: LotSizingMethod
    risk_amount_usd: float
    risk_percent: float
    stop_loss_pips: float
    atr_value: float
    balance: float
    notes: str = ""


class DynamicLotSizer:
    """
    Production-grade Dynamic Lot Sizer supporting:
    - ATR-based position sizing (primary method)
    - Fixed % risk
    - Kelly Criterion (capped)
    - Volatility-adjusted sizing
    - Hard lot limits enforcement
    """

    def __init__(self, config: Optional[LotSizingConfig] = None):
        self._cfg = config or LotSizingConfig()

    # ── public API ──────────────────────────────────────────────

    def calculate(
        self,
        balance: float,
        stop_loss_pips: float,
        atr_pips: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_rr: Optional[float] = None,
        volatility_ratio: float = 1.0,
    ) -> LotSizingResult:
        """Calculate optimal lot size based on configured method."""
        if balance <= 0 or stop_loss_pips <= 0:
            return self._zero_result(balance, stop_loss_pips, atr_pips or 0.0)

        method = self._cfg.method
        if method == LotSizingMethod.FIXED_PERCENT:
            lot = self._fixed_percent(balance, stop_loss_pips)
        elif method == LotSizingMethod.ATR_BASED:
            lot = self._atr_based(balance, atr_pips or stop_loss_pips, stop_loss_pips)
        elif method == LotSizingMethod.FIXED_LOT:
            lot = self._cfg.fixed_lot
        elif method == LotSizingMethod.KELLY:
            lot = self._kelly(balance, stop_loss_pips, win_rate or 0.55, avg_rr or 1.5)
        elif method == LotSizingMethod.VOLATILITY_ADJ:
            lot = self._volatility_adj(balance, stop_loss_pips, volatility_ratio)
        else:
            lot = self._fixed_percent(balance, stop_loss_pips)

        lot = self._clamp(lot)
        risk_usd = lot * stop_loss_pips * self._cfg.pip_value_usd
        risk_pct = (risk_usd / balance) * 100 if balance > 0 else 0.0

        # Hard cap: never risk more than max_risk_percent
        if risk_pct > self._cfg.max_risk_percent:
            lot = self._max_safe_lot(balance, stop_loss_pips)
            lot = self._clamp(lot)
            risk_usd = lot * stop_loss_pips * self._cfg.pip_value_usd
            risk_pct = (risk_usd / balance) * 100

        return LotSizingResult(
            lot_size=lot,
            method_used=method,
            risk_amount_usd=round(risk_usd, 2),
            risk_percent=round(risk_pct, 3),
            stop_loss_pips=stop_loss_pips,
            atr_value=atr_pips or 0.0,
            balance=balance,
            notes=f"method={method.value} cap={self._cfg.max_risk_percent}%",
        )

    # ── sizing methods ──────────────────────────────────────────

    def _fixed_percent(self, balance: float, sl_pips: float) -> float:
        risk_usd = balance * (self._cfg.risk_percent / 100.0)
        pip_val  = self._cfg.pip_value_usd
        return risk_usd / (sl_pips * pip_val) if sl_pips > 0 else 0.0

    def _atr_based(self, balance: float, atr_pips: float, sl_pips: float) -> float:
        """ATR-normalised: SL expressed as ATR multiple."""
        adjusted_sl = max(sl_pips, atr_pips * self._cfg.atr_multiplier)
        return self._fixed_percent(balance, adjusted_sl)

    def _kelly(self, balance: float, sl_pips: float,
               win_rate: float, avg_rr: float) -> float:
        """
        Kelly Criterion: f* = p - q/b
        p = win rate, q = loss rate, b = avg reward/risk
        Applies fractional Kelly for safety.
        """
        p = max(0.01, min(win_rate, 0.99))
        q = 1.0 - p
        b = max(0.1, avg_rr)
        kelly_f = p - (q / b)
        kelly_f = max(0.0, kelly_f) * self._cfg.kelly_fraction
        risk_usd = balance * kelly_f
        pip_val  = self._cfg.pip_value_usd
        return risk_usd / (sl_pips * pip_val) if sl_pips > 0 else 0.0

    def _volatility_adj(self, balance: float, sl_pips: float,
                        vol_ratio: float) -> float:
        """Scale base lot inversely to volatility ratio."""
        base_lot = self._fixed_percent(balance, sl_pips)
        factor   = 1.0 / max(vol_ratio, 0.1)
        factor   = max(0.3, min(factor, 2.0))   # clamp 0.3–2.0×
        return base_lot * factor

    # ── helpers ─────────────────────────────────────────────────

    def _max_safe_lot(self, balance: float, sl_pips: float) -> float:
        max_risk_usd = balance * (self._cfg.max_risk_percent / 100.0)
        return max_risk_usd / (sl_pips * self._cfg.pip_value_usd)

    def _clamp(self, lot: float) -> float:
        lot = max(self._cfg.min_lot, min(lot, self._cfg.max_lot))
        step = self._cfg.lot_step
        return math.floor(lot / step) * step

    def _zero_result(self, balance, sl_pips, atr) -> LotSizingResult:
        return LotSizingResult(
            lot_size=self._cfg.min_lot,
            method_used=self._cfg.method,
            risk_amount_usd=0.0,
            risk_percent=0.0,
            stop_loss_pips=sl_pips,
            atr_value=atr,
            balance=balance,
            notes="FALLBACK: invalid inputs → min lot",
        )

    def update_config(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._cfg, k):
                setattr(self._cfg, k, v)

    @property
    def config(self) -> LotSizingConfig:
        return self._cfg


# Global singleton
_lot_sizer: Optional[DynamicLotSizer] = None

def get_lot_sizer() -> DynamicLotSizer:
    global _lot_sizer
    if _lot_sizer is None:
        _lot_sizer = DynamicLotSizer()
    return _lot_sizer
