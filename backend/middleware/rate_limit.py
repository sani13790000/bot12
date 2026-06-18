"""
F1 - Rate Limiting Middleware - Galaxy Vast AI Trading Platform
"""
from __future__ import annotations
import time, asyncio, hashlib, os, logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger('middleware.rate_limit')

RATE_LIMIT_RULES: list = [
    ('/api/v1/auth/login',    5,   60),
    ('/api/v1/auth/register', 3,   60),
    ('/api/v1/signals',       30,  60),
    ('/api/v1/agents',        20,  60),
    ('/api/v1/ai',            15,  60),
    ('/api/v1/backtest',      5,   60),
    ('/api/v1/research',      5,   60),
    ('/health',               60,  60),
    ('/',                     120, 60),
]

@dataclass
class _Window:
    timestamps: list = field(default_factory=list)

    async def is_allowed(self, max_req: int, window_sec: int):
        now = time.time()
        cutoff = now - window_sec
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        count = len(self.timestamps)
        if count < max_req:
            self.timestamps.append(now)
            return True, max_req - count - 1, int(now + window_sec)
        reset_at = int(self.timestamps[0] + window_sec) if self.timestamps else int(now + window_sec)
        return False, 0, reset_at

class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._windows: Dict[str, _Window] = defaultdict(_Window)
        self._lock = asyncio.Lock()

    def _key(self, ip: str, prefix: str) -> str:
        return hashlib.md5(f'{ip}:{prefix}'.encode()).hexdigest()

    async def check(self, ip: str, path: str):
        rule = next(((p, m, w) for p, m, w in RATE_LIMIT_RULES if path.startswith(p)), ('/', 120, 60))
        prefix, max_req, window_sec = rule
        async with self._lock:
            allowed, remaining, reset_at = await self._windows[self._key(ip, prefix)].is_allowed(max_req, window_sec)
        return allowed, max_req, remaining, reset_at

    async def start_cleanup(self) -> None:
        async def _run():
            while True:
                await asyncio.sleep(300)
                try:
                    now = time.time()
                    async with self._lock:
                        stale = [k for k, w in list(self._windows.items())
                                 if not w.timestamps or (now - w.timestamps[-1]) > 120]
                        for k in stale:
                            self._windows.pop(k, None)
                except Exception as e:
                    logger.debug(f'cleanup: {e}')
        asyncio.create_task(_run())

class RedisRateLimiter:
    def __init__(self, url: str) -> None:
        self._url = url
        self._client = None
        self.available = False

    async def connect(self) -> None:
        try:
            import redis.asyncio as aioredis
            self._client = await aioredis.from_url(
                self._url, encoding='utf-8', decode_responses=True,
                socket_connect_timeout=2, socket_timeout=1)
            await self._client.ping()
            self.available = True
            logger.info('RateLimit: Redis connected')
        except Exception as e:
            logger.warning(f'RateLimit: Redis unavailable ({e}) -- in-memory fallback')

    async def check(self, ip: str, path: str):
        rule = next(((p, m, w) for p, m, w in RATE_LIMIT_RULES if path.startswith(p)), ('/', 120, 60))
        prefix, max_req, window_sec = rule
        key = f'rl:{ip}:{prefix}'
        now = time.time()
        try:
            pipe = self._client.pipeline()
            pipe.zremrangebyscore(key, 0, now - window_sec)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_sec + 1)
            results = await pipe.execute()
            count = results[2]
            if count <= max_req:
                return True, max_req, max_req - count, int(now + window_sec)
            oldest = await self._client.zrange(key, 0, 0, withscores=True)
            reset_at = int(oldest[0][1] + window_sec) if oldest else int(now + window_sec)
            return False, max_req, 0, reset_at
        except Exception as e:
            logger.warning(f'Redis RL error: {e}')
            return True, max_req, max_req, int(now + window_sec)

_limiter: Optional[object] = None

async def _get_limiter():
    global _limiter
    if _limiter is None:
        url = os.getenv('REDIS_URL', '')
        if url:
            rl = RedisRateLimiter(url)
            await rl.connect()
            if rl.available:
                _limiter = rl
                return _limiter
        rl = InMemoryRateLimiter()
        await rl.start_cleanup()
        _limiter = rl
    return _limiter

def _client_ip(req: Request) -> str:
    for h in ('X-Forwarded-For', 'X-Real-IP'):
        v = req.headers.get(h, '')
        if v:
            return v.split(',')[0].strip()
    return req.client.host if req.client else 'unknown'

class RateLimitMiddleware(BaseHTTPMiddleware):
    BYPASS = {'/docs', '/redoc', '/openapi.json', '/favicon.ico'}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in self.BYPASS or path.startswith('/static'):
            return await call_next(request)
        ip = _client_ip(request)
        limiter = await _get_limiter()
        allowed, max_req, remaining, reset_at = await limiter.check(ip, path)
        if not allowed:
            logger.warning(f'RateLimit BLOCKED ip={ip} path={path}')
            retry = max(0, reset_at - int(time.time()))
            return JSONResponse(
                status_code=429,
                content={'success': False, 'error': {
                    'code': 'RATE_LIMIT_EXCEEDED',
                    'message': 'Too many requests. Please wait.',
                    'retry_after': retry,
                }},
                headers={
                    'X-RateLimit-Limit': str(max_req),
                    'X-RateLimit-Remaining': '0',
                    'X-RateLimit-Reset': str(reset_at),
                    'Retry-After': str(retry),
                }
            )
        response = await call_next(request)
        response.headers['X-RateLimit-Limit'] = str(max_req)
        response.headers['X-RateLimit-Remaining'] = str(remaining)
        response.headers['X-RateLimit-Reset'] = str(reset_at)
        return response
