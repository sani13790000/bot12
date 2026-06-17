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

from ..core.config import settings
from ..core.logger import get_logger
from ..core.exceptions import MT5TradingError

logger = get_logger("api")


# =====================================================
# Lifespan (startup/shutdown)
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """مدیریت چرخه حیات برنامه"""
    # Startup
    logger.info(f"سرور {settings.APP_NAME} v{settings.APP_VERSION} راه‌اندازی شد")
    logger.info(f"محیط: {settings.ENVIRONMENT}")

    yield

    # Shutdown
    logger.info("سرور متوقف شد")


# =====================================================
# ایجاد اپلیکیشن
# =====================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## اکوسیستم معامله‌گری MT5

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


# =====================================================
# Exception Handlers
# =====================================================

@app.exception_handler(MT5TradingError)
async def mt5_trading_error_handler(request: Request, exc: MT5TradingError):
    """هندلر خطاهای سفارشی"""
    logger.error(f"خطای سیستم: {exc.message}", extra={"error_code": exc.error_code})
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=exc.to_dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """هندلر خطاهای عمومی"""
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
        # تست اتصال دیتابیس
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
        "debug": settings.DEBUG
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
