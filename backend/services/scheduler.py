"""
backend/services/scheduler.py
Background Scheduler — Galaxy Vast AI

Fixes applied:
  - Converted all logger.xxx("msg %s", arg) to logger.xxx(f"msg {arg}")
  - Proper async task management with cancellation
  - Fail-safe exception handling per job
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    name: str
    fn: Callable[[], Coroutine]
    interval_seconds: float
    last_run: float = 0.0
    run_count: int = 0
    error_count: int = 0
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class BackgroundScheduler:
    """Simple asyncio-based background scheduler."""

    def __init__(self) -> None:
        self._jobs: Dict[str, ScheduledJob] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._log = logging.getLogger(self.__class__.__name__)

    def register(self, name: str, fn: Callable, interval_seconds: float, **metadata) -> None:
        """Register a job to run every interval_seconds."""
        self._jobs[name] = ScheduledJob(
            name=name, fn=fn, interval_seconds=interval_seconds, metadata=metadata
        )
        self._log.info(f"Registered job '{name}' every {interval_seconds}s")

    def unregister(self, name: str) -> bool:
        if name in self._jobs:
            del self._jobs[name]
            return True
        return False

    async def start(self) -> None:
        """Start all registered jobs."""
        self._running = True
        for name, job in self._jobs.items():
            if job.enabled:
                self._tasks[name] = asyncio.create_task(self._run_job(job))
        self._log.info(f"Scheduler started with {len(self._tasks)} jobs")

    async def stop(self) -> None:
        """Cancel all running tasks."""
        self._running = False
        for name, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        self._log.info("Scheduler stopped")

    async def _run_job(self, job: ScheduledJob) -> None:
        """Run a job on its interval, with exception isolation."""
        while self._running:
            now = time.monotonic()
            if now - job.last_run >= job.interval_seconds:
                try:
                    await job.fn()
                    job.run_count += 1
                    job.last_run = time.monotonic()
                    self._log.debug(f"Job '{job.name}' completed (run #{job.run_count})")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    job.error_count += 1
                    self._log.error(f"Job '{job.name}' failed: {exc}")
            await asyncio.sleep(1.0)

    def status(self) -> List[Dict[str, Any]]:
        """Return status of all jobs."""
        return [
            {
                "name": j.name,
                "enabled": j.enabled,
                "interval_seconds": j.interval_seconds,
                "run_count": j.run_count,
                "error_count": j.error_count,
                "last_run": j.last_run,
            }
            for j in self._jobs.values()
        ]

    @property
    def is_running(self) -> bool:
        return self._running


_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler
