"""backend/risk/risk_orchestrator.py
FIX #5 - Exposure Control Using Real Risk
FIX #6 - Fail-Closed Mode (configurable per gate)
FIX #7 - Dead code removal: removed 'import asyncio' (zero usages)
FIX #8 - Interface Consistency Audit patches:
  ISSUE-1: RiskInput dataclass (ImportError fix)
  ISSUE-2: RiskCheckResult.to_dict() (AttributeError fix)
  ISSUE-3: RiskOrchestrator.assess() method (AttributeError fix)
  ISSUE-4: _run_vol_gate kwarg fix (price_distance/entry_price invalid)
  ISSUE-5: _run_corr_gate kwarg fix (symbol->new_symbol, add base_risk_percent)
  ISSUE-6: LotSizer.calculate kwarg fix (account_balance->balance, lot_multiplier->volatility_ratio)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# FIX-6: canonical FailMode
try:
    from backend.risk.fail_mode import FailMode, coerce as _coerce
except ImportError:
    class FailMode(str, Enum):   # type: ignore[no-redef]
        FAIL_CLOSED = "FAIL_CLOSED"
        FAIL_OPEN   = "FAIL_OPEN"

    def _coerce(v) -> FailMode:  # type: ignore[misc]
        if isinstance(v, FailMode):
            return v
        return FailMode(str(v).upper())

try:
    from backend.risk._pip_helpers import _price_to_pips
    from backend.risk._pip_helpers import _estimate_risk_pct
except ImportError:
    def _price_to_pips(sym, d): return d * 10_000  # type: ignore
    def _estimate_risk_pct(sym, pd, lot, bal): return (0.0, "none")  # type: ignore

logger = logging.getLogger("risk.orchestrator")


# FIX-5B: clamp helper
def _clamp_risk(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


class RiskDecision(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED  = "BLOCKED"
    ERROR    = "ERROR"


@dataclass
class RiskCheckResult:
    decision:       RiskDecision
    approved:       bool
    block_reason:   str
    risk_percent:   float
    lot_size:       float
    lot_multiplier: float
    gates_passed:   List[str]       = field(default_factory=list)
    gates_failed:   List[str]       = field(default_factory=list)
    metadata:       Dict[str, Any]  = field(default_factory=dict)

    # ISSUE-2 FIX: routes_risk calls decision.to_dict()
    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved":       self.approved,
            "decision":       self.decision.value,
            "block_reason":   self.block_reason,
            "risk_percent":   self.risk_percent,
            "lot_size":       self.lot_size,
            "lot_multiplier": self.lot_multiplier,
            "gates_passed":   self.gates_passed,
            "gates_failed":   self.gates_failed,
            "metadata":       self.metadata,
        }


# ISSUE-1 FIX: routes_risk imports RiskInput from this module
@dataclass
class RiskInput:
    """Input DTO for RiskOrchestrator.assess(). Bridges route layer to check()."""
    symbol:             str
    direction:          str
    balance:            float
    stop_loss_pips:     float
    entry_price:        float            = 0.0
    stop_loss:          float            = 0.0
    equity:             float            = 0.0
    current_atr:        float            = 10.0
    atr_history:        List[float]      = field(default_factory=list)
    current_spread:     float            = 0.0
    avg_spread:         float            = 0.0
    open_positions:     List[Any]        = field(default_factory=list)
    today_trades_count: int              = 0
    today_pnl_usd:      float            = 0.0
    week_pnl_usd:       float            = 0.0
    month_pnl_usd:      float            = 0.0
    user_id:            str              = ""
    signal_id:          str              = ""
    override_risk_pct:  Optional[float]  = None


class RiskOrchestrator:
    def __init__(
        self,
        equity_guard=None,
        daily_limits=None,
        volatility_filter=None,
        correlation_filter=None,
        exposure_control=None,
        lot_sizer=None,
        # FIX-6B: per-gate fail_mode (default FAIL_CLOSED)
        fail_mode_equity:      Any = FailMode.FAIL_CLOSED,
        fail_mode_daily:       Any = FailMode.FAIL_CLOSED,
        fail_mode_volatility:  Any = FailMode.FAIL_CLOSED,
        fail_mode_correlation: Any = FailMode.FAIL_CLOSED,
        fail_mode_lot:         Any = FailMode.FAIL_CLOSED,
        fail_mode_exposure:    Any = FailMode.FAIL_CLOSED,
        # FIX-5A: replaces hardcoded 1.0
        default_risk_percent:  float = 1.0,
    ) -> None:
        if default_risk_percent <= 0:
            raise ValueError(f"default_risk_percent must be > 0, got {default_risk_percent}")
        self._equity     = equity_guard
        self._daily      = daily_limits
        self._vol        = volatility_filter
        self._corr       = correlation_filter
        self._exposure   = exposure_control
        self._lot_sizer  = lot_sizer
        # FIX-6D: coerce all modes
        self._fail_equity  = _coerce(fail_mode_equity)
        self._fail_daily   = _coerce(fail_mode_daily)
        self._fail_vol     = _coerce(fail_mode_volatility)
        self._fail_corr    = _coerce(fail_mode_correlation)
        self._fail_lot     = _coerce(fail_mode_lot)
        self._fail_exp     = _coerce(fail_mode_exposure)
        self._default_risk = default_risk_percent

    async def check(
        self,
        symbol:          str,
        direction:       str,
        entry_price:     float,
        stop_loss:       float,
        account_balance: float,
        user_id:         str = "",
        signal_id:       str = "",
        override_risk_pct: Optional[float] = None,
        **ctx,
    ) -> RiskCheckResult:
        passed:  List[str]       = []
        failed:  List[str]       = []
        meta:    Dict[str, Any]  = {}

        pd  = abs(entry_price - stop_loss)
        slp = _price_to_pips(symbol, pd)
        meta["sl_conversion"] = {"price_distance": pd, "stop_loss_pips": slp, "symbol": symbol}

        # Gate 1: Equity
        if self._equity is not None:
            try:
                eq = await self._run_equity_gate(user_id, account_balance, ctx)
                if not eq["can_trade"]:
                    return self._blk(eq["reason"], passed, ["EQUITY"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("EQUITY")
                meta["equity"] = eq
            except Exception as e:
                logger.critical("EQUITY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_equity, e, exc_info=True)
                if self._fail_equity is FailMode.FAIL_CLOSED:
                    return self._fcr("EQUITY_GATE_ERROR", passed, failed, meta)
                passed.append("EQUITY_FAIL_OPEN")

        # Gate 2: Daily Limits
        if self._daily is not None:
            try:
                dl = await self._run_daily_gate(user_id, ctx)
                if not dl["can_trade"]:
                    return self._blk(dl["reason"], passed, ["DAILY_LIMITS"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("DAILY_LIMITS")
                meta["daily"] = dl
            except Exception as e:
                logger.critical("DAILY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_daily, e, exc_info=True)
                if self._fail_daily is FailMode.FAIL_CLOSED:
                    return self._fcr("DAILY_LIMITS_GATE_ERROR", passed, failed, meta)
                passed.append("DAILY_LIMITS_FAIL_OPEN")

        # Gate 3: Volatility
        lm = 1.0
        if self._vol is not None:
            try:
                vr = await self._run_vol_gate(symbol, pd, entry_price, ctx)
                if not vr["can_trade"]:
                    return self._blk(vr["reason"], passed, ["VOLATILITY"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("VOLATILITY")
                lm = vr.get("lot_multiplier", 1.0)
                meta["volatility"] = vr
            except Exception as e:
                logger.critical("VOLATILITY gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_vol, e, exc_info=True)
                if self._fail_vol is FailMode.FAIL_CLOSED:
                    return self._fcr("VOLATILITY_GATE_ERROR", passed, failed, meta)
                passed.append("VOLATILITY_FAIL_OPEN")

        # Gate 4: Correlation
        if self._corr is not None:
            try:
                cr = await self._run_corr_gate(symbol, direction, ctx)
                if not cr["can_trade"]:
                    return self._blk(cr["reason"], passed, ["CORRELATION"] + failed, meta, 0.0, 0.0, 0.0)
                passed.append("CORRELATION")
                meta["correlation"] = cr
            except Exception as e:
                logger.critical("CORR gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_corr, e, exc_info=True)
                if self._fail_corr is FailMode.FAIL_CLOSED:
                    return self._fcr("CORRELATION_GATE_ERROR", passed, failed, meta)
                passed.append("CORRELATION_FAIL_OPEN")

        # Gate 5: Lot Sizing (preliminary)
        pl  = 0.01
        arp = 0.0
        rs  = "unknown"
        if self._lot_sizer is not None:
            try:
                lot_res = await self._lot_sizer.calculate(
                    balance=account_balance,
                    stop_loss_pips=max(slp, 0.1),
                    symbol=symbol,
                    volatility_ratio=lm,
                    override_risk_pct=override_risk_pct,
                )
                pl  = getattr(lot_res, "lot_size",     pl)
                arp = _clamp_risk(getattr(lot_res, "risk_percent", self._default_risk))
                rs  = "lot_sizer"
                meta["lot_sizing"] = {"lot_size": pl, "risk_percent": arp, "risk_source": rs}
                if pl <= 0:
                    return self._blk("LOT_SIZING_ZERO", passed, ["LOT_SIZING"] + failed, meta, arp, 0.0, lm)
                passed.append("LOT_SIZING")
            except Exception as e:
                logger.critical("LOT gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_lot, e, exc_info=True)
                if self._fail_lot is FailMode.FAIL_CLOSED:
                    return self._fcr("LOT_SIZING_GATE_ERROR", passed, failed, meta)
                passed.append("LOT_SIZING_FAIL_OPEN")
                arp = _clamp_risk(self._default_risk)
                rs  = "config_fallback"
        else:
            if override_risk_pct and override_risk_pct > 0:
                arp = _clamp_risk(override_risk_pct)
                rs  = "override"
            else:
                est_raw, est_src = _estimate_risk_pct(symbol, pd, pl, account_balance)
                if est_raw > 0:
                    arp = _clamp_risk(est_raw)
                    rs  = f"estimated:{est_src}"
                else:
                    arp = _clamp_risk(self._default_risk)
                    rs  = "config_fallback"

        # Gate 6: Exposure
        if self._exposure is not None:
            try:
                ops = _normalise_positions(ctx.get("open_positions", []))
                er  = await self._run_exposure_gate(symbol, direction, arp, ops)
                if not er["can_trade"]:
                    return self._blk(er["reason"], passed, ["EXPOSURE"] + failed, meta, arp, 0.0, lm)
                er["risk_source"] = rs
                passed.append("EXPOSURE")
                meta["exposure"] = er
            except Exception as e:
                logger.critical("EXP gate exception symbol=%s fail_mode=%s: %s",
                                symbol, self._fail_exp, e, exc_info=True)
                if self._fail_exp is FailMode.FAIL_CLOSED:
                    return self._fcr("EXPOSURE_GATE_ERROR", passed, failed, meta)
                passed.append("EXPOSURE_FAIL_OPEN")

        return RiskCheckResult(
            RiskDecision.APPROVED, True, "",
            arp, pl, lm,
            gates_passed=passed, gates_failed=failed, metadata=meta,
        )

    # ISSUE-3 FIX: routes_risk calls RiskOrchestrator().assess(inp)
    async def assess(self, inp: "RiskInput") -> "RiskCheckResult":
        """Convenience wrapper: RiskInput -> check().
        ARCH: routes_risk and external callers use this DTO-based API.
        """
        if inp.entry_price == 0.0 and inp.stop_loss == 0.0:
            # Reconstruct price levels from stop_loss_pips for gates that need them.
            sl_price_dist = inp.stop_loss_pips / 10_000.0
            entry_price   = 1.0 + sl_price_dist
            stop_loss     = 1.0
        else:
            entry_price = inp.entry_price
            stop_loss   = inp.stop_loss

        return await self.check(
            symbol            = inp.symbol,
            direction         = inp.direction,
            entry_price       = entry_price,
            stop_loss         = stop_loss,
            account_balance   = inp.balance,
            user_id           = inp.user_id,
            signal_id         = inp.signal_id,
            override_risk_pct = inp.override_risk_pct,
            # volatility / spread context forwarded via **ctx
            current_atr       = inp.current_atr,
            atr_history       = inp.atr_history,
            current_spread    = inp.current_spread,
            avg_spread        = inp.avg_spread,
            open_positions    = inp.open_positions,
            today_trades_count = inp.today_trades_count,
            today_pnl_usd     = inp.today_pnl_usd,
            week_pnl_usd      = inp.week_pnl_usd,
            month_pnl_usd     = inp.month_pnl_usd,
        )

    # -- Gate runners --

    async def _run_equity_gate(self, u, b, ctx):
        r = self._equity
        if hasattr(r, "check"):
            res = r.check(user_id=u, account_balance=b, **ctx)
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_daily_gate(self, u, ctx):
        r = self._daily
        if hasattr(r, "check"):
            res = r.check(user_id=u)
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_vol_gate(self, symbol, pd, entry, ctx):
        r = self._vol
        if hasattr(r, "check"):
            # ISSUE-4 FIX: VolatilityFilter.check(current_atr, atr_history, current_spread, avg_spread, symbol)
            # price_distance/entry_price are NOT valid VF params; extract valid ones from ctx only.
            current_atr    = float(ctx.get("current_atr", max(pd * 10_000, 10.0)))
            atr_history    = ctx.get("atr_history", None)
            current_spread = float(ctx.get("current_spread", 0.0))
            avg_spread     = float(ctx.get("avg_spread", 0.0))
            res = r.check(
                current_atr    = current_atr,
                atr_history    = atr_history,
                current_spread = current_spread,
                avg_spread     = avg_spread,
                symbol         = symbol,
            )
            if hasattr(res, "__await__"): res = await res
            return {
                "can_trade":      getattr(res, "can_trade",      True),
                "reason":         getattr(res, "reason",         ""),
                "lot_multiplier": getattr(res, "lot_multiplier", 1.0),
            }
        return {"can_trade": True, "reason": "", "lot_multiplier": 1.0}

    async def _run_corr_gate(self, symbol, direction, ctx):
        r = self._corr
        if hasattr(r, "check"):
            # ISSUE-5 FIX: CorrelationFilter.check(new_symbol, new_direction, open_positions, base_risk_percent)
            # Keyword names differ from orchestrator locals; map explicitly.
            open_positions    = _normalise_positions(ctx.get("open_positions", []))
            base_risk_percent = float(ctx.get("base_risk_percent",
                                              ctx.get("risk_percent", self._default_risk)))
            res = r.check(
                new_symbol        = symbol,
                new_direction     = direction,
                open_positions    = open_positions,
                base_risk_percent = base_risk_percent,
            )
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}
        return {"can_trade": True, "reason": ""}

    async def _run_exposure_gate(self, symbol, direction, arp, ops):
        r = self._exposure
        if hasattr(r, "check"):
            res = r.check(symbol, direction, arp, ops)
            if hasattr(res, "__await__"): res = await res
            return {"can_trade": getattr(res, "can_trade", True), "reason": getattr(res, "reason", "")}
        return {"can_trade": True, "reason": ""}

    @staticmethod
    def _fcr(r, p, f, m) -> RiskCheckResult:
        return RiskCheckResult(
            RiskDecision.BLOCKED, False, r, 0.0, 0.0, 0.0,
            gates_passed=p, gates_failed=[r] + f, metadata=m,
        )

    @staticmethod
    def _blk(r, p, f, m, rp, ls, lm) -> RiskCheckResult:
        return RiskCheckResult(
            RiskDecision.BLOCKED, False, r, rp, ls, lm,
            gates_passed=p, gates_failed=f, metadata=m,
        )


def _normalise_positions(positions) -> list:
    try:
        from backend.risk.exposure_control import ExposurePosition
    except Exception:
        from types import SimpleNamespace as ExposurePosition  # type: ignore
    result = []
    for p in positions:
        if isinstance(p, dict):
            try:
                ep = ExposurePosition(
                    symbol        = str(p.get("symbol", "")),
                    direction     = str(p.get("direction", "BUY")),
                    risk_percent  = float(p.get("risk_percent", 0.0)),
                    risk_usd      = float(p.get("risk_usd",     0.0)),
                )
                result.append(ep)
            except Exception as e:
                logger.warning("Skipping invalid position dict: %s - %s", p, e)
        else:
            result.append(p)
    return result
