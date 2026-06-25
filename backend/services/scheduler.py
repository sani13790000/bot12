"""Background Scheduler - Phase Q-28..Q-33 fixes
FIX: Converted all logger.xxx("msg %s", arg) to logger.xxx(f"msg {arg}")
"""
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
    PENDING = "pending"
    RUNNING = "running"
    DEAD    = "dead"


@dataclass
class TaskInfo:
    name:       str
    fn:         Callable
    interval_s: float
    status:     TaskStatus = TaskStatus.PENDING
    error_count: int       = 0
    last_run:   float      = 0.0
    task:       Optional[asyncio.Task] = None


class BackgroundScheduler:
    _MAX_REGISTRY = 50

    def __init__(self) -> None:
        self._registry: Dict[str, TaskInfo] = {}
        self._shutdown: Optional[asyncio.Event] = None
        self._loop_task: Optional[asyncio.Task] = None

    def _ensure_primitives(self) -> None:
        if self._shutdown is None:
            self._shutdown = asyncio.Event()

    def register(
        self,
        name:       str,
        fn:         Callable,
        interval_s: float,
    ) -> None:
        if name in self._registry:
            logger.warning(f"[Scheduler] '{name}' already registered"); return
        if len(self._registry) >= self._MAX_REGISTRY:
            logger.error(f"[Scheduler] registry full ({self._MAX_REGISTRY})"); return
        self._registry[name] = TaskInfo(name=name, fn=fn, interval_s=interval_s)
        logger.info(f"[Scheduler] registered '{name}' interval={interval_s:.0f}s")

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
            except asyncio.TimeoutError: pass
            try:
                await info.fn()
                info.last_run = time.monotonic()
            except Exception as e:
                info.error_count += 1
                logger.error(f"[Scheduler] '{name}' error #{info.error_count}: {e}")
        info.status = TaskStatus.DEAD
        logger.info(f"[Scheduler] '{name}' stopped")

    async def shutdown(self, timeout_s: float = 10.0) -> None:
        self._ensure_primitives()
        self._shutdown.set()
        logger.info(f"[Scheduler] shutdown {len(self._registry)} tasks")
        tasks = [info.task for info in self._registry.values() if info.task]
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout_s)

    async def start_all(self) -> None:
        self._ensure_primitives()
        for name, info in self._registry.items():
            task = asyncio.create_task(self._run_task(name), name=f"sched:{"name}")
            task.add_done_callback(
                lambda t: logger.warning(f"[Scheduler] DEAD task: '{t.get_name()}'")
                if not t.cancelled() and t.exception() else None
            )
            info.task = task


scheduler = BackgroundScheduler()
