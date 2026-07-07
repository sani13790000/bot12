"""
backend/risk/risk_orchestrator.py
Galaxy Vast AI Trading Platform — Risk Pipeline

GATE ORDER (fixed gate numbering — AI-NEW-1):
  GATE 1: KillSwitch          (emergency stop — fail-closed)
  GATE 2: NewsFilter          (block trading during high-impact events)
  GATE 3: DailyLimits         (max daily loss / max daily trades)
  GATE 4: SessionFilter       (time-of-day restrictions)
  GATE 5: CorrelationFilter   (position correlation limits)
  GATE 6: ExposureControl     (max open exposure per symbol/direction)
  GATE 7: MarginGate          (free margin sufficiency check)
  GATE 8: LotSizer            (position sizing — final output)

FIXES APPLIED:
  BUG-R4-3:  KillSwitch was instantiated fresh (new KillSwitch()) — now uses singleton get_kill_switch()
  BUG-R4-3b: ks.check() was called without required equity/balance args — now passes both correctly
  BUG-R4-3c: except ImportError silently swallowed TypeError — now uses except Exception
  BUG-R5-2:  balance=input.free_margin (semantically wrong) — now uses input.balance (total balance)
  AI-NEW-1:  Gate 5 was numbered twice (5 & 5), Gate 5.5 for MarginGate — renumbered correctly
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ── Input / Output DTOs ──────────────────────────────────────────────────────

@dataclass
class RiskInput:
    symbol: str
    direction: str           # "BUY" | "SELL"
    volume: float            # requested lot size
    entry_price: float
    sl_price: Optional[float]  = None
    tp_price: Optional[float]  = None
    # Account state — caller must populate all three
    equity:      float = 0.0  # current equity
    balance:     float = 0.0  # total account balance (NOT free_margin!)
    free_margin: float = 0.0  # available margin for new trades
    used_margin: float = 0.0  # margin already used by open positions
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskResult:
    approved: bool
    approved_volume: float = 0.0
    reject_gate:    Optional[str] = None
    reject_reason:  Optional[str] = None
    gate_details:   Dict[str, Any] = field(default_factory=dict)


# ── Gate helpers ─────────────────────────────────────────────────────────────

def _try_import(module_path: str, class_name: str) -> Optional[Any]:
    """Return class or None — never raises."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name, None)
    except Exception:
        return None


# ── Orchestrator ─────────────────────────────────────────────────────────────

