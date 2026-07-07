"""
heartbeat.py — Telegram Bot liveness heartbeat

Writes /tmp/bot_heartbeat every INTERVAL seconds while the bot is polling.
Docker healthcheck reads this file to detect dead polling.

Usage (in bot.py polling loop):
    from backend.telegram.heartbeat import start_heartbeat, stop_heartbeat
    await start_heartbeat()
    # ... polling ...
    await stop_heartbeat()

Docker healthcheck command:
    python3 -c "
import os, time, sys
try:
    age = time.time() - os.path.getmtime('/tmp/bot_heartbeat')
    sys.exit(0 if age < 120 else 1)
except FileNotFoundError:
    sys.exit(1)
"
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

HEARTBEAT_FILE = "/tmp/bot_heartbeat"
INTERVAL = 30  # seconds

_task: Optional[asyncio.Task] = None
_running = False


def _write_heartbeat() -> None:
    """Write current timestamp to heartbeat file."""
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(str(time.time()))
    except OSError as e:
        logger.warning("[Heartbeat] Could not write %s: %s", HEARTBEAT_FILE, e)


async def _heartbeat_loop() -> None:
    """Background loop that updates the heartbeat file."""
    global _running
    logger.info("[Heartbeat] Started — writing to %s every %ds", HEARTBEAT_FILE, INTERVAL)
    _write_heartbeat()  # Write immediately on start
    while _running:
        await asyncio.sleep(INTERVAL)
        if _running:
            _write_heartbeat()
    logger.info("[Heartbeat] Stopped")


async def start_heartbeat() -> None:
    """Start the heartbeat background task."""
    global _task, _running
    if _task is not None and not _task.done():
        return  # Already running
    _running = True
    _task = asyncio.create_task(_heartbeat_loop())


async def stop_heartbeat() -> None:
    """Stop the heartbeat background task."""
    global _task, _running
    _running = False
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    # Clean up file
    try:
        os.remove(HEARTBEAT_FILE)
    except FileNotFoundError:
        pass


def is_alive(max_age_seconds: int = 120) -> bool:
    """Check if heartbeat file is fresh (for health endpoints)."""
    try:
        age = time.time() - os.path.getmtime(HEARTBEAT_FILE)
        return age < max_age_seconds
    except FileNotFoundError:
        return False
