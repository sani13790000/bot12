"""backend/risk/kill_switch.py
PHASE-4: Emergency Kill Switch — hard stop for live trading.

Triggers:
  K-1: equity < absolute_floor_usd
  K-2: total drawdown from HWM >= hard_drawdown_pct
  K-3: equity drops flash_crash_pct% within flash_window_seconds
  K-4: manual activation via activate()

On activation:
  - Sets _active flag (fail-closed)
  - Calls all registered async callbacks (e.g. close-all positions)
  - Logs CRITICAL

Reset: explicit reset() with admin token only.

Fixes applied:
  CB-NEW-1: is_active is @property — callers must NOT add ()
  CB-NEW-2: kill_switch singleton exported at module level
  CB-NEW-3: check() requires equity + balance args (documented clearly)
"""
from __future__ import annotations
import asyncio, time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional

try:
    from ..core.logger import get_logger
    logger = get_logger('risk.kill_switch')
except ImportError:
    import logging
    logger = logging.getLogger('risk.kill_switch')


@dataclass
class KillSwitchConfig:
    absolute_floor_usd:   float = 0.0
    hard_drawdown_pct:    float = 20.0
    flash_crash_pct:      float = 10.0
    flash_window_seconds: float = 60.0
    enabled:              bool  = True


@dataclass
class KillSwitchState:
    active:             bool                     = False
    reason:             str                      = ''
    activated_at:       Optional[datetime]       = None
    activation_equity:  float                    = 0.0
    high_water_mark:    float                    = 0.0
    total_activations:  int                      = 0


OnKillCallback = Callable[[str, float], Awaitable[None]]


