"""
backend/core/interfaces.py
Galaxy Vast AI Trading Interfaces (repaired)
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Protocol

class SignalProvider(Protocol):
    async def get_signal(self, symbol: str) -> dict[str, Any]: ...

class RiskGate(Protocol):
    def check(self, trade: dict[str, Any]) -> bool: ...

class OrderExecutor(Protocol):
    async def execute(self, order: dict[str, Any]) -> dict[str, Any]: ...

class BaseService(ABC):
    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
    @abstractmethod
    async def health_check(self) -> dict[str, Any]: ...

__all__ = ["SignalProvider", "RiskGate", "OrderExecutor", "BaseService"]
