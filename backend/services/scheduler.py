"""Background Scheduler - Phase Q-28..Q-33 fixes."""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("services.scheduler")


class TaskStatus(str, Enum):
    PENDING  = "PENDING"
    RUNNING  = "RUNNING"
    SUCCESS  = "SUCCESS"
    FAILED   = "FAILED"
    DISABLED = "DISABLED"


@dataclass
class TaskInfo:
    name:         str
    coro_factory: Callable
    interval_s:   float
    enabled:      bool       = True
    status:       TaskStatus = TaskStatus.PENDING
    last_run:     float      = 0.0
    last_error:   str        = ""
    run_count:    int        = 0
    fail_count:   int        = 0
    task:         Optional[asyncio.Task] = field(default=None, repr=False)


class Scheduler:
    """Async background task scheduler."""

    def __init__(self) -> None:
        self._registry:   Dict[str, TaskInfo]    = {}
        self._started:    bool                   = False
        self._lock:       Optional[asyncio.Lock]  = None
        self._stop_event: Optional[asyncio.Event] = None

    def register(self, name: str, coro_factory: Callable, interval_s: float, enabled: bool = True) -> None:
        if name in self._registry:
            raise ValueError(f"Task already registered: {name}")
        self._registry[name] = TaskInfo(name=name, coro_factory=coro_factory, interval_s=interval_s, enabled=enabled)
        logger.info(f"Registered task {name} every {interval_s}s")

    def _ensure_primitives(self) -> None:
        if self._lock is None:
            self._lock       = asyncio.Lock()
            self._stop_event = asyncio.Event()

    async def start_all(self) -> None:
        self._ensure_primitives()
        for name, info in self._registry.items():
            if not info.enabled:
                continue
            task = asyncio.create_task(self._run_task(name), name=("sched:" + name))
            task.add_done_callback(
                lambda t: logger.warning(f"[Scheduler] DEAD: {t.get_name()}")
                if not t.cancelled() and t.exception() else None
            )
            info.task = task
        self._started = True
        logger.info(f"Scheduler started: {len(self._registry)} tasks")

    async def stop_all(self, timeout_s: float = 5.0) -> None:
        if self._stop_event:
            self._stop_event.set()
        tasks = [i.task for i in self._registry.values() if i.task]
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout_s)

    async def _run_task(self, name: str) -> None:
        info = self._registry[name]
        while not (self._stop_event and self._stop_event.is_set()):
            await asyncio.sleep(info.interval_s)
            if not info.enabled:
                continue
            t0 = time.perf_counter()
            try:
                info.status   = TaskStatus.RUNNING
                info.last_run = time.time()
                await info.coro_factory()
                info.status    = TaskStatus.SUCCESS
                info.run_count += 1
                logger.debug(f"Task {name} OK in {(time.perf_counter()-t0)*1000:.1f}ms")
            except Exception as exc:
                info.status     = TaskStatus.FAILED
                info.fail_count += 1
                info.last_error = str(exc)
                logger.error(f"Task {name} FAILED: {exc}")
