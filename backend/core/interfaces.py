"""
backend/core/interfaces.py
Galaxy Vast AI Trading Platform — Enterprise Interfaces (SOLID/DI/Clean-Arch)
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)
__all__ = ["ISignalEngine", "IOrderExecutor", "IMarketDataProvider", "IRiskManager"]


class ISignalEngine(ABC):
    """Abstract signal generation interface."""
    @abstractmethod
    def generate_signals(self, symbol: str, timeframe: str) -> List[Dict[str, Any]]:
        ...


class IOrderExecutor(ABC):
    """Abstract order execution interface."""
    @abstractmethod
    def execute_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        ...
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...


class IMarketDataProvider(ABC):
    """Abstract market data interface."""
    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> List[Dict]:
        ...
    @abstractmethod
    def get_tick(self, symbol: str) -> Dict[str, float]:
        ...


class IRiskManager(ABC):
    """Abstract risk management interface."""
    @abstractmethod
    def check_risk(self, order: Dict[str, Any]) -> bool:
        ...
    @abstractmethod
    def get_position_size(self, symbol: str, risk_pct: float) -> float:
        ...
