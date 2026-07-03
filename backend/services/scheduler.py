from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional
from ..core.logger import get_logger

logger = get_logger('services.scheduler')


@dataclass
class TaskInfo:
    name: str
    coro_fn: Callable[[], Coroutine[Any, Any, None]]
    interval_s: float
    task: Optional[asyncio.Task] = field(default=None, repr=False)
    run_count: int = 0
    error_count: int = 0


class Scheduler:
    def __init__(self):
        self._registry: Dict[str, TaskInfo] = {}
        self._lock = None
        self._event = None

    def _ensure_primitives(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
            self._event = asyncio.Event()

    def register(self, name, coro_fn, interval_s=60.0):
        self._registry[name] = TaskInfo(name=name, coro_fn=coro_fn, interval_s=interval_s)
        logger.info('Scheduler registered task: %s (every %.0fs)', name, interval_s)

    async def _run_task(self, name):
        info = self._registry[name]
        while True:
            try:
                await info.coro_fn()
                info.run_count += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                info.error_count += 1
                logger.error("[Scheduler] Task '%s' error #%d: %s", name, info.error_count, exc)
            await asyncio.sleep(info.interval_s)

    async def start_all(self):
        self._ensure_primitives()
        for name, info in self._registry.items():
            task = asyncio.create_task(self._run_task(name), name=('sched:' + name))
            info.task = task
        logger.info('Scheduler started %d tasks', len(self._registry))

    async def stop_all(self):
        for info in self._registry.values():
            if info.task and not info.task.done():
                info.task.cancel()

    def status(self):
        return {name: {'running': not (info.task.done() if info.task else True), 'runs': info.run_count, 'errors': info.error_count} for name, info in self._registry.items()}
