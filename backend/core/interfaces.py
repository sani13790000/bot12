"""
backend/core/interfaces.py
Galaxy Vast AI Trading Platform -- Core Interfaces
"""
from __future__ import annotations

import abc
from typing import Any, Optional


class IAnalysisEngine(abc.ABC):
    """Abstract base class for all analysis engines."""

    @abc.abstractmethod
    async def analyze(self, symbol: str, timeframe: str, bars: int = 100) -> dict:
        """Perform market analysis and return structured results."""
        ...

    @abc.abstractmethod
    def name(self) -> str:
        ...


class IAgent(abc.ABC):
    """Abstract base class for all trading agents."""

    @property
    @abc.abstractmethod
    def agent_id(self) -> str:
        ...

    @abc.abstractmethod
    async def vote(self, context: dict) -> dict:
        ...


class IRiskManager(abc.ABC):
    """Abstract base class for risk management."""

    @abc.abstractmethod
    def check(self, order: dict) -> tuple[bool, str]:
        ...

    @abc.abstractmethod
    def current_exposure(self) -> float:
        ...


class INotifier(abc.ABC):
    """Abstract base class for notification channels."""

    @abc.abstractmethod
    async def send(self, message: str, level: str = "info") -> bool:
        ...
