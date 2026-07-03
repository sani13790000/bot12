"""
Module: scheduler
Path: backend/services/scheduler.py
Task scheduler stub.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable, Dict

log = logging.getLogger(__name__)


class Scheduler:
    """Simple async task scheduler."""

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}

    def schedule(self, name: str, coro: Callable, interval_s: float) -> None:
        log.info("scheduler_register name=%s interval=%s", name, interval_s)

    def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()


scheduler = Scheduler()
