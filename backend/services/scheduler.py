"""
backend/services/scheduler.py
Galaxy Vast AI — Background Task Scheduler

وظیفه: اجرای وظایف پس‌زمینه با interval قابل تنظیم.

اصلاح اعمال‌شده:
  FIX-1 L90: f"sched:{"name"}" → "sched:" + name
             (f-string تو در تو در Python 3.11 مجاز نیست)
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────────────

class TaskStatus(Enum):
    IDLE    = auto()
    RUNNING = auto()
    DEAD    = auto()


@dataclass
class TaskInfo:
    """اطلاعات یک وظیفه ثبت‌شده."""

    name:        str
    fn:          Callable
    interval_s:  float
    status:      TaskStatus = TaskStatus.IDLE
    last_run:    float      = field(default_factory=time.monotonic)
    error_count: int        = 0
    task:        Any        = field(default=None, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler
# ─────────────────────────────────────────────────────────────────────────────

class BackgroundScheduler:
    """
    Async background scheduler با graceful shutdown.

    استفاده:
        scheduler.register("heartbeat", heartbeat_fn, interval_s=30)
        await scheduler.start_all()
        await scheduler.shutdown()
    """

    _MAX_REGISTRY = 64

    def __init__(self) -> None:
        self._registry: Dict[str, TaskInfo] = {}
        self._shutdown: Optional[asyncio.Event] = None

    def _ensure_primitives(self) -> None:
        if self._shutdown is None:
            self._shutdown = asyncio.Event()

    def register(self, name: str, fn: Callable, interval_s: float) -> None:
        if name in self._registry:
            logger.warning("[Scheduler] '%s' already registered", name); return
        if len(self._registry) >= self._MAX_REGISTRY:
            logger.error("[Scheduler] registry full (%d)", self._MAX_REGISTRY); return
        self._registry[name] = TaskInfo(name=name, fn=fn, interval_s=interval_s)
        logger.info("[Scheduler] registered '%s' interval=%.0fs", name, interval_s)

    async def _run_task(self, name: str) -> None:
        info = self._registry.get(name)
        if not info:
            return
        info.status = TaskStatus.RUNNING
        while True:
            sleep_s = max(info.interval_s - (time.monotonic() - info.last_run), 0)
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=sleep_s)
                break
            except asyncio.TimeoutError:
                pass
            try:
                await info.fn()
                info.last_run = time.monotonic()
            except Exception as e:
                info.error_count += 1
                logger.error("[Scheduler] '%s' error #%d: %s", name, info.error_count, e)
        info.status = TaskStatus.DEAD
        logger.info("[Scheduler] '%s' stopped", name)

    async def shutdown(self, timeout_s: float = 10.0) -> None:
        self._ensure_primitives()
        self._shutdown.set()
        tasks = [info.task for info in self._registry.values() if info.task]
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=timeout_s
            )

    async def start_all(self) -> None:
        self._ensure_primitives()
        for name, info in self._registry.items():
            task = asyncio.create_task(
                self._run_task(name),
                name="sched:" + name,   # FIX-1: بود f"sched:{"name"}"
            )
            task.add_done_callback(
                lambda t: logger.warning("[Scheduler] DEAD task: '%s'", t.get_name())
                if not t.cancelled() and t.exception() else None
            )
            info.task = task


scheduler = BackgroundScheduler()
