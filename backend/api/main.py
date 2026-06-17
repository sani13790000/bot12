"""
API اصلی - FastAPI

این فایل اصلی‌ترین نقاط ورود REST API را تعریف می‌کند.

نویسنده: MT5 Trading Team
تاریخ: 2026-06-12
"""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
import uuid
from typing import Dict, Any
from collections import defaultdict
import threading

from ..core.config import settings
from ..core.logger import get_logger
from ..core.exceptions import MT5TradingError

logger = get_logger("api")


# =====================================================
# Rate Limiter ساده در حافظه
# =====================================================

class InMemoryRateLimiter:
    """
    Rate Limiter ساده مبتنی بر IP + Sliding Window

    در production از Redis استفاده کنید.
    این implementation برای single-instance مناسب است.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._store: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, identifier: str) -> bool:
        """بررسی اینکه آیا درخواست مجاز است"""
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            # حذف درخواست‌های خارج از window
            self._store[identifier] = [
                ts for ts in self._store[identifier]
                if ts > window_start
            ]
            # بررسی تعداد درخواست‌ها
            if len(self._store[identifier]) >= self.max_requests:
                return False
            # ثبت درخواست جدید
            self._store[identifier].append(now)
            return True

    def get_remaining(self, identifier: str) -> int:
        """تعداد درخواست‌های باقی‌مانده"""
        now = time.time()
        window_start = now - self.window_seconds
        with self._lock:
            count = len([
                ts for ts in self._store.get(identifier, [])
                if ts > window_start
            ])
            return max(0, self.max_requests - count)

    def cleanup(self):
        """پاکسازی ورودی‌های قدیمی"""
        now = time.time()
        window_start = now - self.window_seconds
        with self._lock:
            keys_to_delete = []
            for key, timestamps in self._store.items():
                cleaned = [ts for ts in timestamps if ts > window_start]
                if cleaned:
                    self._store[key] = cleaned
                else:
                    keys_to_delete.append(key)
            for key in keys_to_delete:
                del self._store[key]


# instance سراسری
rate_limiter = InMemoryRateLimiter(
    max_requests=100,
    window_seconds=60
)

# Rate limiter سخت‌گیرانه‌تر برای auth endpoints
auth_rate_limiter = InMemoryRateLimiter(
    max_requests=10,
    window_seconds=60
)


# =====================================================
# Lifespan (startup/shutdown)
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """مدیریت چرخه حیات برنامه"""
    # Startup
    logger.info(f"سرور {settings.APP_NAME} v{settings.APP_VERSION} راه‌اندازی شد")
    logger.info(f"محیط: {settings.ENVIRONMENT}")
    logger.info(f"Rate Limiting فعال: {rate_limiter.max_requests} req/{rate_limiter.window_seconds}s")

    yield

    # Shutdown
    rate_limiter.cleanup()
    logger.info("سرور متوقف شد")


# =====================================================
# ایجاد اپلیکیشن
# =====================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## اکوسیستم معاملاتی MT5

این API برای تحلیل بازار و تولید سیگنال‌های معاملاتی طراحی شده است.

### بخش‌های اصلی:
- **تحلیل**: Smart Money, Price Action, Decision Engine
- **معاملات**: مشاهده و مدیریت معاملات
- **سیگنال‌ها**: دریافت سیگنال‌های معاملاتی
- **گزارش‌ها**: آمار و عملکرد
    """,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)


