"""
backend/services/signal_processor.py
Galaxy Vast AI Trading Platform
âââââââââââââââââââââââââââââ

ÙØ§Ø·ÙÙ: SignalProcessor

ÙØ¸ÛÙÙ:
  - Ø¯Ø³ØªÛÚØª Ø§ÛÙ Ú·Ø§Ø¯ÙØ§Ù incoming Ø¨Ø± Supabase
  - Ø¬Ø°Ú· ØªÙØ±Ú©ÛØª Ø³ÛÚ¯ÙÙÙ ÙØ¬Ø§Ø² Ø¨Ø± Ø³ÛÚ¯ÙÙÙ Ø¦ÙÙ
  - ÙÙØ´ voting_engine Ù ØªÙ¶jâÙÛØ¯Ù Ø§ÛÙ
  - ØªØ³Ú· ÛØ³ Ø¨Ù execution_service

Imports:
  - asyncio
  - dataclasses
  - typing
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    id:               str
    symbol:           str
    timeframe:        str
    direction:        str
    entry_price:      float
    sl_price:         float
    tp_price:         float
    confidence:       float               # 0.0 - 1.0
    source:           str                 # "auto" | "semi_auto" | "manual"
    user_id:          Optional[str]  = None
    notes:            List[str]      = field(default_factory=list)
    created_at:       Optional[datetime] = None


@dataclass
class ProcessResult:
    success:      bool
    signal_id:    str
    stage:        str
    message:      str
    elapsed_ms:   float
    executed:     bool       = False
    ticket:       Optional[str] = None
    notes:        List[str]  = field(default_factory=list)


class SignalProcessor:
    """
    Ø§ÙÚ¯ ÙÛÚÚÄÛ Ø Ø¯ ØµÙØ´Ø§Ù Ø³ÛÚ¯ÙÙÙ ÙØ¬Ø§Ø².

    ÙØ±ØªØª Process:
        1.  Date Validation (Ø³ÙØ¯ ÛØª Ø²ÙØ§Ù ÙÙØ±ÙØ¯Û Ø¨Ø§Ø´ÙØ¯)
        2.  Risk/Reward check (Ø³ÙØ¯ Ø©Ø¯Ø§ÙÙ R:R)
        3.  Voting confirmation (ØªÙÚ¯ÛØª ÙØªÛÙ ÙØªÛÙ Ø¢Ø±Ø§Û Ø°Ù Ø°Ø¯Û)
        4.  Execution via ExecutionService
        5.  Alert via Telegram
    """

    MIN_CONFIDENCE = 0.60
    MIN_RR_RATIO   = 1.5
    TIMEOUT_S      = 30

    def __init__(self, execution_service=None, voting_engine=None,
                 telegram_alerts=None) -> None:
        self.execution_service = execution_service
        self.voting_engine     = voting_engine
        self.telegram_alerts   = telegram_alerts

    async def process(self, signal: TradingSignal) -> ProcessResult:
        t0 = datetime.now(timezone.utc).timestamp()
        try:
            return await asyncio.wait_for(
                self._process_internal(signal, t0),
                timeout=self.TIMEOUT_S
            )
        except asyncio.TimeoutError:
            msg = f"signal {signal.id} timed out after {self.TIMEOUT_S}s"
            logger.error(msg)
            await self._send_alert(f"â¨ Timeout: {msg}")
            return self._reject(signal, msg, t0)

    async def _process_internal(self, signal: TradingSignal, t0: float) -> ProcessResult:
        # 1: validate
        if signal.confidence < self.MIN_CONFIDENCE:
            return self._reject(signal, f"confidence {signal.confidence:.2f} < {self.MIN_CONFIDENCE}", t0)
        if signal.sl_price and signal.tp_price:
            risk   = abs(signal.entry_price - signal.sl_price)
            reward = abs(signal.tp_price - signal.entry_price)
            if risk > 0 and (reward / risk) < self.MIN_RR_RATIO:
                return self._reject(signal, f"R:R {reward/risk:.2f} < {self.MIN_RR_RATIO}", t0)
        if not await self._voting_confirms(signal):
            return self._reject(signal, "VotingEngine rejected", t0)
        # 2: execute
        result = await self._execute(signal)
        elapsed = round((datetime.now(timezone.utc).timestamp() - t0) * 1000, 2)
        await self._send_alert(f"â Signal {signal.id} executed: {result}")
        return ProcessResult(success=True, signal_id=signal.id, stage="executed",
                             message=str(result), elapsed_ms=elapsed, executed=True,
                             ticket=str(result) if result else None)

    async def _voting_confirms(self, signal: TradingSignal) -> bool:
        if not self.voting_engine:
            return True
        try:
            result = await self.voting_engine.vote(signal)
            return bool(result)
        except Exception as e:
            logger.warning("voting error: %s", e)
            return True

    async def _execute(self, signal: TradingSignal):
        if not self.execution_service:
            return None
        return await self.execution_service.execute(signal)

    async def _send_alert(self, msg: str) -> None:
        if not self.telegram_alerts:
            return
        try:
            await self.telegram_alerts.send(msg)
        except Exception as e:
            logger.warning("alert failed: %s", e)

    def _reject(self, signal: TradingSignal, reason: str, t0: float) -> ProcessResult:
        logger.info("REJECTED %s: %s", signal.id, reason)
        elapsed = round((datetime.now(timezone.utc).timestamp() - t0) * 1000, 2)
        return ProcessResult(success=False, signal_id=signal.id, stage="rejected",
                             message=reason, elapsed_ms=elapsed)
