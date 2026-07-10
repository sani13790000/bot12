"""
backend/risk/manager.py
Risk Management System - Position sizing, drawdown limits, exposure control
Complete production-ready implementation
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import StrEnum

logger = logging.getLogger(__name__)


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskMetrics:
    """Risk metrics snapshot."""
    current_equity: float
    daily_loss: float
    drawdown_percent: float
    margin_level: float
    risk_level: RiskLevel
    active_positions: int
    max_positions: int
    daily_volume: float
    max_daily_volume: float


@dataclass
class Position:
    """Trading position."""
    ticket: int
    symbol: str
    type: str
    volume: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    profit: float


class RiskManager:
    """Central risk management system"""

    def __init__(
        self,
        initial_balance: float = 10000,
        max_daily_loss_percent: float = 5.0,
        max_drawdown_percent: float = 20.0,
        max_positions: int = 5,
        max_position_size: float = 1.0,
        risk_per_trade: float = 2.0,  # % of equity
        margin_warning_level: float = 50.0,
        margin_stop_level: float = 30.0,
    ):
        """Initialize Risk Manager."""
        self.initial_balance = initial_balance
        self.peak_equity = initial_balance
        self.current_equity = initial_balance
        self.max_daily_loss = (initial_balance * max_daily_loss_percent) / 100
        self.max_drawdown = (initial_balance * max_drawdown_percent) / 100
        self.max_positions = max_positions
        self.max_position_size = max_position_size
        self.risk_per_trade = risk_per_trade
        self.margin_warning_level = margin_warning_level
        self.margin_stop_level = margin_stop_level
        
        self.positions: List[Position] = []
        self.daily_loss = 0.0
        self.daily_volume = 0.0
        self.max_daily_volume = 10.0  # Max 10 lots per day
        self.trading_enabled = True
        
        logger.info(
            "[risk] RiskManager initialized: balance=%.2f, max_loss=%.2f, max_dd=%.2f",
            initial_balance,
            self.max_daily_loss,
            self.max_drawdown
        )

    def check_risk_levels(self, current_equity: float, margin_level: float) -> Tuple[RiskLevel, List[str]]:
        """Check risk levels and return alerts."""
        alerts = []
        risk_level = RiskLevel.LOW

        # Update equity and peak
        self.current_equity = current_equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        # Check daily loss
        daily_loss = self.initial_balance - current_equity
        if daily_loss > self.max_daily_loss:
            alerts.append(f"Daily loss limit exceeded: ${daily_loss:.2f}")
            risk_level = RiskLevel.CRITICAL
        elif daily_loss > (self.max_daily_loss * 0.8):
            alerts.append(f"Daily loss warning: ${daily_loss:.2f}")
            risk_level = RiskLevel.HIGH

        # Check drawdown
        drawdown = (self.peak_equity - current_equity) / self.peak_equity * 100
        if drawdown > self.max_drawdown:
            alerts.append(f"Max drawdown exceeded: {drawdown:.2f}%")
            risk_level = RiskLevel.CRITICAL
        elif drawdown > (self.max_drawdown * 0.8):
            alerts.append(f"Drawdown warning: {drawdown:.2f}%")
            if risk_level != RiskLevel.CRITICAL:
                risk_level = RiskLevel.HIGH

        # Check margin
        if margin_level < self.margin_stop_level:
            alerts.append(f"Margin critical: {margin_level:.2f}%")
            risk_level = RiskLevel.CRITICAL
        elif margin_level < self.margin_warning_level:
            alerts.append(f"Margin warning: {margin_level:.2f}%")
            if risk_level != RiskLevel.CRITICAL:
                risk_level = RiskLevel.HIGH

        # Check position count
        if len(self.positions) >= self.max_positions:
            alerts.append(f"Max positions reached: {len(self.positions)}/{self.max_positions}")
            if risk_level == RiskLevel.LOW:
                risk_level = RiskLevel.MEDIUM

        if alerts:
            logger.warning("[risk] Alerts: %s", " | ".join(alerts))

        return risk_level, alerts

    def can_open_position(
        self,
        symbol: str,
        volume: float,
        entry_price: float,
        stop_loss: float
    ) -> Tuple[bool, str]:
        """Check if position can be opened."""
        # Check if trading enabled
        if not self.trading_enabled:
            return False, "Trading disabled due to risk limits"

        # Check position count
        if len(self.positions) >= self.max_positions:
            return False, f"Max positions reached ({self.max_positions})"

        # Check volume
        if volume > self.max_position_size:
            return False, f"Position size exceeds limit ({self.max_position_size} lots)"

        # Check daily volume
        if self.daily_volume + volume > self.max_daily_volume:
            return False, f"Daily volume limit exceeded"

        # Check risk amount
        risk_amount = abs(entry_price - stop_loss) * volume * 100000  # Assuming micro lots
        max_risk = (self.current_equity * self.risk_per_trade) / 100
        
        if risk_amount > max_risk:
            return False, f"Risk per trade exceeded (${risk_amount:.2f} > ${max_risk:.2f})"

        logger.info(
            "[risk] Position allowed: %s %.2f lots, risk=$%.2f",
            symbol, volume, risk_amount
        )
        return True, "OK"

    def register_position(self, position: Position) -> None:
        """Register opened position."""
        self.positions.append(position)
        self.daily_volume += position.volume
        logger.info(
            "[risk] Position registered: %s ticket=%d volume=%.2f",
            position.symbol, position.ticket, position.volume
        )

    def unregister_position(self, ticket: int, pnl: float) -> None:
        """Unregister closed position."""
        position = next((p for p in self.positions if p.ticket == ticket), None)
        if position:
            self.positions.remove(position)
            self.daily_loss += abs(pnl) if pnl < 0 else 0
            logger.info(
                "[risk] Position closed: %s ticket=%d pnl=%.2f",
                position.symbol, ticket, pnl
            )

    def get_metrics(self, margin_level: float) -> RiskMetrics:
        """Get current risk metrics."""
        drawdown = ((self.peak_equity - self.current_equity) / self.peak_equity * 100) if self.peak_equity > 0 else 0
        
        # Determine risk level
        risk_level = RiskLevel.LOW
        if drawdown > (self.max_drawdown * 0.8) or margin_level < self.margin_warning_level:
            risk_level = RiskLevel.HIGH
        if drawdown > self.max_drawdown or margin_level < self.margin_stop_level:
            risk_level = RiskLevel.CRITICAL

        return RiskMetrics(
            current_equity=self.current_equity,
            daily_loss=self.daily_loss,
            drawdown_percent=drawdown,
            margin_level=margin_level,
            risk_level=risk_level,
            active_positions=len(self.positions),
            max_positions=self.max_positions,
            daily_volume=self.daily_volume,
            max_daily_volume=self.max_daily_volume
        )

    def reset_daily_limits(self) -> None:
        """Reset daily counters (call at end of trading day)."""
        self.daily_loss = 0.0
        self.daily_volume = 0.0
        self.trading_enabled = True
        logger.info("[risk] Daily limits reset")

    def get_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        symbol: str = "EURUSD"
    ) -> float:
        """Calculate optimal position size based on risk."""
        risk_amount = abs(entry_price - stop_loss)
        if risk_amount == 0:
            return 0.1
        
        max_risk = (self.current_equity * self.risk_per_trade) / 100
        position_size = max_risk / (risk_amount * 100000)  # Micro lots
        
        # Cap to max position size
        position_size = min(position_size, self.max_position_size)
        
        return round(position_size, 2)
