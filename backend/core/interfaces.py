"""
backend/core/interfaces.py
Galaxy Vast AI Trading Platform — Enterprise Interfaces

Abstract base classes and protocols for all major components.
Enables dependency injection and clean separation of concerns.
"""
from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional


class IAgent(abc.ABC):
    """Abstract trading agent interface."""
    name: str
    weight: float = 1.0

    @abc.abstractmethod
    async def vote(self, context: Dict[str, Any]) -> Any:
        """Cast a vote given market context."""

    @abc.abstractmethod
    async def analyze(self, symbol: str, data: Dict) -> Dict[str, Any]:
        """Analyze market data and return signals."""


class IRiskManager(abc.ABC):
    """Abstract risk management interface."""

    @abc.abstractmethod
    async def check(self, signal: Dict) -> bool:
        """Return True if signal passes risk checks."""

    @abc.abstractmethod
    async def calculate_lot_size(self, symbol: str, risk_pct: float, balance: float) -> float:
        """Calculate position size based on risk percentage."""


class IExecutor(abc.ABC):
    """Abstract trade executor interface."""

    @abc.abstractmethod
    async def open_trade(self, signal: Dict) -> Dict:
        """Open a trade and return order result."""

    @abc.abstractmethod
    async def close_trade(self, trade_id: str) -> Dict:
        """Close an open trade."""

    @abc.abstractmethod
    async def get_open_trades(self) -> List[Dict]:
        """Return list of currently open trades."""


class IDataFeed(abc.ABC):
    """Abstract market data feed interface."""

    @abc.abstractmethod
    async def get_tick(self, symbol: str) -> Dict[str, float]:
        """Get latest tick data for symbol."""

    @abc.abstractmethod
    async def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> List[Dict]:
        """Get OHLCV candles for symbol."""


class INotifier(abc.ABC):
    """Abstract notification interface."""

    @abc.abstractmethod
    async def send(self, message: str, level: str = "INFO", **kwargs) -> bool:
        """Send a notification. Returns True on success."""


class ILicenseValidator(abc.ABC):
    """Abstract license validation interface."""

    @abc.abstractmethod
    def is_valid(self) -> bool:
        """Return True if license is currently valid."""

    @abc.abstractmethod
    def get_plan(self) -> str:
        """Return current plan name."""

    @abc.abstractmethod
    def has_feature(self, feature: str) -> bool:
        """Return True if feature is included in current plan."""
