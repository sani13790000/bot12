"""
backend/core/interfaces.py
Galaxy Vast AI Trading Platform — Core Abstract Interfaces

All major components implement one of these protocols/ABCs so the
codebase remains loosely coupled and unit-testable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# Analysis Interfaces
# --------------------------------------------------------------------------- #

class IAnalysisEngine(ABC):
    """Base for SMC, Price-Action, and Decision engines."""

    @abstractmethod
    async def analyze(
        self,
        symbol:    str,
        timeframe: str,
        data:      Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run analysis on market data and return structured result."""

    @abstractmethod
    def get_name(self) -> str:
        """Return human-readable engine name."""


class IAgent(ABC):
    """Base for all voting agents."""

    @abstractmethod
    async def vote(
        self,
        context: Dict[str, Any],
    ) -> Any:
        """Cast a vote given the current market context."""

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Unique identifier for this agent."""

    @property
    def weight(self) -> float:
        """Voting weight (default 1.0)."""
        return 1.0


# --------------------------------------------------------------------------- #
# Execution Interfaces
# --------------------------------------------------------------------------- #

class IExecutionBroker(ABC):
    """Broker / MT5 connector interface."""

    @abstractmethod
    async def place_order(
        self,
        symbol:     str,
        order_type: str,
        volume:     float,
        price:      Optional[float] = None,
        sl:         Optional[float] = None,
        tp:         Optional[float] = None,
        comment:    str = "",
    ) -> Dict[str, Any]:
        """Place an order and return ticket info."""

    @abstractmethod
    async def close_position(
        self,
        ticket:  int,
        volume:  Optional[float] = None,
        comment: str = "",
    ) -> Dict[str, Any]:
        """Close a position (partially or fully)."""

    @abstractmethod
    async def get_open_positions(self) -> List[Dict[str, Any]]:
        """Return all currently open positions."""

    @abstractmethod
    async def get_account_info(self) -> Dict[str, Any]:
        """Return account balance, equity, margin info."""


# --------------------------------------------------------------------------- #
# Risk Interfaces
# --------------------------------------------------------------------------- #

class IRiskManager(ABC):
    """Risk check interface."""

    @abstractmethod
    async def check(
        self,
        signal:  Dict[str, Any],
        account: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate a signal against risk rules.
        Returns dict with keys: approved (bool), reason (str), adjusted_lot (float).
        """


# --------------------------------------------------------------------------- #
# Data / Repository Interfaces
# --------------------------------------------------------------------------- #

class IRepository(ABC):
    """Generic async CRUD repository."""

    @abstractmethod
    async def get(self, id: str) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    async def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit:   int = 100,
        offset:  int = 0,
    ) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def update(
        self,
        id:   str,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    async def delete(self, id: str) -> bool:
        ...
