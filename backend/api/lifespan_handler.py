"""
backend/api/lifespan_handler.py
FastAPI Application Lifespan Events
Startup and shutdown event handlers
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app) -> AsyncGenerator:
    """
    FastAPI lifespan context manager
    Handles startup and shutdown events
    
    Usage in main.py:
        from fastapi import FastAPI
        from backend.api.lifespan_handler import lifespan
        
        app = FastAPI(lifespan=lifespan)
    """
    
    # ============================================================================
    # STARTUP EVENTS
    # ============================================================================
    
    logger.info("╔════════════════════════════════════════════════════════════╗")
    logger.info("║         Galaxy Vast AI Trading Platform - STARTING         ║")
    logger.info("╚════════════════════════════════════════════════════════════╝")
    
    try:
        # 1. Initialize Database
        logger.info("[startup] Initializing database...")
        try:
            from backend.database.session import init_db
            init_db()
            logger.info("[startup] ✅ Database initialized")
        except Exception as e:
            logger.error("[startup] ❌ Database init failed: %s", e)
            raise
        
        # 2. Initialize Redis Cache
        logger.info("[startup] Initializing Redis cache...")
        try:
            import redis
            redis_client = redis.Redis(
                host='localhost',
                port=6379,
                db=0,
                decode_responses=True
            )
            redis_client.ping()
            app.state.redis = redis_client
            logger.info("[startup] ✅ Redis cache initialized")
        except Exception as e:
            logger.warning("[startup] ⚠️ Redis not available (optional): %s", e)
            app.state.redis = None
        
        # 3. Initialize MT5 Connector
        logger.info("[startup] Initializing MT5 connector...")
        try:
            from backend.mt5_connector.connector import MT5Connector
            mt5 = MT5Connector()
            await mt5.connect()
            app.state.mt5 = mt5
            logger.info("[startup] ✅ MT5 connector initialized")
        except Exception as e:
            logger.error("[startup] ❌ MT5 initialization failed: %s", e)
            # Don't raise - allow app to start without MT5
            app.state.mt5 = None
        
        # 4. Initialize Telegram Bot
        logger.info("[startup] Initializing Telegram bot...")
        try:
            from backend.telegram.bot import TelegramBot
            telegram = TelegramBot()
            app.state.telegram = telegram
            logger.info("[startup] ✅ Telegram bot initialized")
        except Exception as e:
            logger.error("[startup] ❌ Telegram initialization failed: %s", e)
            app.state.telegram = None
        
        # 5. Load License Validator
        logger.info("[startup] Loading license validator...")
        try:
            from backend.license.checksum_validator import get_license_validator
            license_validator = get_license_validator()
            app.state.license_validator = license_validator
            logger.info("[startup] ✅ License validator loaded")
        except Exception as e:
            logger.error("[startup] ❌ License validator failed: %s", e)
            app.state.license_validator = None
        
        # 6. Verify Production Hardening
        logger.info("[startup] Verifying production hardening...")
        try:
            from backend.core.production_hardening import ProductionHardening
            hardening = ProductionHardening()
            hardening.run_all_checks()
            
            for warning in hardening.warnings:
                logger.warning("[startup] ⚠️ %s", warning)
            
            for error in hardening.errors:
                logger.error("[startup] ❌ %s", error)
            
            if hardening.is_ready:
                logger.info("[startup] ✅ Production hardening checks passed")
            else:
                logger.error("[startup] ❌ Production hardening checks FAILED")
                # In production, we might want to fail startup
        
        except Exception as e:
            logger.error("[startup] ❌ Hardening check failed: %s", e)
        
        # 7. Log Startup Summary
        logger.info("╔════════════════════════════════════════════════════════════╗")
        logger.info("║              ✅ APPLICATION STARTUP COMPLETE               ║")
        logger.info("║                                                            ║")
        logger.info("║  Database:    %s", "✅ Ready" if hasattr(app.state, 'db') else "⚠️ Optional")
        logger.info("║  Redis:       %s", "✅ Ready" if app.state.redis else "⚠️ Optional")
        logger.info("║  MT5:         %s", "✅ Connected" if app.state.mt5 else "⚠️ Failed")
        logger.info("║  Telegram:    %s", "✅ Ready" if app.state.telegram else "⚠️ Failed")
        logger.info("║  License:     %s", "✅ Ready" if app.state.license_validator else "⚠️ Failed")
        logger.info("║                                                            ║")
        logger.info("║  Status: READY FOR REQUESTS                              ║")
        logger.info("╚════════════════════════════════════════════════════════════╝")
    
    except Exception as e:
        logger.critical("[startup] ❌ Critical startup error: %s", e)
        logger.critical("[startup] Application cannot start safely")
        raise
    
    # ============================================================================
    # YIELD - Application Running
    # ============================================================================
    
    yield
    
    # ============================================================================
    # SHUTDOWN EVENTS
    # ============================================================================
    
    logger.info("╔════════════════════════════════════════════════════════════╗")
    logger.info("║          Galaxy Vast AI Trading Platform - SHUTTING DOWN   ║")
    logger.info("╚════════════════════════════════════════════════════════════╝")
    
    # 1. Close MT5 Connection
    if hasattr(app.state, 'mt5') and app.state.mt5:
        try:
            logger.info("[shutdown] Closing MT5 connection...")
            await app.state.mt5.disconnect()
            logger.info("[shutdown] ✅ MT5 connection closed")
        except Exception as e:
            logger.error("[shutdown] ❌ MT5 disconnect error: %s", e)
    
    # 2. Stop Telegram Bot
    if hasattr(app.state, 'telegram') and app.state.telegram:
        try:
            logger.info("[shutdown] Stopping Telegram bot...")
            # Stop polling if running
            if hasattr(app.state.telegram, 'stop_polling'):
                await app.state.telegram.stop_polling()
            logger.info("[shutdown] ✅ Telegram bot stopped")
        except Exception as e:
            logger.error("[shutdown] ❌ Telegram stop error: %s", e)
    
    # 3. Close Database
    try:
        logger.info("[shutdown] Closing database...")
        from backend.database.session import close_db
        close_db()
        logger.info("[shutdown] ✅ Database closed")
    except Exception as e:
        logger.error("[shutdown] ❌ Database close error: %s", e)
    
    # 4. Close Redis
    if hasattr(app.state, 'redis') and app.state.redis:
        try:
            logger.info("[shutdown] Closing Redis...")
            app.state.redis.close()
            logger.info("[shutdown] ✅ Redis closed")
        except Exception as e:
            logger.error("[shutdown] ❌ Redis close error: %s", e)
    
    logger.info("╔════════════════════════════════════════════════════════════╗")
    logger.info("║              ✅ APPLICATION SHUTDOWN COMPLETE              ║")
    logger.info("╚════════════════════════════════════════════════════════════╝")
