"""
Galaxy Vast AI Trading Platform
FastAPI Application Entry Point

F4 FIX:
  - Rate limiting middleware (RateLimitMiddleware)
  - Sentry monitoring (SENTRY_DSN env var)
  - /health endpoint with DB + circuit breaker status
  - Structured startup logging

C8 FIX:
  - CORS origins from ALLOWED_ORIGINS env var
  - No more allow_origins=['*']
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _get_allowed_origins() -> list:
    raw = os.getenv('ALLOWED_ORIGINS', '')
    if raw.strip():
        origins = [o.strip() for o in raw.split(',') if o.strip()]
        logger.info(f'CORS: {len(origins)} origin(s) from environment')
        return origins
    dev_origins = [
        'http://localhost:3000',
        'http://localhost:5173',
        'http://localhost:8080',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:5173',
    ]
    logger.warning('CORS: ALLOWED_ORIGINS not set -- allowing localhost only.')
    return dev_origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Galaxy Vast AI Trading Platform -- Starting...')

    # F4: Sentry initialization
    sentry_dsn = os.getenv('SENTRY_DSN', '')
    if sentry_dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=sentry_dsn,
                traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
                profiles_sample_rate=float(os.getenv('SENTRY_PROFILES_SAMPLE_RATE', '0.0')),
                environment=os.getenv('ENVIRONMENT', 'production'),
            )
            logger.info('Sentry monitoring initialized')
        except Exception as exc:
            logger.warning(f'Sentry init failed: {exc}')

    # F4: initialize rate limiter singleton
    try:
        from ..middleware.rate_limit import _get_limiter
        await _get_limiter()
        logger.info('RateLimit limiter initialized')
    except Exception as exc:
        logger.warning(f'Rate limiter init failed: {exc}')

    logger.info('Galaxy Vast AI Trading Platform -- Ready')
    yield
    logger.info('Galaxy Vast AI Trading Platform -- Shutdown complete.')


app = FastAPI(
    title='Galaxy Vast AI Trading Platform',
    description=(
        'Institutional-Grade AI Trading Ecosystem\n\n'
        'Features: SMC Analysis, AI Prediction, Multi-Agent Voting, '
        'Portfolio Risk, Self-Learning, Analytics, '
        'Institutional Backtest Engine, Market Replay, Walk-Forward'
    ),
    version='2.1.0-F',
    lifespan=lifespan,
    docs_url='/docs',
    redoc_url='/redoc',
    contact={'name': 'Galaxy Vast Support', 'url': 'https://t.me/GalaxyVast_Support'},
    license_info={'name': 'Galaxy Vast Enterprise License'},
)

# C8 FIX: CORS whitelist from environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allow_headers=['Authorization', 'Content-Type', 'X-License-Key', 'X-Request-ID'],
)

# F4: Rate limiting middleware
try:
    from ..middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)
    logger.info('RateLimit middleware registered')
except Exception as exc:
    logger.warning(f'RateLimit middleware registration failed: {exc}')


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception('Unhandled exception', extra={'path': request.url.path})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            'success': False,
            'error': {
                'code': 'INTERNAL_SERVER_ERROR',
                'message': 'Internal server error. Technical team has been notified.',
                'path': request.url.path,
            }
        }
    )


def _register_routers():
    registered = []
    failed = []
    router_map = {
        'signals':       ('backend.api.routes.signals',       None),
        'trades':        ('backend.api.routes.trades',        None),
        'risk':          ('backend.api.routes.risk',          None),
        'agents':        ('backend.api.routes.agents',        None),
        'intelligence':  ('backend.api.routes.intelligence',  None),
        'self_learning': ('backend.api.routes.self_learning', None),
        'analytics':     ('backend.api.routes.analytics',     None),
        'research':      ('backend.api.routes.research',      None),
        'ai_prediction': ('backend.api.routes.ai_prediction', None),
        'backtest':      ('backend.api.routes.backtest_engine', None),
    }
    for name, (module_path, _) in router_map.items():
        try:
            import importlib
            mod = importlib.import_module(module_path)
            app.include_router(mod.router)
            registered.append(name)
        except ImportError as e:
            failed.append(f'{name}: {e}')
        except Exception as e:
            failed.append(f'{name}: {e}')
    if registered:
        logger.info(f'Routers registered: {registered}')
    if failed:
        logger.warning(f'Routers failed: {failed}')

_register_routers()


@app.get('/', tags=['Health'])
async def root():
    return {
        'brand':   'Galaxy Vast AI Trading Platform',
        'version': '2.1.0-F',
        'status':  'online',
        'modules': [
            'signals', 'trades', 'risk_v2', 'multi_agent',
            'intelligence', 'self_learning', 'analytics',
            'research', 'ai_prediction', 'institutional_backtest',
        ],
    }


@app.get('/health', tags=['Health'])
async def health_check():
    try:
        from ..circuit_breaker import _BREAKERS
        circuits = {name: b.to_dict() for name, b in _BREAKERS.items()}
    except Exception:
        circuits = {}
    try:
        from ..database.connection_health import get_connection_status
        db_status = await get_connection_status()
    except Exception as exc:
        db_status = {'connected': False, 'status': f'error: {exc}'}

    overall = 'healthy' if db_status.get('connected') else 'degraded'
    return JSONResponse(
        status_code=200 if overall == 'healthy' else 503,
        content={
            'status': overall,
            'version': '2.1.0-F',
            'database': db_status,
            'circuits': circuits,
        }
    )
