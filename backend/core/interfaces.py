"""
backend/core/interfaces.py
Galaxy Vast AI Trading Platform — Enterprise Interfaces
Phase 7 — Abstract base classes and protocol definitions.
"""
from __future__ import annotations

import abc
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol


class ISignalProducer(abc.ABC):
    """Abstract base for all signal producers."""

    @abc.abstractmethod
    async def produce(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ...


class IRiskManager(abc.ABC):
    """Abstract base for risk managers."""

    @abc.abstractmethod
    async def check(self, signal: Dict[str, Any]) -> bool:
        ...

    @abc.abstractmethod
    async def get_position_size(self, signal: Dict[str, Any]) -> float:
        ...


class IOrderExecutor(abc.ABC):
    """Abstract base for order executors."""

    @abc.abstractmethod
    async def execute(self, order: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abc.abstractmethod
    async def cancel(self, order_id: str) -> bool:
        ...


class INotifier(abc.ABC):
    """Abstract base for notification providers."""

    @abc.abstractmethod
    async def send(self, message: str, level: str = "INFO", **kwargs: Any) -> bool:
        ...


class IDataFeed(Protocol):
    """Protocol for market data feeds."""

    async def subscribe(self, symbols: List[str]) -> None:
        ...

    def stream(self) -> AsyncIterator[Dict[str, Any]]:
        ...


class IHealthCheck(abc.ABC):
    """Abstract base for health checks."""

    @abc.abstractmethod
    async def check(self) -> Dict[str, Any]:
        ...

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...
