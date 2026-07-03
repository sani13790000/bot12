"""
backend/core/interfaces.py
Galaxy Vast AI Trading Platform — Enterprise Interfaces (SOLID/DI/Clean Architecture)
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ISignalSource(Protocol):
    """Any component that produces trading signals."""
    async def get_signals(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class IRiskGate(Protocol):
    """Component that approves or rejects a trade proposal."""
    def approve(self, proposal: dict[str, Any]) -> bool: ...


@runtime_checkable
class IOrderExecutor(Protocol):
    """Low-level order placement."""
    async def place_order(self, order: dict[str, Any]) -> dict[str, Any]: ...
    async def cancel_order(self, order_id: str) -> bool: ...


class BaseAgent(ABC):
    """Abstract base for all Galaxy Vast AI agents."""
    name: str = "base"

    @abstractmethod
    async def analyze(self, market_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze market and return a vote dict."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if agent is healthy."""


class BaseRiskModule(ABC):
    """Base for all risk management modules."""

    @abstractmethod
    def evaluate(self, trade: dict[str, Any]) -> tuple[bool, str]:
        """Return (approved, reason)."""


__all__ = [
    "ISignalSource", "IRiskGate", "IOrderExecutor",
    "BaseAgent", "BaseRiskModule",
]
