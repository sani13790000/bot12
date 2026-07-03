"""
backend/self_learning/retraining_service.py
Galaxy Vast AI — Self-Learning Retraining Service
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class RetrainingService:
    """Manages periodic model retraining."""

    def __init__(self, interval_hours: float = 24.0) -> None:
        self.interval_hours = interval_hours
        self._running = False
        self._last_run: datetime | None = None
        self._run_count = 0

    async def start(self) -> None:
        self._running = True
        logger.info("RetrainingService started")
        asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.interval_hours * 3600)
            if self._running:
                await self.retrain()

    async def retrain(self) -> dict[str, Any]:
        logger.info("Starting model retraining...")
        self._last_run = datetime.utcnow()
        self._run_count += 1
        return {
            "status": "completed",
            "run_id": self._run_count,
            "timestamp": self._last_run.isoformat(),
        }

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "run_count": self._run_count,
        }


_service: RetrainingService | None = None


def get_retraining_service() -> RetrainingService:
    global _service
    if _service is None:
        _service = RetrainingService()
    return _service


__all__ = ["RetrainingService", "get_retraining_service"]
