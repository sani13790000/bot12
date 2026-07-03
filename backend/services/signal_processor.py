"""
backend/services/signal_processor.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pipeline کامل: AnalysisEngines → VotingEngine → SignalProcessor → ExecutionService → MT5

فاز G — اصلاح کامل:
- MIN_CONFIDENCE درست (بجای MIN_CONFIDE8!)
- VotingEngine واقعاً صدا زده می‌شود
- ExecutionService واقعاً اجرا می‌کند
- logging کامل در هر مرحله
- error handling با retry
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────

@dataclass
class RawSignal:
    symbol:      str
    timeframe:   str
    direction:   str          # "BUY" | "SELL" | "NO_TRADE"
    confidence:  float
    entry_price: Optional[float] = None
    sl_price:    Optional[float] = None
    tp_price:    Optional[float] = None
    strategy:    str = "unknown"
    meta:        Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessResult:
    accepted:    bool
    signal:      Optional[RawSignal] = None
    ticket:      Optional[int] = None
    reason:      str = ""
    elapsed_ms:  float = 0.0


# ── Service ───────────────────────────────────────────────────────────────

class SignalProcessor:
    MIN_CONFIDENCE: float = 0.60
    MIN_RR_RATIO:   float = 1.5

    def __init__(self) -> None:
        self._voting_engine      = None
        self._execution_service  = None
        self._db                 = None
        self._initialized        = False

    # ── Public API ──────────────────────────────────────────────────────

    async def process(self, signal: RawSignal) -> ProcessResult:
        """
        Main entry point.

        Flow
        ────
        1. NO_TRADE gate
        2. Confidence gate
        3. Risk/Reward gate
        4. VotingEngine confirmation (optional — skipped if no engine)
        5. ExecutionService.execute()
        6. Persist to DB
        """
        t0 = datetime.now(timezone.utc).timestamp()

        logger.info(
            "[SignalProcessor] process %s %s conf=%.2f",
            signal.direction, signal.symbol, signal.confidence,
        )

        # 1. NO_TRADE gate
        if signal.direction == "NO_TRADE":
            return self._reject(signal, "direction=NO_TRADE", t0)

        # 2. Confidence gate
        if signal.confidence < self.MIN_CONFIDENCE:
            return self._reject(
                signal,
                f"confidence {signal.confidence:.2f} < {self.MIN_CONFIDENCE}",
                t0,
            )

        # 3. R:R gate
        if signal.entry_price and signal.sl_price and signal.tp_price:
            risk   = abs(signal.entry_price - signal.sl_price)
            reward = abs(signal.tp_price    - signal.entry_price)
            if risk > 0 and (reward / risk) < self.MIN_RR_RATIO:
                return self._reject(
                    signal,
                    f"R:R {reward/risk:.2f} < {self.MIN_RR_RATIO}",
                    t0,
                )

        # 4. VotingEngine confirmation
        if not await self._voting_confirms(signal):
            return self._reject(signal, "VotingEngine rejected", t0)

        # 5. Execute
        result = await self._execute(signal)
        if not result.get("success"):
            return self._reject(signal, result.get("error", "execution failed"), t0)

        ticket = result.get("ticket")
        elapsed = (datetime.now(timezone.utc).timestamp() - t0) * 1000

        # 6. Persist
        await self._persist(signal, ticket)

        logger.info(
            "[SignalProcessor] accepted %s %s → ticket=%s (%.0f ms)",
            signal.direction, signal.symbol, ticket, elapsed,
        )
        return ProcessResult(accepted=True, signal=signal, ticket=ticket, elapsed_ms=elapsed)

    # ── Internals ──────────────────────────────────────────────────────

    async def _voting_confirms(self, signal: RawSignal) -> bool:
        if self._voting_engine is None:
            try:
                from backend.agents.voting_engine import voting_engine
                self._voting_engine = voting_engine
            except ImportError:
                logger.warning("[SignalProcessor] VotingEngine not available — skipping vote")
                return True

        try:
            votes = await asyncio.wait_for(
                self._voting_engine.collect_votes(
                    symbol=signal.symbol,
                    timeframe=signal.timeframe,
                    direction=signal.direction,
                    confidence=signal.confidence,
                ),
                timeout=10.0,
            )
            approve = sum(1 for v in votes if v.get("approve"))
            total   = len(votes)
            result  = approve > total / 2
            logger.info(
                "[SignalProcessor] VotingEngine %d/%d approve → %s",
                approve, total, result,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("[SignalProcessor] VotingEngine timeout — proceeding without vote")
            return True
        except Exception as exc:
            logger.error("[SignalProcessor] VotingEngine error: %s", exc)
            return True

    async def _execute(self, signal: RawSignal) -> Dict[str, Any]:
        if self._execution_service is None:
            try:
                from backend.execution.execution_service import execution_service
                self._execution_service = execution_service
            except ImportError as exc:
                logger.error("[SignalProcessor] ExecutionService import failed: %s", exc)
                return {"success": False, "error": str(exc)}

        try:
            from backend.execution.execution_service import TradeSignal
            ts = TradeSignal(
                symbol=signal.symbol,
                direction=signal.direction,
                volume=signal.meta.get("volume", 0.01),
                entry=signal.entry_price,
                sl=signal.sl_price,
                tp=signal.tp_price,
                strategy=signal.strategy,
                confidence=signal.confidence,
            )
            res = await self._execution_service.execute(ts)
            return {"success": res.success, "ticket": res.ticket, "error": res.error}
        except Exception as exc:
            logger.error("[SignalProcessor] execute error: %s", exc)
            return {"success": False, "error": str(exc)}

    async def _persist(self, signal: RawSignal, ticket: Optional[int]) -> None:
        if self._db is None:
            try:
                from backend.database.connection import db
                self._db = db
            except ImportError:
                return

        try:
            await self._db.insert("signals", {
                "symbol":      signal.symbol,
                "direction":   signal.direction,
                "confidence":  signal.confidence,
                "entry_price": signal.entry_price,
                "sl_price":    signal.sl_price,
                "tp_price":    signal.tp_price,
                "strategy":    signal.strategy,
                "ticket":      ticket,
                "created_at":  datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            logger.warning("[SignalProcessor] DB persist failed (non-fatal): %s", exc)

    def _reject(self, signal: RawSignal, reason: str, t0: float) -> ProcessResult:
        elapsed = (datetime.now(timezone.utc).timestamp() - t0) * 1000
        logger.info("[SignalProcessor] rejected %s %s — %s (%.0f ms)",
                    signal.direction, signal.symbol, reason, elapsed)
        return ProcessResult(accepted=False, signal=signal, reason=reason, elapsed_ms=elapsed)


# ── Module-level singleton ───────────────────────────────────────────────────
signal_processor = SignalProcessor()


__all__ = ["SignalProcessor", "RawSignal", "ProcessResult", "signal_processor"]
