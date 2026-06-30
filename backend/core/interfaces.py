"""
backend/core/interfaces.py
Galaxy Vast AI Trading Platform — Enterprise Interfaces (SOLID/DI/Clean Architecture)

Central location for abstract base classes and protocols used across modules.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol

from backend.core.enums import TradeDirection


class SignalGenerator(Protocol):
    """Protocol for any signal generation strategy."""

    async def generate(
        self,
        symbol: str,
        timeframe: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...


class RiskGate(Protocol):
    """Protocol for risk-management gates."""

    async def check(
        self,
        signal: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...


class ExecutionBroker(ABC):
    """Abstract base class for trade execution brokers."""

    @abstractmethod
    async def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def close_position(self, position_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_account_summary(self) -> Dict[str, Any]:
        raise NotImplementedError


class NotificationChannel(ABC):
    """Abstract base class for alert/notification channels."""

    @abstractmethod
    async def send(self, message: str, level: str = "INFO") -> bool:
        raise NotImplementedError
