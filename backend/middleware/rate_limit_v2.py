"""backend/middleware/rate_limit_v2.py — Phase 12
P12-FIX-RL-1: X-Forwarded-For فقط از trusted proxies
P12-FIX-RL-2: per-user rate limiting
P12-FIX-RL-3: endpoint-specific limits
P12-FIX-RL-4: standardized 429 + retry-after
P12-FIX-RL-5: bounded memory 100K
"""
from __future__ import annotations
import asyncio, logging, time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple
from fastapi import Request
from fastapi.responses import JSONResponse
from ..core.error_codes import EC, api_error
import base64, json

log = logging.getLogger("middleware.rate_limit_v2")

_ENDPOINT_LIMITS: Dict[str, Tuple[int, int]] = {
    "/api/v1/auth/login":    (10,  60),
    "/api/v1/auth/register": (5,   3600),
    "/api/v1/auth/refresh":  (20,  60),
    "/api/v1/signals":       (120, 60),
    "/api/v1/trades":        (120, 60),
    "/api/v1/risk/assess":   (30,  60),
    "/billing/webhook":      (200, 60),
}
_DEFAULT_LIMIT  = 60
_DEFAULT_WINDOW = 60
_MAX_TRACKED    = 100_000


def _get_endpoint_limit(path: str) -> Tuple[int, int]:
    for prefix, (lim, win) in _ENDPOINT_LIMITS.items():
        if path.startswith(prefix):
            return lim, win
    return _DEFAULT_LIMIT, _DEFAULT_WINDOW


class _SlidingWindow:
    def __init__(self, max_keys: int = _MAX_TRACKED):
        self._windows:  Dict[str, Deque[float]] = {}
        self._max_keys = max_keys

    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        if key not in self._windows:
            if len(self._windows) >= self._max_keys:
                try:
                    del self._windows[next(iter(self._windows))]
                except StopIteration:
                    pass
            self._windows[key] = deque()
        dq = self._windows[key]
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True

    def reset_at(self, key: str, window: int) -> float:
        dq = self._windows.get(key)
        if not dq:
            return time.time()
        return time.time() + (window - (time.monotonic() - dq[0]))

    def cleanup(self, window: int = 3600) -> int:
        now   = time.monotonic()
        stale = [k for k, dq in self._windows.items() if not dq or dq[-1] < now - window]
        for k in stale:
            del self._windows[k]
        return len(stale)


_ip_window   = _SlidingWindow()
_user_window = _SlidingWindow()


class RateLimitMiddlewareV2:
    def __init__(self, app, default_limit: int = _DEFAULT_LIMIT, default_window: int = _DEFAULT_WINDOW):
        self.app = app
        self.default_limit  = default_limit
        self.default_window = default_window

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        path    = request.url.path
        limit, window = _get_endpoint_limit(path)
        from .security_hardened import get_real_ip
        ip = get_real_ip(request)
        ip_key = f"ip:{ip}:{path.split('/')[3] if path.count('/') >= 3 else 'root'}"
        if not _ip_window.is_allowed(ip_key, limit, window):
            reset = _ip_window.reset_at(ip_key, window)
            log.warning("IP rate limited ip=%s path=%s", ip, path)
            return await self._rate_limited(scope, receive, send, reset, EC.RATE_LIMITED_IP)
        user_id = _extract_user_id_soft(request)
        if user_id:
            user_key = f"user:{user_id}:{path.split('/')[3] if path.count('/') >= 3 else 'root'}"
            if not _user_window.is_allowed(user_key, max(limit * 2, 200), window):
                reset = _user_window.reset_at(user_key, window)
                log.warning("User rate limited user=%s path=%s", user_id, path)
                return await self._rate_limited(scope, receive, send, reset, EC.RATE_LIMITED_USER)
        await self.app(scope, receive, send)

    async def _rate_limited(self, scope, receive, send, reset: float, code: str) -> None:
        retry_after = max(1, int(reset - time.time()))
        err  = api_error(code)
        resp = JSONResponse(err.to_response(), status_code=429, headers={"Retry-After": str(retry_after), "X-RateLimit-Reset": str(int(reset)), "X-RateLimit-Remaining": "0"})
        await resp(scope, receive, send)


def _extract_user_id_soft(request: Request) -> Optional[str]:
    try:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token  = auth[7:]
        parts  = token.split(".")
        if len(parts) != 3:
            return None
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        return str(payload.get("sub", ""))
    except Exception:
        return None


async def start_cleanup_v2() -> None:
    async def _loop() -> None:
        while True:
            await asyncio.sleep(300)
            n1 = _ip_window.cleanup()
            n2 = _user_window.cleanup()
            if n1 or n2:
                log.debug("RateLimit cleanup: ip=%d user=%d evicted", n1, n2)
    t = asyncio.create_task(_loop(), name="rate_limit_v2:cleanup")
    t.add_done_callback(lambda t: log.error("cleanup died: %s", t.exception()) if not t.cancelled() and t.exception() else None)
