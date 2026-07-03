"""backend/services/scheduler.py"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable
logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks.values():
            t.cancel()
        self._tasks.clear()

    def schedule(self, name: str, coro_fn: Callable, interval: float = 60.0) -> None:
        async def _loop():
            while self._running:
                try:
                    await coro_fn()
                except Exception as e:
                    logger.error(f"Task {name} failed: {e}")
                await asyncio.sleep(interval)
        if name in self._tasks:
            self._tasks[name].cancel()
        self._tasks[name] = asyncio.create_task(_loop())

_scheduler: Scheduler | None = None

def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler

__all__ = ["Scheduler", "get_scheduler"]
