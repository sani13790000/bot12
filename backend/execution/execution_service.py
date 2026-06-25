"""backend/execution/execution_service.py
Enterprise Execution Service.
SOLID: S=orchestrates only, O=via interfaces, L=any IOrderBroker, I=minimal interfaces, D=constructor injection.
Preserves: FIX-1 idempotency, FIX-2 queue, CRITICAL-1 lazy lock, CRITICAL-2 set_mt5.
"""
from __future__ import annotations
import asyncio, time, uuid
from typing import Any, Dict, Optional, Set
from ..core.config import settings
from ..core.exceptions import BrokerConnectionError, OrderSubmissionError
from ..core.logger import get_logger
from ..core.retry import MT5_RETRY, with_retry_async
from ..observability.metrics import metrics_registry

logger = get_logger('execution.service')

_IDEMPOTENCY_STORE:      Dict[str, str]   = {}
_IDEMPOTENCY_TIMESTAMPS: Dict[str, float] = {}
_INFLIGHT_SIGNALS:       Set[str]         = set()
_IDEMPOTENCY_TTL: float = 600.0
_IDEMPOTENCY_LOCK: Optional[asyncio.Lock] = None
_INFLIGHT_LOCK:    Optional[asyncio.Lock] = None

def _get_idempotency_lock() -> asyncio.Lock:
    global _IDEMPOTENCY_LOCK
    if _IDEMPOTENCY_LOCK is None: _IDEMPOTENCY_LOCK = asyncio.Lock()
    return _IDEMPOTENCY_LOCK

def _get_inflight_lock() -> asyncio.Lock:
    global _INFLIGHT_LOCK
    if _INFLIGHT_LOCK is None: _INFLIGHT_LOCK = asyncio.Lock()
    return _INFLIGHT_LOCK

def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None: return default
    try: return float(val)
    except (TypeError, ValueError): return default

async def _idempotency_check(signal_id: str) -> Optional[str]:
    now = time.monotonic()
    async with _get_idempotency_lock():
        stale = [k for k, ts in _IDEMPOTENCY_TIMESTAMPS.items() if now - ts > _IDEMPOTENCY_TTL]
        for k in stale: _IDEMPOTENCY_STORE.pop(k, None); _IDEMPOTENCY_TIMESTAMPS.pop(k, None)
        return _IDEMPOTENCY_STORE.get(signal_id)

async def _idempotency_register(signal_id: str, order_id: str) -> None:
    async with _get_idempotency_lock():
        _IDEMPOTENCY_STORE[signal_id] = order_id; _IDEMPOTENCY_TIMESTAMPS[signal_id] = time.monotonic()

async def _idempotency_release(signal_id: str) -> None:
    async with _get_idempotency_lock():
        _IDEMPOTENCY_STORE.pop(signal_id, None); _IDEMPOTENCY_TIMESTAMPS.pop(signal_id, None)

