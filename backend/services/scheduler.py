"""Background Scheduler - Phase Q-28..Q-33 fixes
FIX: Converted all logger.xxx to use f-strings properly.
FIX: Fixed nested f-string 'sched:{name}' -> 'sched:' + name
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional

log = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    func: Callable[[], Coroutine[Any, Any, None]]
    interval_s: float
    task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
    run_count: int = 0
    error_count: int = 0


class BackgroundScheduler:
    """Simple interval-based background task scheduler."""

    def __init__(self) -> None:
        self._registry: Dict[str, TaskInfo] = {}
        self._started = False
        self._lock: Optional[asyncio.Lock] = None
        self._event: Optional[asyncio.Event] = None

    def _ensure_primitives(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        if self._event is None:
            self._event = asyncio.Event()

    def register(
        self,
        name: str,
        func: Callable[[], Coroutine[Any, Any, None]],
        interval_s: float,
    ) -> None:
        """Register a background task."""
        self._registry[name] = TaskInfo(func=func, interval_s=interval_s)
        log.info("Scheduler registered task: %s (interval=%.0fs)", name, interval_s)

    async def _run_task(self, name: str) -> None:
        """Run a single task in a loop."""
        info = self._registry[name]
        while True:
            try:
                await info.func()
                info.run_count += 1
            except asyncio.CancelledError:
                log.info("Task cancelled: %s", name)
                break
            except Exception as exc:
                info.error_count += 1
                log.exception("Task error: %s -> %s", name, exc)
            await asyncio.sleep(info.interval_s)

    async def start_all(self) -> None:
        """Start all registered tasks."""
        self._ensure_primitives()
        for name, info in self._registry.items():
            task = asyncio.create_task(self._run_task(name), name="sched:" + name)
            task.add_done_callback(
                lambda t: log.warning("[Scheduler] DEAD task: %s", t.get_name())
                if not t.cancelled() and t.exception() else None
            )
            info.task = task
        self._started = True
        log.info("Scheduler started %d tasks", len(self._registry))

    async def stop_all(self, timeout_s: float = 5.0) -> None:
        """Cancel all tasks and wait for them to finish."""
        tasks = [
            info.task
            for info in self._registry.values()
            if info.task and not info.task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=timeout_s
            )
        self._started = False
        log.info("Scheduler stopped")

    def status(self) -> Dict[str, Any]:
        """Return status of all registered tasks."""
        return {
            name: {
                "running": bool(info.task and not info.task.done()),
                "run_count": info.run_count,
                "error_count": info.error_count,
                "interval_s": info.interval_s,
            }
            for name, info in self._registry.items()
        }


# Module-level singleton
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    """Return the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler
