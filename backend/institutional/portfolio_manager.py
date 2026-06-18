"""Galaxy Vast AI Trading Platform — Institutional Portfolio Manager.

Strategies:
- EQUAL_WEIGHT
- RISK_PARITY
- KELLY_CRITERION
- MINIMUM_VARIANCE
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class PortfolioPosition:
    symbol: str
    direction: str
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_usd: float
    weight: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "volume": self.volume,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_usd": round(self.risk_usd, 2),
            "weight": round(self.weight, 4),
        }


@dataclass
class Portfolio:
    cash: float
    total_value: float
    positions: List[PortfolioPosition] = field(default_factory=list)
    allocation: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cash": round(self.cash, 2),
            "total_value": round(self.total_value, 2),
            "positions": [p.to_dict() for p in self.positions],
            "allocation": self.allocation,
        }


class PortfolioManager:
    """Multi-symbol portfolio construction and rebalancing."""

    def __init__(self, total_capital: float, max_risk_pct: float = 5.0):
        self.total_capital = total_capital
        self.max_risk_pct = max_risk_pct
        self.positions: List[PortfolioPosition] = []

    def build_portfolio(
        self,
        signals: List[Dict[str, Any]],
        returns_matrix: Optional[pd.DataFrame] = None,
        strategy: str = "EQUAL_WEIGHT",
    ) -> Portfolio:
        if not signals:
            return Portfolio(cash=self.total_capital, total_value=self.total_capital)

        symbols = [s["symbol"] for s in signals]
        n = len(symbols)

        if strategy == "EQUAL_WEIGHT":
            weights = {sym: 1.0 / n for sym in symbols}
        elif strategy == "RISK_PARITY" and returns_matrix is not None:
            weights = self._risk_parity_weights(returns_matrix, symbols)
        elif strategy == "MINIMUM_VARIANCE" and returns_matrix is not None:
            weights = self._min_variance_weights(returns_matrix, symbols)
        elif strategy == "KELLY_CRITERION":
            weights = self._kelly_weights(signals)
        else:
            weights = {sym: 1.0 / n for sym in symbols}

        positions = []
        allocation = {}
        total_risk = 0.0
        for sig in signals:
            sym = sig["symbol"]
            weight = weights.get(sym, 0.0)
            allocation[sym] = weight
            pos = self._signal_to_position(sig, weight)
            positions.append(pos)
            total_risk += pos.risk_usd

        # Risk cap check
        if total_risk > self.total_capital * (self.max_risk_pct / 100.0):
            scale = self.total_capital * (self.max_risk_pct / 100.0) / total_risk
            for pos in positions:
                pos.volume *= scale
                pos.risk_usd *= scale

        self.positions = positions
        return Portfolio(
            cash=self.total_capital - sum(p.risk_usd for p in positions),
            total_value=self.total_capital,
            positions=positions,
            allocation=allocation,
        )

    def _signal_to_position(self, signal: Dict[str, Any], weight: float) -> PortfolioPosition:
        symbol = signal.get("symbol", "XAUUSD")
        direction = str(signal.get("direction", "BUY")).upper()
        ep = float(signal.get("entry_price", 0.0))
        sl = float(signal.get("stop_loss", 0.0))
        tp = float(signal.get("take_profit", 0.0))
        risk_amount = self.total_capital * (self.max_risk_pct / 100.0) * weight
        risk_pips = abs(ep - sl)
        point_value = 10.0
        volume = risk_amount / (risk_pips * point_value) if risk_pips > 0 else 0.01
        return PortfolioPosition(
            symbol=symbol,
            direction=direction,
            volume=round(volume, 2),
            entry_price=ep,
            stop_loss=sl,
            take_profit=tp,
            risk_usd=risk_amount,
            weight=weight,
        )

    @staticmethod
    def _risk_parity_weights(returns: pd.DataFrame, symbols: List[str]) -> Dict[str, float]:
        sub = returns[symbols].dropna()
        cov = sub.cov().values
        inv_diag = 1.0 / np.diag(cov)
        raw = inv_diag / inv_diag.sum()
        return {sym: float(raw[i]) for i, sym in enumerate(symbols)}

    @staticmethod
    def _min_variance_weights(returns: pd.DataFrame, symbols: List[str]) -> Dict[str, float]:
        sub = returns[symbols].dropna()
        cov = sub.cov().values
        try:
            inv = np.linalg.inv(cov)
            ones = np.ones(len(symbols))
            w = inv @ ones / (ones.T @ inv @ ones)
        except np.linalg.LinAlgError:
            w = np.ones(len(symbols)) / len(symbols)
        return {sym: float(w[i]) for i, sym in enumerate(symbols)}

    @staticmethod
    def _kelly_weights(signals: List[Dict[str, Any]]) -> Dict[str, float]:
        total = 0.0
        weights = {}
        for sig in signals:
            win_rate = float(sig.get("win_rate", 0.5))
            avg_win = float(sig.get("avg_win", 1.0))
            avg_loss = float(sig.get("avg_loss", 1.0))
            k = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win if avg_win > 0 else 0.0
            k = max(0.0, k)
            weights[sig["symbol"]] = k
            total += k
        if total == 0:
            n = len(signals)
            return {s["symbol"]: 1.0 / n for s in signals}
        return {sym: w / total for sym, w in weights.items()}
