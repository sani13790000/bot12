"""
backend/services/scheduler.py
Galaxy Vast AI -- Background Task Scheduler

A lightweight async scheduler that runs periodic tasks inside the
FastAPI process. All primitives are asyncio-based (no threads).

FIX: nested f-string f"sched:{"name"}" replaced with string concat.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    """Metadata for a registered periodic task."""
    name:        str
    coro_fn:     Callable[..., Coroutine[Any, Any, None]]
    interval_s:  float
    enabled:     bool  = True
    last_run:    float = 0.0
    run_count:   int   = 0
    error_count: int   = 0


class Scheduler:
    """
    Simple periodic task scheduler.

    Usage::

        scheduler = Scheduler()
        scheduler.register("heartbeat", heartbeat_fn, interval_s=30)
        await scheduler.start()
        # ... at shutdown:
        await scheduler.stop()
    """

    def __init__(self) -> None:
        self._registry: Dict[str, TaskInfo] = {}
        self._tasks:    Dict[str, asyncio.Task] = {}
        self._running:  bool = False
        self._lock:     asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def register(
        self,
        name:       str,
        coro_fn:    Callable[..., Coroutine[Any, Any, None]],
        interval_s: float = 60.0,
        enabled:    bool  = True,
    ) -> None:
        """Register a periodic coroutine. Call before start()."""
        self._registry[name] = TaskInfo(
            name=name,
            coro_fn=coro_fn,
            interval_s=interval_s,
            enabled=enabled,
        )
        logger.debug("[Scheduler] registered task '%s' every %.0fs", name, interval_s)

    async def start(self) -> None:
        """Spawn asyncio tasks for all registered, enabled entries."""
        if self._running:
            logger.warning("[Scheduler] already running — ignoring start()")
            return
        self._running = True
        self._ensure_primitives()
        for name, info in self._registry.items():
            if not info.enabled:
                continue
            task = asyncio.create_task(self._run_task(name), name=("sched:" + str(name)))
            task.add_done_callback(
                lambda t: logger.warning("[Scheduler] DEAD task: '%s'", t.get_name())
                if t.cancelled() or t.exception() else None
            )
            self._tasks[name] = task
        logger.info("[Scheduler] started %d tasks", len(self._tasks))

    async def stop(self) -> None:
        """Cancel all running tasks gracefully."""
        self._running = False
        for name, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._tasks.clear()
        logger.info("[Scheduler] stopped")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _ensure_primitives(self) -> None:
        """Re-create Lock on the running loop (needed after restart)."""
        try:
            loop = asyncio.get_running_loop()
            if self._lock._loop is not loop:  # type: ignore[attr-defined]
                self._lock = asyncio.Lock()
        except RuntimeError:
            pass

    async def _run_task(self, name: str) -> None:
        """Periodic loop for a single task."""
        info = self._registry[name]
        logger.info("[Scheduler] task '%s' started (interval=%.0fs)", name, info.interval_s)
        while self._running and info.enabled:
            await asyncio.sleep(info.interval_s)
            if not self._running:
                break
            try:
                await info.coro_fn()
                info.run_count += 1
                logger.debug("[Scheduler] '%s' run #%d OK", name, info.run_count)
            except Exception as exc:
                info.error_count += 1
                logger.error(
                    "[Scheduler] '%s' error #%d: %s",
                    name, info.error_count, exc, exc_info=True,
                )
        logger.info("[Scheduler] task '%s' stopped", name)


# Module-level singleton
scheduler = Scheduler()
