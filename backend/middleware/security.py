"""Security Middleware — Galaxy Vast AI
Fixes: CSP header added, query string SQLi check, log injection prevention
"""
from __future__ import annotations
import re, time, uuid
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.core.logger import get_logger

logger = get_logger("middleware.security")

_SQL = re.compile(
    r"(\bunion\b|\bselect\b|\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b"
    r"|\btruncate\b|\bexec\b|\bexecute\b|--|;\s*--|xp_|0x[0-9a-f]+"
    r"|\bcast\s*\(|\bconvert\s*\(|\bchar\s*\(|\bnchar\s*\()",
    re.IGNORECASE,
)
_XSS = re.compile(
    r"(<script|javascript:|vbscript:|onload=|onerror=|onclick=|<iframe|<object|<embed)",
    re.IGNORECASE,
)
_NL = re.compile(r"[\r\n]")


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = str(uuid.uuid4())
        start = time.monotonic()
        request.state.request_id = rid
        ip = request.client.host if request.client else "unknown"

        # 1. SQL injection in query string (NEW)
        qs = request.url.query
        if qs and _SQL.search(qs):
            logger.warning("SQLi in query string id=%s ip=%s", rid, ip)
            return JSONResponse(status_code=400, content={"detail": "Invalid request"})

        # 2. SQL injection + XSS in body
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = (await request.body()).decode("utf-8", errors="replace")
                if _SQL.search(body):
                    logger.warning("SQLi in body id=%s ip=%s", rid, ip)
                    return JSONResponse(status_code=400, content={"detail": "Invalid request"})
                if _XSS.search(body):
                    logger.warning("XSS in body id=%s ip=%s", rid, ip)
                    return JSONResponse(status_code=400, content={"detail": "Invalid request"})
            except Exception:
                pass

        response: Response = await call_next(request)
        ms = round((time.monotonic() - start) * 1000, 2)

        # 3. Security headers
        response.headers.update({
            "X-Request-ID": rid,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            # CSP — was missing, now added
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self' wss:; "
                "frame-ancestors 'none'"
            ),
        })

        # 4. Audit log (sanitized — no newlines)
        safe_path = _NL.sub("", str(request.url.path))
        logger.info(
            "REQ id=%s method=%s path=%s status=%s ms=%s ip=%s user=%s",
            rid, request.method, safe_path, response.status_code, ms, ip,
            getattr(request.state, "user_id", None),
        )
        return response
