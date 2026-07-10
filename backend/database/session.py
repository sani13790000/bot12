"""
backend/database/session.py
SQLAlchemy Database Configuration
Session factory, engine, and dependency injection
"""

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import os

from backend.database.models import Base

logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://bot12:bot12pass@localhost:5432/bot12"
)

# Create engine with appropriate pool settings
if "sqlite" in DATABASE_URL:
    # For SQLite (testing)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    # For PostgreSQL (production)
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connection before using
        echo=False,
    )

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db() -> None:
    """Initialize database - create all tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("[database] Database initialized - all tables created")
    except Exception as exc:
        logger.error("[database] Failed to initialize database: %s", exc)
        raise


def get_db() -> Session:
    """
    Dependency for FastAPI routes to get database session.
    
    Usage:
        @router.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_db_async() -> Session:
    """Async version of get_db for async routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def close_db() -> None:
    """Close database connection"""
    engine.dispose()
    logger.info("[database] Database connection closed")
