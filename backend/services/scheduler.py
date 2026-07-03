"""Background Scheduler - Phase Q-28..Q-33 fixes
FIX: Converted all logger.xxx("msg %s", arg) to logger.xxx(f"msg {arg}")
FIX: Nested f-string in create_task name= fixed
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING  = "PENDING"
    RUNNING  = "RUNNING"
    DONE     = "DONE"
    FAILED   = "FAILED"
    DISABLED = "DISABLED"


@dataclass
class TaskInfo:
    name:     str
    fn:       Callable[..., Coroutine]
    interval: float
    status:   TaskStatus  = TaskStatus.PENDING
    last_run: float       = 0.0
    runs:     int         = 0
    errors:   int         = 0
    task:     Optional[asyncio.Task] = field(default=None, repr=False)


class BackgroundScheduler:
    """Simple interval-based background task scheduler."""

    def __init__(self) -> None:
        self._registry:   Dict[str, TaskInfo] = {}
        self._running:    bool                = False
        self._primitives_ready: bool          = False
        self._lock: Optional[asyncio.Lock]    = None

    def _ensure_primitives(self) -> None:
        if not self._primitives_ready:
            self._lock             = asyncio.Lock()
            self._primitives_ready = True

    def register(
        self,
        name:     str,
        fn:       Callable[..., Coroutine],
        interval: float,
    ) -> None:
        """Register a recurring task."""
        self._registry[name] = TaskInfo(name=name, fn=fn, interval=interval)
        logger.info(f"Scheduler: registered task '{name}' every {interval}s")

    async def start(self) -> None:
        """Start all registered tasks."""
        self._ensure_primitives()
        self._running = True
        logger.info(f"Scheduler: starting {len(self._registry)} tasks")
        for name, info in self._registry.items():
            task = asyncio.create_task(self._run_task(name), name=("sched:" + str(name)))
            task.add_done_callback(
                lambda t: logger.warning(f"[Scheduler] DEAD task: '{t.get_name()}'")
                if not t.cancelled() and t.exception() else None
            )
            info.task   = task
            info.status = TaskStatus.RUNNING

    async def stop(self) -> None:
        """Cancel all running tasks."""
        self._running = False
        for info in self._registry.values():
            if info.task and not info.task.done():
                info.task.cancel()
                try:
                    await info.task
                except asyncio.CancelledError:
                    pass
        logger.info("Scheduler: stopped")

    async def _run_task(self, name: str) -> None:
        """Run a single task in a loop."""
        info = self._registry[name]
        while self._running:
            start = time.monotonic()
            try:
                await info.fn()
                info.runs    += 1
                info.last_run = time.time()
                info.status   = TaskStatus.DONE
            except asyncio.CancelledError:
                break
            except Exception as exc:
                info.errors += 1
                info.status  = TaskStatus.FAILED
                logger.error(f"Scheduler task '{name}' error: {exc}")
            elapsed = time.monotonic() - start
            sleep   = max(0.0, info.interval - elapsed)
            await asyncio.sleep(sleep)

    def get_status(self) -> Dict[str, Any]:
        return {
            name: {
                "status":   i.status.value,
                "runs":     i.runs,
                "errors":   i.errors,
                "last_run": i.last_run,
                "interval": i.interval,
            }
            for name, i in self._registry.items()
        }


scheduler = BackgroundScheduler()
