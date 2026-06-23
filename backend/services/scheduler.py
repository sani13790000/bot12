"""Background Scheduler - Phase Q-28..Q-33 fixes."""
from __future__ import annotations
import asyncio, logging, random, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional
logger = logging.getLogger(__name__)

class TaskStatus(str, Enum):
    RUNNING  = "running"
    SLEEPING = "sleeping"
    DEAD     = "dead"
    STOPPING = "stopping"

@dataclass
class TaskInfo:
    name:       str
    interval_s: float
    status:     TaskStatus = TaskStatus.SLEEPING
    last_run:   Optional[datetime] = None
    last_error: Optional[str] = None
    run_count:  int = 0
    error_count:int = 0
    task:       Optional[asyncio.Task] = None  # type: ignore

class BackgroundScheduler:
    _MAX_REGISTRY = 100

    def __init__(self) -> None:
        self._registry: Dict[str, TaskInfo] = {}
        self._shutdown = asyncio.Event()
        self._lock = asyncio.Lock()

    def register(self, name: str, coro_fn: Callable[[], Coroutine[Any, Any, None]],
                 interval_s: float, jitter_s: float = 0.0, startup_delay_s: float = 0.0) -> None:
        if name in self._registry:
            logger.warning("[Scheduler] '%s' already registered", name); return
        if len(self._registry) >= self._MAX_REGISTRY:
            logger.error("[Scheduler] registry full (%d)", self._MAX_REGISTRY); return
        info = TaskInfo(name=name, interval_s=interval_s)
        self._registry[name] = info
        info.task = asyncio.get_event_loop().create_task(
            self._run_loop(name, coro_fn, interval_s, jitter_s, startup_delay_s),
            name=f"scheduler:{name}"
        )
        logger.info("[Scheduler] registered '%s' interval=%.0fs", name, interval_s)

    async def _run_loop(self, name: str, coro_fn: Callable[[], Coroutine[Any, Any, None]],
                        interval_s: float, jitter_s: float, startup_delay_s: float) -> None:
        info = self._registry[name]
        if startup_delay_s > 0: await asyncio.sleep(startup_delay_s)
        while not self._shutdown.is_set():
            sleep_s = interval_s + random.uniform(0, jitter_s)
            try:
                info.status = TaskStatus.RUNNING
                info.last_run = datetime.now(timezone.utc)
                await coro_fn()
                info.run_count += 1
                info.last_error = None
            except asyncio.CancelledError:
                info.status = TaskStatus.STOPPING
                logger.info("[Scheduler] '%s' cancelled", name); return
            except Exception as e:
                info.error_count += 1
                info.last_error = str(e)
                logger.error("[Scheduler] '%s' error #%d: %s", name, info.error_count, e, exc_info=True)
                if info.error_count > 3: sleep_s = min(sleep_s, 60.0)
            finally:
                if info.status != TaskStatus.STOPPING: info.status = TaskStatus.SLEEPING
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=sleep_s)
                break
            except asyncio.TimeoutError: pass
        info.status = TaskStatus.DEAD
        logger.info("[Scheduler] '%s' stopped", name)

    async def shutdown(self, timeout_s: float = 10.0) -> None:
        logger.info("[Scheduler] shutdown %d tasks", len(self._registry))
        self._shutdown.set()
        tasks = [i.task for i in self._registry.values() if i.task and not i.task.done()]
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout_s)
            for t in pending: t.cancel()
        self._registry.clear()
        logger.info("[Scheduler] shutdown complete")

    def health(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc); dead = 0; infos = []
        for name, info in self._registry.items():
            ago = round((now - info.last_run).total_seconds(), 1) if info.last_run else None
            overdue = (info.status == TaskStatus.SLEEPING and ago is not None and ago > info.interval_s * 3)
            if overdue or info.status == TaskStatus.DEAD:
                dead += 1
                logger.warning("[Scheduler] DEAD task: '%s'", name)
            infos.append({"name": name, "status": info.status.value, "interval_s": info.interval_s,
                          "run_count": info.run_count, "error_count": info.error_count,
                          "last_run_ago_s": ago, "last_error": info.last_error, "is_overdue": overdue})
        return {"total_tasks": len(self._registry), "dead_count": dead,
                "healthy": dead == 0, "tasks": infos}

_scheduler: Optional[BackgroundScheduler] = None
def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None: _scheduler = BackgroundScheduler()
    return _scheduler
