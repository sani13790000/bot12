"""Background Scheduler - Phase Q-28..Q-33 fixes
FIX: Converted all logger.xxx("msg %s", arg) to logger.xxx(f"msg {arg}")
FIX: f"sched:{name}" nested f-string replaced with string concat
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    task:       Optional[asyncio.Task] = None  # type: ignore[type-arg]
    last_run:   float = field(default_factory=time.monotonic)
    error_count: int  = 0


class BackgroundScheduler:
    """Registry-based background task scheduler."""

    _MAX_REGISTRY = 64

    def __init__(self) -> None:
        self._registry: Dict[str, TaskInfo] = {}
        self._shutdown:  Optional[asyncio.Event] = None
        self._lock:      Optional[asyncio.Lock]  = None

    # ------------------------------------------------------------------ setup
    def _ensure_primitives(self) -> None:
        if self._shutdown is None:
            self._shutdown = asyncio.Event()
        if self._lock is None:
            self._lock = asyncio.Lock()

    # ---------------------------------------------------------------- register
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

    # --------------------------------------------------------------- task loop
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

    # ------------------------------------------------------------ lifecycle
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
            _task_name = "sched:" + name
            task = asyncio.create_task(self._run_task(name), name=_task_name)
            task.add_done_callback(
                lambda t: logger.warning(f"[Scheduler] DEAD task: '{t.get_name()}'")
                if not t.cancelled() and t.exception() else None
            )
            info.task = task


scheduler = BackgroundScheduler()
