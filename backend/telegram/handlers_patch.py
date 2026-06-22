from __future__ import annotations
import logging, time
from functools import wraps
from typing import Any, Callable, Dict, Set

logger = logging.getLogger(__name__)

_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX    = 30


class _RateLimiter:
    """P-14 FIX: per-chat rate limiter."""
    def __init__(self) -> None:
        self._counts: Dict[int, list] = {}

    def is_allowed(self, chat_id: int) -> bool:
        now = time.time()
        window = self._counts.setdefault(chat_id, [])
        self._counts[chat_id] = [t for t in window if now - t < _RATE_LIMIT_WINDOW]
        if len(self._counts[chat_id]) >= _RATE_LIMIT_MAX:
            return False
        self._counts[chat_id].append(now)
        return True


_rate_limiter = _RateLimiter()

# P-13 FIX: idempotency
_processed_callbacks: Set[str] = set()
_idempotency_timestamps: Dict[str, float] = {}
_IDEMPOTENCY_TTL = 300


def _register_callback(callback_id: str) -> bool:
    now = time.time()
    expired = [k for k, t in _idempotency_timestamps.items() if now - t > _IDEMPOTENCY_TTL]
    for k in expired:
        _processed_callbacks.discard(k)
        del _idempotency_timestamps[k]
    if callback_id in _processed_callbacks:
        return False
    _processed_callbacks.add(callback_id)
    _idempotency_timestamps[callback_id] = now
    return True


def safe_handler(func: Callable) -> Callable:
    """P-11 FIX: wraps handlers - no crash on DB/network errors."""
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> None:
        update  = args[-2] if len(args) >= 2 else None
        context = args[-1] if len(args) >= 1 else None
        try:
            await func(*args, **kwargs)
        except Exception as exc:
            logger.error("[Handler] %s error: %s", func.__name__, exc, exc_info=True)
            try:
                if update and hasattr(update, "effective_chat") and update.effective_chat:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="error - please retry",
                    )
            except Exception:
                pass
    return wrapper


def rate_limited(func: Callable) -> Callable:
    """P-14 FIX: rate limit decorator."""
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> None:
        update  = args[-2] if len(args) >= 2 else None
        context = args[-1] if len(args) >= 1 else None
        chat_id = 0
        if update and hasattr(update, "effective_chat") and update.effective_chat:
            chat_id = update.effective_chat.id
        if not _rate_limiter.is_allowed(chat_id):
            try:
                await context.bot.send_message(chat_id=chat_id, text="rate limited - wait")
            except Exception:
                pass
            return
        await func(*args, **kwargs)
    return wrapper


def format_signal_safe(signal: Dict[str, Any]) -> str:
    """P-15 FIX: never AttributeError on None fields."""
    direction  = signal.get("direction", "?")
    symbol     = signal.get("symbol", "?")
    entry      = signal.get("entry_price")
    sl         = signal.get("stop_loss")
    tp1        = signal.get("take_profit_1") or signal.get("take_profit")
    confidence = signal.get("confidence_score", signal.get("confidence", 0))
    risk_level = signal.get("risk_level", "?")
    signal_id  = signal.get("id", signal.get("signal_id", "?"))
    emoji      = "UP" if direction == "BUY" else "DN" if direction == "SELL" else "-"
    lines = [
        f"{emoji} {symbol} - {direction} | ID:{signal_id}",
        f"Entry: {f'{entry:.5f}' if entry is not None else 'N/A'}",
        f"SL: {f'{sl:.5f}' if sl is not None else 'N/A'}",
        f"TP1: {f'{tp1:.5f}' if tp1 is not None else 'N/A'}",
        f"Confidence: {confidence}% | Risk: {risk_level}",
    ]
    return "\n".join(lines)


async def answer_callback_safe(query: Any, text: str = "ok") -> None:
    """P-12 FIX: always answer callback."""
    try:
        await query.answer(text)
    except Exception as exc:
        logger.debug("[Handler] answer_callback: %s", exc)


class ApproveRejectHandler:
    """P-12+P-13 FIX: approve/reject with immediate answer + idempotency."""

    def __init__(self, semi_auto_service: Any) -> None:
        self._svc = semi_auto_service

    @safe_handler
    async def handle(self, update: Any, context: Any) -> None:
        query = update.callback_query
        data  = query.data or ""
        # P-12 FIX: answer immediately
        await answer_callback_safe(query)
        if not data.startswith(("approve_", "reject_")):
            return
        parts     = data.split("_", 1)
        action    = parts[0]
        signal_id = parts[1] if len(parts) > 1 else ""
        # P-13 FIX: idempotency check
        if not _register_callback(f"{action}_{signal_id}"):
            try:
                await query.edit_message_text("already processed")
            except Exception:
                pass
            return
        try:
            if action == "approve":
                await self._svc.approve(signal_id)
                await query.edit_message_text(f"approved: {signal_id}")
            else:
                await self._svc.reject(signal_id)
                await query.edit_message_text(f"rejected: {signal_id}")
        except Exception as exc:
            logger.error("[Handler] approve/reject signal=%s: %s", signal_id, exc)
            try:
                await query.edit_message_text(f"error: {exc}")
            except Exception:
                pass
