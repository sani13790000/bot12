"""backend/execution/execution_service.py
Enterprise Execution Service.
SOLID: S=orchestrates only, O=via interfaces, L=any IOrderBroker, I=minimal interfaces, D=constructor injection.
Preserves: FIX 1 idempotency, FIX-2 queue, CRITICAL-1 lazy lock, CRITICAL-2 set_mt5.
Fixes:
  - LOG-FIX-6: asyncio.wait_for timeout guard on broker.initialize()
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

_IDEMPLOTENCY_STORE:      Dict[str, str]   = {}
_IDEMPLOTENCY_TIMESTAMPS: Dict[str, float] = {}
_INFLIGHT_SIGNALS:       Set[str]          = set()
_IDEMPLOTENCY_TTL: float = 600.0

__all__ = ['ExecutionService', 'get_execution_service']


def _generate_order_id() -> str:
    return str(uuid.uuid4())


class ExecutionService:
    """Orchestrates signal → broker execution pipeline."""

    def __init__(self, risk: Any, broker: Any, osm: Any, fr: Any, pr: Any, *, default_risk_pct: float = 1.0) -> None:
        self._risk = risk; self._broker = broker; self._osm = osm; self._fr = fr; self._pr = pr
        self._default_risk_pct = default_risk_pct; self._running = False

    async def start(self) -> None:
        if self._running: return
        logger.info('ExecutionService starting')
        try:
            await asyncio.wait_for(  # LOG-FIX-6: timeout guard -- broker init must not hang forever
                self._broker.initialize(),
                timeout=getattr(settings, 'BROKER_INIT_TIMEOUT_S', 30.0)
            )
        except asyncio.TimeoutError as exc:
            raise BrokerConnectionError(
                f"Broker initialization timed out after {getattr(settings, 'BROKER_INIT_TIMEOUT_S', 30)}s"
            ) from exc
        await self._osm.start()
        self._fr.set_retry_callback(self._retry_execute)
        await self._fr.start()
        if hasattr(self._pr, 'set_mt5'): self._pr.set_mt5(self._broker)  # CRITICAL-2
        await self._pr.start()
        self._running = True
        logger.info('ExecutionService started')

    async def stop(self) -> None:
        if not self._running: return
        logger.info('ExecutionService stopping')
        await self._osm.stop()
        await self._fr.stop()
        await self._pr.stop()
        self._running = False
        logger.info('ExecutionService stopped')

    def _get_idempotency_lock(self) -> asyncio.Lock:
        if not hasattr(self, '_idempotency_lock'):
            self._idempotency_lock = asyncio.Lock()
        return self._idempotency_lock

    def _get_queue_lock(self) -> asyncio.Lock:
        if not hasattr(self, '_queue_lock'):
            self._queue_lock = asyncio.Lock()
        return self._queue_lock

    async def execute_signal(self, signal: Dict) -> Dict:
        """Full pipeline: idempotency ₒ risk ₒ lot calc ₒ broker submit."""
        signal_id = signal.get('signal_id') or signal.get('id') or str(uuid.uuid4())
        t0 = time.monotonic()
        async with self._get_idempotency_lock():
            self._evict_old_idempotency()
            if signal_id in _IDEMPLOTENCY_STORE:
                existing = _IDEMPLOTENCY_STORE[signal_id]
                logger.info('Duplicate signal %s -> %s', signal_id[:8], existing[:8])
                return {'status': 'duplicate', 'order_id': existing, 'signal_id': signal_id}
            if signal_id in _INFLIGHT_SIGNALS:
                logger.warning('Signal %s in flight', signal_id[:8])
                return {'status': 'in_flight', 'signal_id': signal_id}
            _INFLIGHT_SIGNALS.add(signal_id)
        try:
            risk_result = await self._risk.assess(signal)
            if not risk_result.allowed:
                logger.info('Risk block %s: %s', signal_id[:8], risk_result.reason)
                metrics_registry.trade_rejected(signal.get('symbol',''), 'risk')
                return {'status': 'risk_blocked', 'reason': risk_result.reason, 'signal_id': signal_id}
            order_id = _generate_order_id()
            async with self._get_idempotency_lock():
                _IDEMPLOTENCY_STORE[signal_id] = order_id
                _IDEMPLOTENCY_TIMESTAMPS[signal_id] = time.monotonic()
            await self._submit_order(signal, order_id, risk_result)
            latency = time.monotonic() - t0
            metrics_registry.trade_filled(signal.get('symbol',''), signal.get('direction',''), latency)
            logger.info('Order %s submitted in %.3fs', order_id[:8], latency)
            return {'status': 'submitted', 'order_id': order_id, 'signal_id': signal_id, 'latency_s': round(latency, 3)}
        except Exception as exc:
            logger.error('execute_signal failed %s: %s', signal_id[:8], exc, exc_info=True)
            metrics_registry.trade_rejected(signal.get('symbol',''), 'exception')
            raise
        finally:
            _INFLIGHT_SIGNALS.discard(signal_id)

    async def _submit_order(self, signal: Dict, order_id: str, risk_result: Any) -> None:
        result = await with_retry_async(
            lambda: self._broker.send_order(signal, order_id),
            config=MT5_RETRY,
            on_retry=lambda a, e, s: metrics_registry.order_retry(signal.get('symbol',''))
        )
        if not result:
            raise OrderSubmissionError(signal.get('symbol',''), order_id, retcode=0, reason='broker returned false')

    async def _retry_execute(self, metadata: Dict) -> bool:
        try:
            await self._broker.send_order(metadata, metadata.get('order_id',''))
            return True
        except Exception as exc:
            logger.error('_retry_execute failed: %s', exc, exc_info=True)
            return False

    def _evict_old_idempotency(self) -> None:
        now = time.monotonic()
        expired = [k for k, t in _IDEMPLOTENCY_TIMESTAMPS.items() if now - t > _IDEMPLOTENCY_TTL]
        for k in expired:
            _IDEMPLOTENCY_STORE.pop(k, None)
            _IDEMPLOTENCY_TIMESTAMPS.pop(k, None)


__execution_service_instance: Optional[ExecutionService] = None
__execution_service_lock: Optional[asyncio.Lock] = None


def _get_es_lock() -> asyncio.Lock:
    global __execution_service_lock
    if __execution_service_lock is None:
        __execution_service_lock = asyncio.Lock()
    return __execution_service_lock


async def get_execution_service(**aliases) -> ExecutionService:
    global __execution_service_instance
    if __execution_service_instance is not None:
        return __execution_service_instance
    async with _get_es_lock():
        if __execution_service_instance is not None:
            return __execution_service_instance
        from .mt5_connector import MT5Connector
        from .order_state_machine import OrderStateMachine
        from .failure_recovery import FailureRecoveryEngine
        from .position_reconciliation import PositionReconciliation
        from ..risk.risk_orchestrator import get_risk_orchestrator
        risk = await get_risk_orchestrator()
        broker = MT5Connector()
        osm = OrderStateMachine()
        fr = FailureRecoveryEngine()
        pr = PositionReconciliation()
        svc = ExecutionService(risk=risk, broker=broker, osm=osm, fr=fr, pr=pr)
        await svc.start()
        __execution_service_instance = svc
        return svc
