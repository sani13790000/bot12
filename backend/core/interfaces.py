"""
backend/core/interfaces.py
Galaxy Vast AI Trading Platform — Enterprise Interfaces (SOLID/DI/Clean Architecture)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ISignalGenerator(Protocol):
    """Protocol for signal generators."""

    async def generate(self, market_data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...


@runtime_checkable
class IRiskGate(Protocol):
    """Protocol for risk gates."""

    async def check(self, signal: Dict[str, Any]) -> bool: ...


@runtime_checkable
class IExecutionEngine(Protocol):
    """Protocol for execution engines."""

    async def execute(self, order: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class ILearningService(Protocol):
    """Protocol for learning/feedback services."""

    async def record(self, event: Any) -> None: ...


@runtime_checkable
class IMetricsCollector(Protocol):
    """Protocol for metrics collection."""

    def increment(self, name: str, value: float = 1.0) -> None: ...
    def gauge(self, name: str, value: float) -> None: ...
    def histogram(self, name: str, value: float) -> None: ...


@runtime_checkable
class ICache(Protocol):
    """Protocol for cache implementations."""

    async def get(self, key: str) -> Optional[Any]: ...
    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None: ...
    async def delete(self, key: str) -> None: ...
