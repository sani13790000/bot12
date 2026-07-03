"""Background Scheduler.

Fix Q-28: Converted nested f-string to string concatenation.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    name: str
    coro_factory: Callable[[], Coroutine]
    interval: float
    task: Optional[asyncio.Task] = None
    error_count: int = 0
    last_error: str = ""
    last_run: float = 0.0


class BackgroundScheduler:
    """Simple interval-based background task scheduler."""

    def __init__(self) -> None:
        self._registry: dict[str, TaskInfo] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._running = False

    def _ensure_primitives(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()

    def register(self, name: str, coro_factory: Callable, interval: float = 60.0) -> None:
        self._registry[name] = TaskInfo(name=name, coro_factory=coro_factory, interval=interval)
        logger.info("Registered task %s (interval=%.0fs)", name, interval)

    async def _run_task(self, name: str) -> None:
        import time
        info = self._registry[name]
        while self._running:
            try:
                info.last_run = time.time()
                await info.coro_factory()
                info.error_count = 0
            except asyncio.CancelledError:
                break
            except Exception as exc:
                info.error_count += 1
                info.last_error = str(exc)
                logger.exception("[Scheduler] Task %s error #%d: %s", name, info.error_count, exc)
            await asyncio.sleep(info.interval)

    async def start_all(self) -> None:
        self._ensure_primitives()
        self._running = True
        for name in self._registry:
            task = asyncio.create_task(self._run_task(name), name=("sched:" + str(name)))
            task.add_done_callback(
                lambda t: logger.warning("[Scheduler] DEAD task: '%s'", t.get_name())
                if not t.cancelled() and t.exception() else None
            )
            self._registry[name].task = task

    async def stop_all(self) -> None:
        self._running = False
        for info in self._registry.values():
            if info.task and not info.task.done():
                info.task.cancel()

    def status(self) -> dict:
        return {
            name: {
                "running": bool(info.task and not info.task.done()),
                "error_count": info.error_count,
                "last_error": info.last_error,
                "interval": info.interval,
            }
            for name, info in self._registry.items()
        }


scheduler = BackgroundScheduler()
