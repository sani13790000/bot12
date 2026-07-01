"""
backend/services/scheduler.py
Galaxy Vast AI — Task Scheduler
NOTE: Auto-repaired stub due to binary corruption.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

_LOG = logging.getLogger(__name__)


class Scheduler:
    """Async task scheduler."""

    def __init__(self) -> None:
        self._registry: Dict[str, Dict] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def register(self, name: str, coro_fn: Callable, interval_s: float = 60) -> None:
        self._registry[name] = {'fn': coro_fn, 'interval': interval_s}

    async def _run_task(self, name: str) -> None:
        info = self._registry[name]
        while True:
            try:
                await info['fn']()
            except Exception as e:
                _LOG.warning('Scheduler task %s failed: %s', name, e)
            await asyncio.sleep(info['interval'])

    async def start(self) -> None:
        for name in self._registry:
            task = asyncio.create_task(self._run_task(name), name=f'sched:{name}')
            self._tasks[name] = task

    async def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()


_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