class ExecutionService:
    def __init__(self, risk: Any, broker: Any, osm: Any, fr: Any, pr: Any, *, default_risk_pct: float = 1.0) -> None:
        self._risk = risk; self._broker = broker; self._osm = osm; self._fr = fr; self._pr = pr
        self._default_risk_pct = default_risk_pct; self._running = False

    async def start(self) -> None:
        if self._running: return
        logger.info('ExecutionService starting')
        await self._broker.initialize()
        await self._osm.start()
        self._fr.set_retry_callback(self._retry_execute)
        await self._fr.start()
        if hasattr(self._pr, 'set_mt5'): self._pr.set_mt5(self._broker)  # CRITICAL-2
        await self._pr.start()
        self._running = True
        logger.info('ExecutionService started')

    async def stop(self) -> None:
        if not self._running: return
        for fn in (self._fr.stop, self._pr.stop, self._broker.shutdown):
            try: await fn()
            except Exception as exc: logger.error('stop error', error=str(exc))
        self._running = False
        logger.info('ExecutionService stopped')

    async def execute_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        signal_id = signal.get('signal_id') or signal.get('id') or str(uuid.uuid4())
        log = logger.bind(signal_id=signal_id, symbol=signal.get('symbol', '?'))
        async with _get_inflight_lock():
            if signal_id in _INFLIGHT_SIGNALS:
                log.warning('Signal already inflight'); return {'success': False, 'order_id': None, 'message': 'signal_inflight'}
            _INFLIGHT_SIGNALS.add(signal_id)
        try: return await self._pipeline(signal, signal_id, log)
        finally:
            async with _get_inflight_lock(): _INFLIGHT_SIGNALS.discard(signal_id)

    async def _pipeline(self, signal: Dict[str, Any], signal_id: str, log: Any) -> Dict[str, Any]:
        existing = await _idempotency_check(signal_id)
        if existing: log.info('Already executed', existing=existing); return {'success': True, 'order_id': existing, 'message': 'already_executed'}
        t0 = time.monotonic(); risk_result = await self._run_risk(signal, log)
        metrics_registry.risk_latency('orchestrator', time.monotonic()-t0)
        if not risk_result.get('approved', False):
            reason = risk_result.get('block_reason', 'unknown')
            metrics_registry.trade_rejected(signal.get('symbol', '?'), reason)
            log.warning('Risk blocked', reason=reason)
            return {'success': False, 'order_id': None, 'message': f'risk_blocked:{reason}', 'risk_result': risk_result}
        order = await self._create_order(signal, risk_result, signal_id)
        order_id = getattr(order, 'order_id', str(uuid.uuid4()))
        await _idempotency_register(signal_id, order_id)
        metrics_registry.trade_submitted(signal.get('symbol','?'), signal.get('direction','?'))
        t1 = time.monotonic()
        try: await self._submit(order)
        except (OrderSubmissionError, BrokerConnectionError) as exc:
            log.error('Submission failed', error=str(exc))
            await self._fr.handle_failure(order, str(exc))
            return {'success': False, 'order_id': order_id, 'message': f'submission_failed:{exc}'}
        metrics_registry.trade_filled(signal.get('symbol','?'), signal.get('direction','?'), time.monotonic()-t1)
        metrics_registry.set_lot_size(signal.get('symbol','?'), risk_result.get('lot_size', 0.0))
        log.info('Order filled', order_id=order_id, fill_ms=round((time.monotonic()-t1)*1000,1))
        return {'success': True, 'order_id': order_id, 'message': 'filled', 'risk_result': risk_result}

    async def _run_risk(self, signal: Dict[str, Any], log: Any) -> Dict[str, Any]:
        try:
            from ..risk.risk_orchestrator import RiskInput
            inp = RiskInput(
                symbol=signal.get('symbol',''), direction=signal.get('direction','BUY'),
                balance=_safe_float(signal.get('balance'),10000.), stop_loss_pips=_safe_float(signal.get('stop_loss_pips'),20.),
                entry_price=_safe_float(signal.get('entry_price')), stop_loss=_safe_float(signal.get('stop_loss')),
                equity=_safe_float(signal.get('equity'),10000.), current_atr=_safe_float(signal.get('current_atr'),10.),
                atr_history=signal.get('atr_history',[]), current_spread=_safe_float(signal.get('current_spread')),
                avg_spread=_safe_float(signal.get('avg_spread')), open_positions=signal.get('open_positions',[]),
                today_trades_count=int(signal.get('today_trades_count',0)), today_pnl_usd=_safe_float(signal.get('today_pnl_usd')),
                week_pnl_usd=_safe_float(signal.get('week_pnl_usd')), month_pnl_usd=_safe_float(signal.get('month_pnl_usd')),
                user_id=signal.get('user_id',''), signal_id=signal.get('signal_id',''),
                override_risk_pct=signal.get('override_risk_pct'),
                extra_ctx={'win_rate': _safe_float(signal.get('win_rate'),0.55), 'avg_rr': _safe_float(signal.get('avg_rr'),1.5)},
            )
            result = await self._risk.assess(inp)
            return result.to_dict() if hasattr(result, 'to_dict') else {'approved': True, 'lot_size': 0.01}
        except Exception as exc:
            log.error('Risk error', error=str(exc))
            return {'approved': False, 'block_reason': f'risk_error:{exc}', 'lot_size': 0.0}

    async def _create_order(self, signal: Dict[str, Any], risk_result: Dict[str, Any], signal_id: str) -> Any:
        return await self._osm.create_order(
            signal_id=signal_id, symbol=signal.get('symbol',''), direction=signal.get('direction','BUY'),
            lot_size=_safe_float(risk_result.get('lot_size'),0.01), entry_price=_safe_float(signal.get('entry_price')),
            stop_loss=_safe_float(signal.get('stop_loss')), take_profit=_safe_float(signal.get('take_profit')),
            requested_price=_safe_float(signal.get('entry_price')),
        )

    async def _submit(self, order: Any) -> Any:
        from .mt5_connector import MT5OrderRequest
        request = MT5OrderRequest(symbol=order.symbol, order_type=order.direction, volume=order.lot_size,
            price=order.entry_price or 0., sl=order.stop_loss or 0., tp=order.take_profit or 0.,
            comment=f'GVA:{order.order_id[:8]}')
        return await with_retry_async(
            coro_factory=lambda: self._broker.send_order(request), config=MT5_RETRY,
            operation_name=f'send_order.{order.symbol}',
            on_retry=lambda a,e,s: metrics_registry.order_retry(order.symbol)
        )

    async def _retry_execute(self, metadata: Dict[str, Any]) -> bool:
        log = logger.bind(retry=True, signal_id=metadata.get('signal_id','?'))
        try:
            await self._pr.run_once()
            od = metadata.get('order', {})
            from .order_state_machine import ManagedOrder
            retry_order = ManagedOrder(
                order_id=str(uuid.uuid4()), signal_id=metadata.get('signal_id',''),
                symbol=od.get('symbol',''), direction=od.get('direction','BUY'),
                lot_size=_safe_float(od.get('lot_size'),0.01), entry_price=_safe_float(od.get('entry_price')),
                stop_loss=_safe_float(od.get('stop_loss')), take_profit=_safe_float(od.get('take_profit')),
                requested_price=_safe_float(od.get('requested_price'),0.),
            )
            await self._submit(retry_order)
            log.info('Retry succeeded', order_id=retry_order.order_id); return True
        except Exception as exc:
            log.error('Retry failed', error=str(exc))
            metrics_registry.dead_letter(metadata.get('symbol','?')); return False

    async def health(self) -> Dict[str, Any]:
        broker_ok = False
        try: broker_ok = await asyncio.wait_for(self._broker.health_check(), timeout=3.)
        except Exception: pass
        return {'running': self._running, 'broker': broker_ok, 'counters': metrics_registry.snapshot().get('counters', {})}

_execution_service_instance: Optional[ExecutionService] = None

def get_execution_service() -> ExecutionService:
    global _execution_service_instance
    if _execution_service_instance is not None: return _execution_service_instance
    from ..execution.mt5_connector           import mt5_connector
    from ..execution.order_state_machine      import order_state_machine
    from ..execution.failure_recovery         import failure_recovery
    from ..execution.position_reconciliation  import position_reconciliation
    from ..risk.risk_orchestrator             import get_risk_orchestrator as _get_risk
    class _LazyRisk:
        async def assess(self, inp: Any) -> Any: return await (await _get_risk()).assess(inp)
        async def check(self, **kw: Any) -> Any:  return await (await _get_risk()).check(**kw)
    _execution_service_instance = ExecutionService(
        risk=_LazyRisk(), broker=mt5_connector, osm=order_state_machine,
        fr=failure_recovery, pr=position_reconciliation,
        default_risk_pct=getattr(settings, 'DEFAULT_RISK_PCT', 1.0),
    )
    return _execution_service_instance

execution_service = get_execution_service()