class RiskOrchestrator:
    """
    Runs each risk gate in sequence.
    Any gate can reject the trade by returning approved=False.
    All gates are fail-open EXCEPT KillSwitch (GATE 1) which is fail-closed.
    """

    def __init__(self) -> None:
        self._margin_gate: Optional[Any] = None

    def _get_margin_gate(self) -> Any:
        if self._margin_gate is None:
            try:
                from backend.risk.margin_gate import MarginGate
                self._margin_gate = MarginGate()
            except ImportError:
                pass
            except Exception as exc:
                log.warning("MarginGate init failed: %s", exc)
        return self._margin_gate

    async def assess(self, inp: RiskInput) -> RiskResult:
        """
        Run all gates in order. Return on first rejection.
        Returns RiskResult with approved_volume set by LotSizer (GATE 8).
        """
        details: Dict[str, Any] = {}

        # ── GATE 1: KillSwitch (FAIL-CLOSED) ────────────────────────────────
        try:
            from backend.risk.kill_switch import get_kill_switch
            ks = get_kill_switch()  # BUG-R4-3 FIX: use singleton, not KillSwitch()
            # BUG-R5-2 FIX: balance= is total account balance, NOT free_margin
            await ks.check(equity=inp.equity, balance=inp.balance)
            details["gate_1_kill_switch"] = "passed"
        except Exception as exc:
            # Includes KillSwitchActivatedError and any other error — fail-closed
            err_name = type(exc).__name__
            log.critical("[GATE 1] KillSwitch blocked trade: %s — %s", err_name, exc)
            return RiskResult(
                approved=False,
                reject_gate="GATE_1_KILL_SWITCH",
                reject_reason=f"KillSwitch active: {exc}",
                gate_details=details,
            )

        # ── GATE 2: NewsFilter ───────────────────────────────────────────────
        NewsFilterClass = _try_import("backend.risk.news_filter", "NewsFilter")
        if NewsFilterClass is not None:
            try:
                nf = NewsFilterClass()
                result = await asyncio.wait_for(
                    nf.check(inp.symbol, inp.direction), timeout=2.0
                )
                details["gate_2_news_filter"] = getattr(result, "reason", str(result))
                if hasattr(result, "approved") and not result.approved:
                    return RiskResult(
                        approved=False,
                        reject_gate="GATE_2_NEWS_FILTER",
                        reject_reason=getattr(result, "reason", "news filter"),
                        gate_details=details,
                    )
            except asyncio.TimeoutError:
                log.warning("[GATE 2] NewsFilter timeout — skipping (fail-open)")
            except Exception as exc:
                log.warning("[GATE 2] NewsFilter error — skipping (fail-open): %s", exc)
        else:
            details["gate_2_news_filter"] = "skipped (not installed)"

        # ── GATE 3: DailyLimits ──────────────────────────────────────────────
        DailyLimitsClass = _try_import("backend.risk.daily_limits", "DailyLimits")
        if DailyLimitsClass is not None:
            try:
                dl = DailyLimitsClass()
                result = await asyncio.wait_for(
                    dl.check(inp.symbol, inp.equity, inp.balance), timeout=2.0
                )
                details["gate_3_daily_limits"] = getattr(result, "reason", str(result))
                if hasattr(result, "approved") and not result.approved:
                    return RiskResult(
                        approved=False,
                        reject_gate="GATE_3_DAILY_LIMITS",
                        reject_reason=getattr(result, "reason", "daily limit"),
                        gate_details=details,
                    )
            except asyncio.TimeoutError:
                log.warning("[GATE 3] DailyLimits timeout — skipping (fail-open)")
            except Exception as exc:
                log.warning("[GATE 3] DailyLimits error — skipping (fail-open): %s", exc)
        else:
            details["gate_3_daily_limits"] = "skipped (not installed)"

        # ── GATE 4: SessionFilter ────────────────────────────────────────────
        SessionFilterClass = _try_import("backend.risk.session_filter", "SessionFilter")
        if SessionFilterClass is not None:
            try:
                sf = SessionFilterClass()
                result = sf.check(inp.symbol)
                details["gate_4_session_filter"] = getattr(result, "reason", str(result))
                if hasattr(result, "approved") and not result.approved:
                    return RiskResult(
                        approved=False,
                        reject_gate="GATE_4_SESSION_FILTER",
                        reject_reason=getattr(result, "reason", "session filter"),
                        gate_details=details,
                    )
            except Exception as exc:
                log.warning("[GATE 4] SessionFilter error — skipping (fail-open): %s", exc)
        else:
            details["gate_4_session_filter"] = "skipped (not installed)"

        # ── GATE 5: CorrelationFilter ────────────────────────────────────────
        CorrelationFilterClass = _try_import(
            "backend.risk.correlation_filter", "CorrelationFilter"
        )
        if CorrelationFilterClass is not None:
            try:
                cf = CorrelationFilterClass()
                result = await asyncio.wait_for(
                    cf.check(inp.symbol, inp.direction, inp.volume), timeout=2.0
                )
                details["gate_5_correlation"] = getattr(result, "reason", str(result))
                if hasattr(result, "approved") and not result.approved:
                    return RiskResult(
                        approved=False,
                        reject_gate="GATE_5_CORRELATION",
                        reject_reason=getattr(result, "reason", "correlation limit"),
                        gate_details=details,
                    )
            except asyncio.TimeoutError:
                log.warning("[GATE 5] CorrelationFilter timeout — skipping (fail-open)")
            except Exception as exc:
                log.warning("[GATE 5] CorrelationFilter error — skipping: %s", exc)
        else:
            details["gate_5_correlation"] = "skipped (not installed)"

        # ── GATE 6: ExposureControl ──────────────────────────────────────────
        ExposureControlClass = _try_import(
            "backend.risk.exposure_control", "ExposureControl"
        )
        if ExposureControlClass is not None:
            try:
                ec = ExposureControlClass()
                result = await asyncio.wait_for(
                    ec.check(inp.symbol, inp.direction, inp.volume, inp.equity),
                    timeout=2.0,
                )
                details["gate_6_exposure"] = getattr(result, "reason", str(result))
                if hasattr(result, "approved") and not result.approved:
                    return RiskResult(
                        approved=False,
                        reject_gate="GATE_6_EXPOSURE",
                        reject_reason=getattr(result, "reason", "exposure limit"),
                        gate_details=details,
                    )
            except asyncio.TimeoutError:
                log.warning("[GATE 6] ExposureControl timeout — skipping (fail-open)")
            except Exception as exc:
                log.warning("[GATE 6] ExposureControl error — skipping: %s", exc)
        else:
            details["gate_6_exposure"] = "skipped (not installed)"

        # ── GATE 7: MarginGate ───────────────────────────────────────────────
        mg = self._get_margin_gate()
        if mg is not None:
            try:
                # BUG-R4-4 FIX: correct kwarg names — lot_size=, not lots=
                # BUG-R5-2 FIX: balance=inp.balance (total), not free_margin
                mg_result = await asyncio.wait_for(
                    mg.check(
                        symbol=inp.symbol,
                        lot_size=inp.volume,
                        balance=inp.balance,
                        equity=inp.equity,
                        free_margin=inp.free_margin,
                        used_margin=inp.used_margin,
                        direction=inp.direction,
                    ),
                    timeout=5.0,
                )
                details["gate_7_margin"] = {
                    "required": getattr(mg_result, "required_margin", 0),
                    "available": getattr(mg_result, "available_margin", 0),
                    "level_pct": getattr(mg_result, "margin_level_pct", 0),
                }
                if not mg_result.approved:
                    return RiskResult(
                        approved=False,
                        reject_gate="GATE_7_MARGIN",
                        reject_reason=getattr(mg_result, "reject_reason", "margin insufficient"),
                        gate_details=details,
                    )
            except asyncio.TimeoutError:
                log.warning("[GATE 7] MarginGate timeout — skipping (fail-open)")
            except Exception as exc:
                log.warning("[GATE 7] MarginGate error — skipping (fail-open): %s", exc)
        else:
            details["gate_7_margin"] = "skipped (not installed)"

        # ── GATE 8: LotSizer — final approved volume ─────────────────────────
        approved_volume = inp.volume  # default: use requested volume
        LotSizerClass = _try_import("backend.risk.lot_sizer", "LotSizer")
        if LotSizerClass is not None:
            try:
                ls = LotSizerClass()
                sized_volume = await asyncio.wait_for(
                    ls.size(
                        symbol=inp.symbol,
                        direction=inp.direction,
                        equity=inp.equity,
                        balance=inp.balance,
                        sl_price=inp.sl_price,
                        entry_price=inp.entry_price,
                        requested_volume=inp.volume,
                    ),
                    timeout=2.0,
                )
                if sized_volume and sized_volume > 0:
                    approved_volume = sized_volume
                details["gate_8_lot_sizer"] = {"approved_volume": approved_volume}
            except asyncio.TimeoutError:
                log.warning("[GATE 8] LotSizer timeout — using requested volume")
            except Exception as exc:
                log.warning("[GATE 8] LotSizer error — using requested volume: %s", exc)
        else:
            details["gate_8_lot_sizer"] = "skipped (not installed)"

        log.info(
            "[RiskOrchestrator] APPROVED %s %s %.2f lots @ %.5f",
            inp.direction, inp.symbol, approved_volume, inp.entry_price,
        )
        return RiskResult(
            approved=True,
            approved_volume=approved_volume,
            gate_details=details,
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_risk_orchestrator: Optional[RiskOrchestrator] = None


def get_risk_orchestrator() -> RiskOrchestrator:
    """Return the global RiskOrchestrator singleton."""
    global _risk_orchestrator
    if _risk_orchestrator is None:
        _risk_orchestrator = RiskOrchestrator()
    return _risk_orchestrator


risk_orchestrator: RiskOrchestrator = get_risk_orchestrator()
