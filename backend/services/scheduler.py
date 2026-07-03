"""Background Scheduler - Phase Q-28..Q-33 fixes
FIX: Converted all logger.xxx("msg %s", arg) to logger.xxx(f"msg {arg}")
FIX: Nested f-string quotes fixed.
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
    name:        str
    fn:          Callable
    interval_s:  float
    status:      TaskStatus = TaskStatus.PENDING
    error_count: int        = 0
    last_run:    float      = 0.0
    task:        Optional[asyncio.Task] = None


class BackgroundScheduler:
    _MAX_REGISTRY_SIZE = 64
    _MAX_ERROR_COUNT   = 10

    def __init__(self):
        self._registry: Dict[str, TaskInfo] = {}
        self._shutdown: asyncio.Event | None  = None
        self._started = False

    def _ensure_primitives(self) -> None:
        if self._shutdown is None:
            self._shutdown = asyncio.Event()

    def register(self, name: str, fn: Callable, interval_s: float) -> None:
        if len(self._registry) >= self._MAX_REGISTRY_SIZE:
            raise RuntimeError(f"Registry full ({self._MAX_REGISTRY_SIZE})")
        if name in self._registry:
            raise KeyError(f"Task '{name}' already registered")
        self._registry[name] = TaskInfo(name=name, fn=fn, interval_s=interval_s)
        logger.info(f"[Scheduler] Registered task '{name}' every {interval_s}s")

    def unregister(self, name: str) -> None:
        info = self._registry.pop(name, None)
        if info and info.task and not info.task.done():
            info.task.cancel()

    async def _run_task(self, name: str) -> None:
        info = self._registry[name]
        info.status = TaskStatus.RUNNING
        while not (self._shutdown and self._shutdown.is_set()):
            try:
                await info.fn()
                info.error_count = 0
                info.last_run    = time.time()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                info.error_count += 1
                logger.error(f"[Scheduler] Task '{name}' error #{info.error_count}: {exc}")
                if info.error_count >= self._MAX_ERROR_COUNT:
                    info.status = TaskStatus.DEAD
                    logger.critical(f"[Scheduler] Task '{name}' declared DEAD")
                    return
            await asyncio.sleep(info.interval_s)

    async def shutdown(self, timeout_s: float = 5.0) -> None:
        self._ensure_primitives()
        self._shutdown.set()
        logger.info(f"[Scheduler] shutdown {len(self._registry)} tasks")
        tasks = [info.task for info in self._registry.values() if info.task]
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout_s
            )

    async def start_all(self) -> None:
        self._ensure_primitives()
        for name, info in self._registry.items():
            task = asyncio.create_task(self._run_task(name), name=f"sched:{name}")
            task.add_done_callback(
                lambda t: logger.warning(f"[Scheduler] DEAD task: '{t.get_name()}'") \
                if not t.cancelled() and t.exception() else None
            )
            info.task = task


scheduler = BackgroundScheduler()
