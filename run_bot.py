#!/usr/bin/env python3
"""
run_bot.py - Bot12 Entry Point

شروع ربات با تمام agents و API server.
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


async def main():
    """Main entry point for bot12."""
    logger.info("="*70)
    logger.info("🚀 BOT12 - AI Trading Bot Starting")
    logger.info("="*70)

    try:
        # Load environment
        from dotenv import load_dotenv
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            logger.info("✅ Environment loaded from .env")
        else:
            logger.warning("⚠️  .env file not found, using system environment")

        # Initialize configuration
        from backend.core.config import settings
        logger.info(f"📊 Environment: {settings.ENVIRONMENT}")
        logger.info(f"🔑 API Prefix: {settings.API_PREFIX}")

        # Start MT5 connection (if available)
        try:
            from backend.mt5_gateway.agent import mt5_agent
            await mt5_agent.initialize()
            logger.info("✅ MT5 Gateway initialized")
        except Exception as e:
            logger.warning(f"⚠️  MT5 initialization failed: {e}")

        # Initialize agents
        logger.info("\n" + "="*70)
        logger.info("🤖 Initializing AI Agents")
        logger.info("="*70)

        agents_initialized = 0

        # AI Prediction Agent
        try:
            from backend.agents.ai_prediction_agent import AIPredictionAgent
            ai_agent = AIPredictionAgent()
            logger.info("✅ AI Prediction Agent initialized")
            agents_initialized += 1
        except Exception as e:
            logger.error(f"❌ AI Prediction Agent failed: {e}")

        # ML Agent
        try:
            from backend.agents.ml_agent import MLAgent
            ml_agent = MLAgent()
            logger.info("✅ ML Agent initialized")
            agents_initialized += 1
        except Exception as e:
            logger.error(f"❌ ML Agent failed: {e}")

        # Risk Agent
        try:
            from backend.agents.risk_agent import RiskAgent
            risk_agent = RiskAgent()
            logger.info("✅ Risk Management Agent initialized")
            agents_initialized += 1
        except Exception as e:
            logger.error(f"❌ Risk Agent failed: {e}")

        # SMC Agent
        try:
            from backend.agents.smc_agent import SMCAgent
            smc_agent = SMCAgent()
            logger.info("✅ SMC Agent initialized")
            agents_initialized += 1
        except Exception as e:
            logger.error(f"❌ SMC Agent failed: {e}")

        # Execution Agent
        try:
            from backend.agents.execution_agent import ExecutionAgent
            exec_agent = ExecutionAgent()
            logger.info("✅ Execution Agent initialized")
            agents_initialized += 1
        except Exception as e:
            logger.error(f"❌ Execution Agent failed: {e}")

        # Voting Engine
        try:
            from backend.agents.voting_engine import VotingEngine
            voting_engine = VotingEngine()
            logger.info("✅ Voting Engine initialized")
        except Exception as e:
            logger.error(f"❌ Voting Engine failed: {e}")

        logger.info(f"\n✅ {agents_initialized}/5 agents initialized")

        # Start FastAPI server
        logger.info("\n" + "="*70)
        logger.info("🚀 Starting FastAPI Server")
        logger.info("="*70)

        import uvicorn

        # Configuration
        host = os.getenv("API_HOST", "0.0.0.0")
        port = int(os.getenv("API_PORT", "8000"))
        reload = settings.DEBUG
        log_level = os.getenv("LOG_LEVEL", "info").lower()

        logger.info(f"📡 API Server: http://{host}:{port}")
        logger.info(f"📚 Docs: http://{host}:{port}/docs")
        logger.info(f"🔧 ReDoc: http://{host}:{port}/redoc")

        # Run server
        config = uvicorn.Config(
            app="backend.api.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level=log_level,
            access_log=True,
        )
        server = uvicorn.Server(config)
        await server.serve()

    except KeyboardInterrupt:
        logger.info("\n⏹️  Bot12 stopping...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    logger.info("Python version: %s", sys.version)
    logger.info("Project root: %s", PROJECT_ROOT)

    # Run async main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n✅ Bot12 stopped")
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)
        sys.exit(1)
