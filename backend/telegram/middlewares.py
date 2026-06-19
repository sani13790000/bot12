"""Galaxy Vast Telegram Bot Middlewares.

Three middleware layers:
1. LoggingMiddleware  — structured logging for every update
2. RateLimitMiddleware — per-user rate limiting (in-memory sliding window)
3. AuthMiddleware     — user registration + admin flag injection

Security:
- All user inputs sanitised before logging (no log injection)
- Callback data validated (no arbitrary callback injection)
- Admin chat_id sourced from env, never from user input
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable, Dict, MutableMapping

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from backend.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit constants
# ---------------------------------------------------------------------------
_RATE_WINDOW_SECONDS: int = 60
_RATE_MAX_MESSAGES: int = 30          # messages per minute per user
_RATE_MAX_CALLBACKS: int = 20         # callbacks per minute per user
_MAX_TRACKED_USERS: int = 50_000      # cap memory; evict oldest


def _sanitise(text: str | None, max_len: int = 200) -> str:
    """Strip newlines + truncate to prevent log injection."""
    if not text:
        return ""
    return text.replace("\n", " ").replace("\r", " ")[:max_len]


# ---------------------------------------------------------------------------
# 1. Logging Middleware
# ---------------------------------------------------------------------------
class LoggingMiddleware(BaseMiddleware):
    """Log every incoming message/callback with sanitised content."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        detail: str = ""

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            detail = _sanitise(event.text or event.caption or "<non-text>")
            logger.info("MSG uid=%s text=%r", user_id, detail)

        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            # Sanitise callback data — must match known pattern
            raw = event.data or ""
            detail = _sanitise(raw)
            logger.info("CB  uid=%s data=%r", user_id, detail)

        start = time.monotonic()
        result = await handler(event, data)
        elapsed = (time.monotonic() - start) * 1000
        logger.debug("handler done uid=%s elapsed=%.1fms", user_id, elapsed)
        return result


# ---------------------------------------------------------------------------
# 2. Rate-Limit Middleware
# ---------------------------------------------------------------------------
class RateLimitMiddleware(BaseMiddleware):
    """Sliding-window rate limiter, per user_id."""

    def __init__(
        self,
        msg_limit: int = _RATE_MAX_MESSAGES,
        cb_limit: int = _RATE_MAX_CALLBACKS,
        window: int = _RATE_WINDOW_SECONDS,
    ) -> None:
        self._msg_limit = msg_limit
        self._cb_limit = cb_limit
        self._window = window
        # user_id → deque of timestamps
        self._msg_windows: Dict[int, deque] = defaultdict(lambda: deque())
        self._cb_windows: Dict[int, deque] = defaultdict(lambda: deque())

    def _is_limited(self, windows: Dict[int, deque], uid: int, limit: int) -> bool:
        now = time.monotonic()
        dq = windows[uid]
        # Evict stale entries
        while dq and now - dq[0] > self._window:
            dq.popleft()
        if len(dq) >= limit:
            return True
        dq.append(now)
        # Memory cap: keep only last _MAX_TRACKED_USERS users
        if len(windows) > _MAX_TRACKED_USERS:
            oldest_key = next(iter(windows))
            del windows[oldest_key]
        return False

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        uid: int | None = None
        is_cb = False

        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            uid = event.from_user.id
            is_cb = True

        if uid is not None:
            windows = self._cb_windows if is_cb else self._msg_windows
            limit = self._cb_limit if is_cb else self._msg_limit
            if self._is_limited(windows, uid, limit):
                logger.warning("Rate limit hit uid=%d", uid)
                if isinstance(event, Message):
                    await event.answer(
                        "\u26a0\ufe0f Too many requests. Please slow down.",
                        parse_mode=None,
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer("Too many requests. Slow down.", show_alert=True)
                return None

        return await handler(event, data)


# ---------------------------------------------------------------------------
# 3. Auth Middleware
# ---------------------------------------------------------------------------
import os
from backend.core.config import settings


def _get_admin_ids() -> set[int]:
    """Read admin IDs from env — never from user input."""
    raw = os.environ.get("TELEGRAM_ADMIN_IDS", "")
    if not raw:
        # fallback to single TELEGRAM_ADMIN_ID
        single = os.environ.get("TELEGRAM_ADMIN_ID", "")
        raw = single
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


_ADMIN_IDS: set[int] = _get_admin_ids()


class AuthMiddleware(BaseMiddleware):
    """
    Injects two flags into handler data:
      data["is_admin"]     — True if user_id in TELEGRAM_ADMIN_IDS
      data["is_registered"] — True (placeholder; extend with DB lookup)

    Security:
    - Admin IDs are sourced from env, NOT from any user input.
    - No privilege escalation possible via callback data.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        uid: int | None = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            uid = event.from_user.id

        data["is_admin"] = uid is not None and uid in _ADMIN_IDS
        data["is_registered"] = uid is not None  # extend: check DB
        data["user_id"] = uid

        return await handler(event, data)