class KillSwitch:
    """
    Emergency stop mechanism.

    Usage::
        ks = get_kill_switch()
        await ks.check(equity=9500.0, balance=10000.0)  # raises if triggered
        ks.register_callback(close_all_positions)

    IMPORTANT — is_active is a @property (not a method):
        correct:   if ks.is_active:
        WRONG:     if ks.is_active():   ← TypeError: bool is not callable
    """

    def __init__(self, config: Optional[KillSwitchConfig] = None) -> None:
        self.config = config or KillSwitchConfig()
        self.state  = KillSwitchState()
        self._lock  = asyncio.Lock()
        self._callbacks: List[OnKillCallback] = []
        self._equity_history: List[tuple] = []

    def register_callback(self, cb: OnKillCallback) -> None:
        if cb not in self._callbacks:
            self._callbacks.append(cb)
            logger.debug('kill_switch callback registered', cb=cb.__name__)

    def remove_callback(self, cb: OnKillCallback) -> None:
        self._callbacks = [c for c in self._callbacks if c is not cb]

    async def check(self, equity: float, balance: float) -> None:
        """
        Call before every order. Raises KillSwitchActivatedError if triggered.

        Args:
            equity:  Current account equity in USD.
            balance: Current account balance in USD.
        """
        from ..core.exceptions import KillSwitchActivatedError

        if not self.config.enabled:
            return

        async with self._lock:
            if self.state.active:
                raise KillSwitchActivatedError(
                    reason=self.state.reason, equity=equity,
                    threshold_pct=self.config.hard_drawdown_pct)

            if equity > self.state.high_water_mark:
                self.state.high_water_mark = equity

            # K-1: Absolute equity floor
            if self.config.absolute_floor_usd > 0 and equity < self.config.absolute_floor_usd:
                await self._activate(
                    reason=f'equity {equity:.2f} below floor {self.config.absolute_floor_usd:.2f}',
                    equity=equity)
                raise KillSwitchActivatedError(
                    reason=self.state.reason, equity=equity, threshold_pct=0.0)

            # K-2: Hard drawdown from HWM
            if self.state.high_water_mark > 0:
                dd_pct = (self.state.high_water_mark - equity) / self.state.high_water_mark * 100
                if dd_pct >= self.config.hard_drawdown_pct:
                    await self._activate(
                        reason=(f'drawdown {dd_pct:.2f}% >= '
                                f'hard limit {self.config.hard_drawdown_pct:.2f}%'),
                        equity=equity)
                    raise KillSwitchActivatedError(
                        reason=self.state.reason, equity=equity,
                        threshold_pct=self.config.hard_drawdown_pct)

            # K-3: Flash crash detection
            now = time.monotonic()
            self._equity_history.append((now, equity))
            cutoff = now - self.config.flash_window_seconds
            self._equity_history = [(t, e) for t, e in self._equity_history if t >= cutoff]
            if len(self._equity_history) >= 2:
                oldest_eq = self._equity_history[0][1]
                if oldest_eq > 0:
                    flash_drop = (oldest_eq - equity) / oldest_eq * 100
                    if flash_drop >= self.config.flash_crash_pct:
                        await self._activate(
                            reason=(f'flash crash detected: {flash_drop:.2f}% drop '
                                    f'in {self.config.flash_window_seconds:.0f}s'),
                            equity=equity)
                        raise KillSwitchActivatedError(
                            reason=self.state.reason, equity=equity,
                            threshold_pct=self.config.flash_crash_pct)

    async def activate(self, reason: str = 'manual', equity: float = 0.0) -> None:
        """K-4: Manual activation."""
        async with self._lock:
            await self._activate(reason=f'manual: {reason}', equity=equity)

    async def reset(self, admin_token: str, expected_token: str) -> bool:
        if admin_token != expected_token or not admin_token:
            logger.warning('kill_switch reset REJECTED: bad token')
            return False
        async with self._lock:
            self.state.active = False
            self.state.reason = ''
            self.state.activated_at = None
            logger.info('kill_switch RESET by admin',
                        total_activations=self.state.total_activations)
        return True

    # CB-NEW-1 FIX: is_active is a @property — do NOT call with ()
    # Correct:   if ks.is_active:
    # Wrong:     if ks.is_active():   ← TypeError
    @property
    def is_active(self) -> bool:
        return self.state.active

    def get_status(self) -> dict:
        return {
            'active': self.state.active,
            'reason': self.state.reason,
            'activated_at': (self.state.activated_at.isoformat()
                             if self.state.activated_at else None),
            'activation_equity': self.state.activation_equity,
            'high_water_mark': self.state.high_water_mark,
            'total_activations': self.state.total_activations,
            'config': {
                'absolute_floor_usd': self.config.absolute_floor_usd,
                'hard_drawdown_pct':  self.config.hard_drawdown_pct,
                'flash_crash_pct':    self.config.flash_crash_pct,
                'flash_window_s':     self.config.flash_window_seconds,
            },
        }

    async def _activate(self, reason: str, equity: float) -> None:
        if self.state.active:
            return
        self.state.active = True
        self.state.reason = reason
        self.state.activated_at = datetime.now(timezone.utc)
        self.state.activation_equity = equity
        self.state.total_activations += 1
        logger.critical('\U0001f6a8 KILL SWITCH ACTIVATED', reason=reason, equity=equity,
                        hwm=self.state.high_water_mark,
                        activations=self.state.total_activations)
        for cb in list(self._callbacks):
            try:
                await asyncio.wait_for(cb(reason, equity), timeout=10.0)
            except asyncio.TimeoutError:
                logger.error('kill_switch callback timeout', cb=cb.__name__)
            except Exception as exc:
                logger.error('kill_switch callback error', cb=cb.__name__, error=str(exc))


# ── Singleton management ─────────────────────────────────────────────── #

_kill_switch: Optional[KillSwitch] = None


def get_kill_switch(config: Optional[KillSwitchConfig] = None) -> KillSwitch:
    """Return the global KillSwitch singleton."""
    global _kill_switch
    if _kill_switch is None:
        _kill_switch = KillSwitch(config=config)
    return _kill_switch


# CB-NEW-2 FIX: Export module-level singleton so
#   `from backend.risk.kill_switch import kill_switch` works.
# Previously only `get_kill_switch()` was defined — no `kill_switch` name.
kill_switch: KillSwitch = get_kill_switch()