# =====================================================
# Middleware
# =====================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# زمان پردازش
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """افزودن هدر زمان پردازش"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}"
    return response


# Request ID
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """افزودن شناسه درخواست برای ردیابی"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Rate Limiting Middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """
    Rate Limiting middleware — جلوگیری از سوءاستفاده

    - عمومی: ۱۰۰ req/min per IP
    - auth endpoints: ۱۰ req/min per IP (سخت‌گیرانه‌تر)
    - health endpoints: بدون محدودیت
    """
    path = request.url.path

    # health checks از rate limiting معاف هستند
    if path in ["/health", "/health/details", "/"]:
        return await call_next(request)

    # شناسه client = IP اصلی (با X-Forwarded-For در production)
    client_ip = request.headers.get("X-Forwarded-For", "")
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"
    # فقط IP اول را در نظر می‌گیریم
    client_ip = client_ip.split(",")[0].strip()

    # auth endpoints محدودیت سخت‌تری دارند
    if "/auth/" in path or "/license/validate" in path:
        limiter = auth_rate_limiter
        limit_type = "auth"
    else:
        limiter = rate_limiter
        limit_type = "general"

    if not limiter.is_allowed(client_ip):
        remaining = limiter.get_remaining(client_ip)
        logger.warning(
            f"Rate limit exceeded: {client_ip} → {path} "
            f"(type={limit_type}, remaining={remaining})"
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "success": False,
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "تعداد درخواست‌ها از حد مجاز فراتر رفته. لطفاً کمی صبر کنید.",
                    "retry_after": limiter.window_seconds,
                }
            },
            headers={
                "Retry-After": str(limiter.window_seconds),
                "X-RateLimit-Limit": str(limiter.max_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + limiter.window_seconds),
            }
        )

    response = await call_next(request)

    # افزودن هدرهای Rate Limit به هر پاسخ
    remaining = limiter.get_remaining(client_ip)
    response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(time.time()) + limiter.window_seconds)

    return response


# =====================================================
# Exception Handlers
# =====================================================

@app.exception_handler(MT5TradingError)
async def mt5_trading_error_handler(request: Request, exc: MT5TradingError):
    """مدیریت خطاهای سفارشی"""
    logger.error(f"خطای سیستم: {exc.message}", extra={"error_code": exc.error_code})
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=exc.to_dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """مدیریت خطاهای عمومی"""
    logger.exception(f"خطای غیرمنتظره: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "خطای داخلی سرور"
            }
        }
    )


# =====================================================
# Routes
# =====================================================

@app.get("/", tags=["Root"])
async def root():
    """نقطه ورود اصلی"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "docs": "/docs" if settings.DEBUG else "disabled"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    بررسی سلامت سیستم

    این endpoint برای health check و load balancer استفاده می‌شود.
    """
    from ..database import db

    database_status = "healthy"
    try:
        await db.count("user_profiles", use_admin=True)
    except Exception as e:
        database_status = f"error: {str(e)[:50]}"

    return {
        "status": "healthy" if database_status == "healthy" else "degraded",
        "version": settings.APP_VERSION,
        "timestamp": time.time(),
        "components": {
            "api": "healthy",
            "database": database_status
        },
        "environment": settings.ENVIRONMENT
    }


@app.get("/health/details", tags=["Health"])
async def health_detailed():
    """
    جزئیات سلامت سیستم

    برای مانیتورینگ و دیباگ.
    """
    from ..database import db
    import sys

    details = {
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "python_version": sys.version,
        "components": {}
    }

    # دیتابیس
    try:
        count = await db.count("user_profiles", use_admin=True)
        details["components"]["database"] = {
            "status": "healthy",
            "users_count": count
        }
    except Exception as e:
        details["components"]["database"] = {
            "status": "error",
            "error": str(e)[:100]
        }

    # پردازش
    details["components"]["api"] = {
        "status": "healthy",
        "debug": settings.DEBUG,
        "rate_limiter": {
            "max_requests": rate_limiter.max_requests,
            "window_seconds": rate_limiter.window_seconds,
        }
    }

    return details


# =====================================================
# Import Routers
# =====================================================

from .routes import auth, users, analysis, signals, trades, reports
from .routes import decision, license, trade_report, dashboard

app.include_router(
    auth.router,
    prefix=f"{settings.API_PREFIX}/auth",
    tags=["احراز هویت"]
)

app.include_router(
    users.router,
    prefix=f"{settings.API_PREFIX}/users",
    tags=["کاربران"]
)

app.include_router(
    analysis.router,
    prefix=f"{settings.API_PREFIX}/analysis",
    tags=["تحلیل"]
)

app.include_router(
    decision.router,
    prefix=f"{settings.API_PREFIX}/decision",
    tags=["تصمیم‌گیری"]
)

app.include_router(
    signals.router,
    prefix=f"{settings.API_PREFIX}/signals",
    tags=["سیگنال‌ها"]
)

app.include_router(
    trades.router,
    prefix=f"{settings.API_PREFIX}/trades",
    tags=["معاملات"]
)

app.include_router(
    trade_report.router,
    prefix=f"{settings.API_PREFIX}/trade-report",
    tags=["گزارش معاملات"]
)

app.include_router(
    reports.router,
    prefix=f"{settings.API_PREFIX}/reports",
    tags=["گزارش‌ها"]
)

app.include_router(
    license.router,
    prefix=f"{settings.API_PREFIX}/license",
    tags=["لایسنس"]
)

app.include_router(
    dashboard.router,
    prefix=f"{settings.API_PREFIX}/dashboard",
    tags=["داشبورد"]
)
