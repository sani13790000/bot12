"""
backend/database/models.py
SQLAlchemy ORM Models - User, Position, Trade, Alert
Production-ready with proper relationships and constraints
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class User(Base):
    """User account model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    positions = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.username}>"


class PositionStatus(str, enum.Enum):
    """Position status enum"""
    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"


class Position(Base):
    """Open position model"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ticket = Column(Integer, unique=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    position_type = Column(String(10), nullable=False)  # buy/sell
    volume = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    profit = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    status = Column(String(20), default=PositionStatus.OPEN)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime)
    notes = Column(Text)
    
    # Relationships
    user = relationship("User", back_populates="positions")
    trades = relationship("Trade", back_populates="position", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Position {self.symbol} {self.position_type}>"


class TradeStatus(str, enum.Enum):
    """Trade status enum"""
    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"
    CANCELLED = "cancelled"


class Trade(Base):
    """Trade history model"""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"))
    symbol = Column(String(20), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float)
    volume = Column(Float, nullable=False)
    profit_loss = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    status = Column(String(20), default=TradeStatus.OPEN)
    entry_time = Column(DateTime, default=datetime.utcnow)
    exit_time = Column(DateTime)
    strategy = Column(String(100))
    analysis = Column(Text)
    notes = Column(Text)
    
    # Relationships
    user = relationship("User", back_populates="trades")
    position = relationship("Position", back_populates="trades")
    
    def __repr__(self):
        return f"<Trade {self.symbol} {self.status}>"


class AlertLevel(str, enum.Enum):
    """Alert severity level"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, enum.Enum):
    """Alert type enum"""
    TRADE = "trade"
    RISK = "risk"
    SYSTEM = "system"
    TELEGRAM = "telegram"


class Alert(Base):
    """Alert/notification model"""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    alert_type = Column(String(20), nullable=False)
    level = Column(String(20), default=AlertLevel.INFO)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    sent_via_telegram = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="alerts")
    
    def __repr__(self):
        return f"<Alert {self.alert_type} {self.level}>"
