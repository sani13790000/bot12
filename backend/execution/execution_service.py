"""Galaxy Vast AI Trading Platform
Execution Service - FIX-1 + FIX-2

FIX-1: Duplicate Order after Retry
  - signal_id idempotency store with TTL
  - Position reconciliation BEFORE every retry
  - Release idempotency on rejection so retry can re-check

FIX-2: Retry Queue
  - asyncio.Queue passed to FailureRecoveryEngine

CRITICAL-1 FIX: asyncio.Lock() module-level -> lazy init via _get_*_lock()
  Python 3.12+: asyncio.Lock() at import time raises RuntimeError: no running event loop.
  Also breaks on uvicorn --reload (lock detached from new loop).

CRITICAL-2 FIX: self._pr.set_mt5(self._mt5) in start()
  PositionReconciliation._mt5 was always None -> all duplicate checks returned False
  -> MT5 received duplicate order_send() on every retry.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, Optional, Set

from ..core.config import settings
from ..core.logger import get_logger
from ..risk.risk_orchestrator import RiskInput, RiskOrchestrator, get_risk_orchestrator
from ..risk.exposure_control import ExposurePosition
from .mt5_connector import MT5Connector, MT5OrderRequest, mt5_connector as _mt5
from .order_state_machine import ManagedOrder, OrderState, OrderStateMachine, order_state_machine as _osm
from .failure_recovery import FailureRecoveryEngine, RecoveryStrategy, failure_recovery as _fr
from .position_reconciliation import PositionReconciliation, position_reconciliation as _pr
from .semi_auto import SemiAutoManager

logger = get_logger("execution.execution_service")

# FIX-1: idempotency store
_IDEMPOTENCY_STORE: Dict[str, str] = {}
_INFLIGHT_SIGNALS: Set[str] = set()
_IDEMPOTENCY_TTL = 600
_IDEMPOTENCY_TIMESTAMPS: Dict[str, float] = {}

# CRITICAL-1 FIX: asyncio.Lock() must NOT be created at module import time.
# Python 3.10: DeprecationWarning; Python 3.12+: RuntimeError: no running event loop.
# Also broken on uvicorn --reload: pre-existing lock detached from new event loop.
# Solution: lazy init inside running event loop via getter functions.
_IDEMPOTENCY_LOCK: Optional[asyncio.Lock] = None
_INFLIGHT_LOCK:    Optional[asyncio.Lock] = None


def _get_idempotency_lock() -> asyncio.Lock:
    """Lazy-init idempotency lock. Always called from within a running event loop."""
    global _IDEMPOTENCY_LOCK
    if _IDEMPOTENCY_LOCK is None:
        _IDEMPOTENCY_LOCK = asyncio.Lock()
    return _IDEMPOTENCY_LOCK


def _get_inflight_lock() -> asyncio.Lock:
    """Lazy-init inflight lock. Always called from within a running event loop."""
    global _INFLIGHT_LOCK
    if _INFLIGHT_LOCK is None:
        _INFLIGHT_LOCK = asyncio.Lock()
    return _INFLIGHT_LOCK


async def _idempotency_check(signal_id: str) -> Optional[str]:
    """Returns existing order_id if already executed, else None. Evicts stale keys."""
    now = time.monotonic()
    async with _get_idempotency_lock():
        stale = [k for k, ts in _IDEMPOTENCY_TIMESTAMPS.items() if now - ts > _IDEMPOTENCY_TTL]
        for k in stale:
            _IDEMPOTENCY_STORE.pop(k, None)
            _IDEMPOTENCY_TIMESTAMPS.pop(k, None)
        return _IDEMPOTENCY_STORE.get(signal_id)


async def _idempotency_register(signal_id: str, order_id: str) -> None:
    async with _get_idempotency_lock():
        _IDEMPOTENCY_STORE[signal_id] = order_id
        _IDEMPOTENCY_TIMESTAMPS[signal_id] = time.monotonic()


async def _idempotency_release(signal_id: str) -> None:
    async with _get_idempotency_lock():
        _IDEMPOTENCY_STORE.pop(signal_id, None)
        _IDEMPOTENCY_TIMESTAMPS.pop(signal_id, None)


class ExecutionService:
    """
    Orchestrates the full execution pipeline.
    FIX-1: Idempotency key prevents duplicate orders after retry.
            Position reconciliation before every retry.
    FIX-2: asyncio.Queue in FailureRecoveryEngine.
    CRITICAL-1: Module-level asyncio.Lock() replaced with lazy init.
    CRITICAL-2: self._pr.set_mt5(self._mt5) called in start().
    T-1:   RiskOrchestrator.assess() before every order.
    T-2:   Signal dedup via _INFLIGHT_SIGNALS.
    T-3:   semi_auto driven by settings.SEMI_AUTO_MODE.
    T-4:   FailureRecoveryEngine gets _retry_execute callback.
    """

    def __init__(self, mt5=None, osm=None, recovery=None, reconciliation=None, risk=None):
        self._mt5  = mt5  or _mt5
        self._osm  = osm  or _osm
        self._fr   = recovery or _fr
        self._pr   = reconciliation or _pr
        self._risk: Optional[RiskOrchestrator] = risk
        self._semi_auto_enabled: bool = getattr(settings, "SEMI_AUTO_MODE", False)
        self._semi_auto = SemiAutoManager()
        self._running = False

    async def start(self) -> None:
        await self._mt5.initialize()
        await self._osm.start()
        self._fr.set_retry_callback(self._retry_execute)
        await self._fr.start()
        # CRITICAL-2 FIX: Wire MT5Connector into PositionReconciliation BEFORE start().
        # Without this, self._pr._mt5 is always None:
        #   - check_symbol_already_open() -> returns has_duplicate=False unconditionally
        #   - verify_position_exists()    -> returns already_filled=False unconditionally
        # Result: no duplicate detection -> MT5 receives duplicate order_send() on every retry.
        self._pr.set_mt5(self._mt5)
        await self._pr.start()
        if self._semi_auto_enabled:
            await self._semi_auto.start()
        if self._risk is None:
            self._risk = await get_risk_orchestrator()
        self._running = True
        logger.info("ExecutionService started (semi_auto=%s)", self._semi_auto_enabled)

    async def stop(self) -> None:
        self._running = False
        await self._pr.stop()
        await self._fr.stop()
        await self._osm.stop()
        if self._semi_auto_enabled:
            await self._semi_auto.stop()
        await self._mt5.shutdown()
        logger.info("ExecutionService stopped")

    async def execute_signal(self, signal: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
        signal_id = str(signal.get("signal_id") or uuid.uuid4())
        # T-2: concurrent dedup
        async with _get_inflight_lock():
            if signal_id in _INFLIGHT_SIGNALS:
                logger.warning("Duplicate signal %s ignored (in-flight)", signal_id[:8])
                return {"status": "duplicate", "signal_id": signal_id, "message": "Signal already in-flight"}
            _INFLIGHT_SIGNALS.add(signal_id)
        try:
            # FIX-1: idempotency check
            existing_order_id = await _idempotency_check(signal_id)
            if existing_order_id:
                logger.warning("Signal %s already executed -> order_id=%s", signal_id[:8], existing_order_id[:8])
                return {"status": "already_executed", "signal_id": signal_id, "order_id": existing_order_id, "message": "Order was already placed for this signal"}
            return await self._execute_signal_inner(signal, signal_id, user_id)
        finally:
            async with _get_inflight_lock():
                _INFLIGHT_SIGNALS.discard(signal_id)

    async def _execute_signal_inner(self, signal: Dict[str, Any], signal_id: str, user_id: Optional[int]) -> Dict[str, Any]:
        symbol  = signal.get("symbol", "XAUUSD")
        action  = signal.get("action", "")
        entry   = float(signal.get("entry_price", 0.0))
        sl      = float(signal.get("stop_loss", 0.0))
        tp      = float(signal.get("take_profit_1", 0.0))
        raw_lot = float(signal.get("lot_size", 0.01))
        sl_pips = float(signal.get("sl_pips", abs(entry - sl) * 10 if entry and sl else 10.0))

        risk_result = await self._run_risk_check(symbol=symbol, direction=action, sl_pips=sl_pips, signal=signal)
        if not risk_result["approved"]:
            logger.warning("Signal %s BLOCKED by risk: %s", signal_id[:8], risk_result["block_reason"])
            return {"status": "risk_blocked", "signal_id": signal_id, "reason": risk_result["block_reason"], "risk_detail": risk_result}

        volume   = risk_result["lot_size"] or raw_lot
        order_id = str(uuid.uuid4())
        order = ManagedOrder(order_id=order_id, signal_id=signal_id, symbol=symbol, action=action, requested_volume=volume, requested_price=entry, stop_loss=sl, take_profit=tp)
        await self._osm.create_order(order)
        # FIX-1: register BEFORE sending to broker
        await _idempotency_register(signal_id, order_id)

        if self._semi_auto_enabled:
            from .semi_auto import PendingSignal
            pending = PendingSignal(signal_id=signal_id, symbol=symbol, action=action, entry_price=entry, stop_loss=sl, take_profit_1=tp, lot_size=volume)
            await self._semi_auto.submit_for_approval(pending)
            return {"status": "pending_approval", "order_id": order_id, "signal_id": signal_id, "lot_size": volume, "risk_detail": risk_result}

        return await self._submit_order(order)

    async def _run_risk_check(self, symbol: str, direction: str, sl_pips: float, signal: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if self._risk is None:
                self._risk = await get_risk_orchestrator()
            mt5_positions = await self._mt5.get_positions()
            # BUG-3 FIX: ExposurePosition has no 'volume' field.
            # Fields are: symbol, direction, risk_percent, risk_usd (optional).
            open_positions = [
                ExposurePosition(
                    symbol=getattr(p, "symbol", ""),
                    direction="BUY" if getattr(p, "type", 0) == 0 else "SELL",
                    risk_percent=1.0,
                )
                for p in mt5_positions
            ]
            acct    = await self._mt5.get_account_info()
            balance = getattr(acct, "balance", 10_000.0) if acct else 10_000.0
            equity  = getattr(acct, "equity",  balance)  if acct else balance
            inp = RiskInput(
                symbol=symbol, direction=direction, balance=balance, equity=equity,
                stop_loss_pips=max(sl_pips, 1.0),
                current_atr=signal.get("atr", sl_pips),
                atr_history=signal.get("atr_history", []),
                current_spread=signal.get("spread", 2.0),
                avg_spread=signal.get("avg_spread", 2.0),
                open_positions=open_positions,
                today_trades_count=signal.get("today_trades_count", 0),
                today_pnl_usd=signal.get("today_pnl_usd", 0.0),
                week_pnl_usd=signal.get("week_pnl_usd", 0.0),
                month_pnl_usd=signal.get("month_pnl_usd", 0.0),
                # ISSUE-1 FIX: win_rate/avg_rr removed from RiskInput direct fields.
                # RiskInput has no win_rate or avg_rr fields -> was TypeError.
                # Forwarded via extra_ctx so LotSizer receives them through **ctx.
                extra_ctx={"win_rate": signal.get("win_rate", 0.55),
                           "avg_rr":   signal.get("avg_rr",   1.5)},
            )
            decision = await self._risk.assess(inp)
            return decision.to_dict()
        except Exception as exc:
            logger.exception("Risk check failed for %s %s", symbol, direction)
            return {"approved": False, "block_reason": f"Risk engine error: {type(exc).__name__}: {exc}", "lot_size": 0.0}

    async def _submit_order(self, order: ManagedOrder) -> Dict[str, Any]:
        await self._osm.transition(order.order_id, OrderState.SUBMITTED, reason="submitting to MT5")
        mt5_req = MT5OrderRequest(symbol=order.symbol, action=order.action, volume=order.requested_volume, price=order.requested_price or None, sl=order.stop_loss or None, tp=order.take_profit or None)
        result = await self._mt5.send_order(mt5_req)
        if result.success:
            order.mt5_ticket = result.order; order.mt5_deal = result.deal
            order.filled_volume = result.volume; order.filled_price = result.price
            await self._osm.transition(order.order_id, OrderState.FILLED, reason=f"MT5 filled at {result.price}", metadata={"ticket": result.order})
            logger.info("Order %s filled ticket=%s price=%s volume=%s", order.order_id[:8], result.order, result.price, result.volume)
            return {"status": "filled", "order_id": order.order_id, "ticket": result.order, "price": result.price, "volume": result.volume}
        else:
            await self._osm.transition(order.order_id, OrderState.REJECTED, reason=result.error or "MT5 rejected")
            # FIX-1: release so retry can re-check positions
            await _idempotency_release(order.signal_id)
            strategy = await self._fr.handle_failure(order_id=order.order_id, signal_id=order.signal_id, error=result.error or "unknown", retcode=result.retcode, metadata={"order": order.__dict__})
            return {"status": "rejected", "order_id": order.order_id, "error": result.error, "retcode": result.retcode, "recovery": strategy}

    async def _retry_execute(self, failed_order_meta: Dict[str, Any]) -> bool:
        """FIX-1: reconcile + idempotency before retry. FIX-2: called from asyncio.Queue loop."""
        try:
            od = failed_order_meta.get("order", {})
            signal_id = od.get("signal_id", "")
            order_id  = od.get("order_id", "")
            if not signal_id:
                logger.warning("Retry: missing signal_id, skipping")
                return False

            # Step 1: reconcile
            logger.info("Retry %s: reconciling positions first", order_id[:8] if order_id else "?")
            # BUG-1 FIX: was self._pr.run_once() -> AttributeError (only _run_once() existed).
            # run_once() public method added to PositionReconciliation.
            await self._pr.run_once()

            # Step 2: check if position already exists
            mt5_positions = await self._mt5.get_positions()
            mt5_symbols   = {getattr(p, "symbol", "") for p in mt5_positions}
            symbol        = od.get("symbol", "")
            if symbol in mt5_symbols:
                logger.warning("Retry %s: %s already in MT5 - no duplicate", signal_id[:8], symbol)
                await _idempotency_register(signal_id, order_id)
                return True

            # Step 3: re-run risk check
            sl_pips = float(od.get("sl_pips", 10.0))
            risk_result = await self._run_risk_check(symbol=symbol, direction=od.get("action", ""), sl_pips=sl_pips, signal=od)
            if not risk_result["approved"]:
                logger.warning("Retry %s BLOCKED: %s", signal_id[:8], risk_result["block_reason"])
                return False

            # Step 4: submit
            new_order_id = str(uuid.uuid4())
            await _idempotency_register(signal_id, new_order_id)

            # BUG-2 FIX: float(od.get(field, 0.0)) or None crashes when stored value is None.
            # float(None) raises TypeError. Use _safe_float() helper instead.
            def _safe_float(val: Any, default: float = 0.0) -> float:
                """Return float(val) or default if val is None/invalid."""
                if val is None:
                    return default
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return default

            retry_order = ManagedOrder(
                order_id=new_order_id,
                signal_id=signal_id,
                symbol=symbol,
                action=od.get("action", ""),
                requested_volume=_safe_float(od.get("requested_volume"), 0.01),
                requested_price=_safe_float(od.get("requested_price"), 0.0),
                stop_loss=_safe_float(od.get("stop_loss"), 0.0),
                take_profit=_safe_float(od.get("take_profit"), 0.0),
            )
            await self._osm.create_order(retry_order)
            result = await self._submit_order(retry_order)
            success = result.get("status") == "filled"
            logger.info("Retry %s result: %s", new_order_id[:8], result.get("status"))
            return success
        except Exception as exc:
            logger.exception("_retry_execute error: %s", exc)
            return False


execution_service = ExecutionService()
