"""
backend/core/interfaces.py
Galaxy Vast AI Trading Platform — Enterprise Interfaces (SOLID/DI/Clean Architecture)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IDataProvider(ABC):
    @abstractmethod
    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[Dict]:
        ...

    @abstractmethod
    async def get_tick(self, symbol: str) -> Dict[str, Any]:
        ...


class ISignalProvider(ABC):
    @abstractmethod
    async def get_signal(self, symbol: str) -> Dict[str, Any]:
        ...


class IRiskGate(ABC):
    @abstractmethod
    async def check(self, trade: Dict[str, Any]) -> bool:
        ...


class ITradeExecutor(ABC):
    @abstractmethod
    async def execute(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def close(self, trade_id: str) -> bool:
        ...


class INotifier(ABC):
    @abstractmethod
    async def send(self, message: str, level: str = 'INFO') -> None:
        ...


class IMetricsCollector(ABC):
    @abstractmethod
    def increment(self, metric: str, value: float = 1.0) -> None:
        ...

    @abstractmethod
    def gauge(self, metric: str, value: float) -> None:
        ...


class ICache(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...
