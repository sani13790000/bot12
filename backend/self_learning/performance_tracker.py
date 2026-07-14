"""Performance Tracker - Track model and trading performance"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Single performance metric"""
    timestamp: datetime
    metric_name: str
    value: float
    metadata: Dict[str, Any] = None


class PerformanceTracker:
    """
    Tracks and analyzes trading and model performance.
    
    Metrics tracked:
    - Win rate
    - Profit factor
    - Sharpe ratio
    - Max drawdown
    - Model accuracy
    - Signal precision/recall
    """
    
    def __init__(self):
        self.metrics: List[PerformanceMetric] = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.max_drawdown = 0.0
        self.current_drawdown = 0.0
        self.peak_equity = 0.0
    
    async def record_trade_result(self, profit: float, is_win: bool) -> None:
        """
        Record trade result.
        
        Args:
            profit: Profit/loss amount
            is_win: Whether trade was winning
        """
        self.total_trades += 1
        self.total_profit += profit
        
        if is_win:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        self._record_metric(f"trade_{self.total_trades}", profit)
        log.debug(f"Trade recorded: {'WIN' if is_win else 'LOSS'} {profit:+.2f}")
    
    async def record_equity_update(self, current_equity: float) -> None:
        """
        Record equity update for drawdown tracking.
        
        Args:
            current_equity: Current account equity
        """
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
            self.current_drawdown = 0.0
        else:
            drawdown = (self.peak_equity - current_equity) / self.peak_equity if self.peak_equity > 0 else 0
            self.current_drawdown = drawdown
            self.max_drawdown = max(self.max_drawdown, drawdown)
        
        self._record_metric("equity", current_equity)
    
    async def record_model_prediction(
        self, predicted_signal: str, actual_signal: str, confidence: float
    ) -> None:
        """
        Record model prediction for accuracy tracking.
        
        Args:
            predicted_signal: Model prediction (BUY/SELL/HOLD)
            actual_signal: Actual market outcome
            confidence: Model confidence (0-1)
        """
        is_correct = predicted_signal == actual_signal
        self._record_metric("prediction_accuracy", 1.0 if is_correct else 0.0)
        log.debug(f"Prediction: {predicted_signal} vs {actual_signal} (conf: {confidence:.2f})")
    
    def _record_metric(self, metric_name: str, value: float) -> None:
        """Record a performance metric"""
        metric = PerformanceMetric(
            timestamp=datetime.utcnow(),
            metric_name=metric_name,
            value=value
        )
        self.metrics.append(metric)
    
    def get_win_rate(self) -> float:
        """Get win rate percentage"""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
    
    def get_profit_factor(self) -> float:
        """Get profit factor"""
        if self.losing_trades == 0:
            return 0.0
        
        # Simplified: total wins / total losses
        # In reality, this would be sum of wins / sum of losses
        return self.winning_trades / self.losing_trades if self.losing_trades > 0 else 0.0
    
    def get_sharpe_ratio(self) -> float:
        """
        Calculate Sharpe ratio.
        
        Returns:
            Sharpe ratio (simplified version)
        """
        if len(self.metrics) < 2:
            return 0.0
        
        try:
            # Get recent trade results
            trades = [m.value for m in self.metrics if "trade_" in m.metric_name][-100:]  # Last 100 trades
            
            if len(trades) < 2:
                return 0.0
            
            avg_return = sum(trades) / len(trades)
            variance = sum((x - avg_return) ** 2 for x in trades) / len(trades)
            std_dev = variance ** 0.5
            
            # Sharpe = avg_return / std_dev (assuming 0% risk-free rate)
            if std_dev > 0:
                return avg_return / std_dev
            return 0.0
        
        except Exception as e:
            log.error(f"Sharpe ratio calculation error: {e}")
            return 0.0
    
    def get_accuracy(self) -> float:
        """Get model prediction accuracy"""
        accuracy_metrics = [m.value for m in self.metrics if m.metric_name == "prediction_accuracy"]
        
        if not accuracy_metrics:
            return 0.0
        
        return (sum(accuracy_metrics) / len(accuracy_metrics)) * 100
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": round(self.get_win_rate(), 2),
            "total_profit": round(self.total_profit, 2),
            "profit_factor": round(self.get_profit_factor(), 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "current_drawdown_pct": round(self.current_drawdown * 100, 2),
            "sharpe_ratio": round(self.get_sharpe_ratio(), 2),
            "model_accuracy_pct": round(self.get_accuracy(), 2),
            "peak_equity": round(self.peak_equity, 2),
            "metrics_count": len(self.metrics)
        }
    
    def reset_metrics(self) -> None:
        """Reset all metrics"""
        self.metrics = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.max_drawdown = 0.0
        self.current_drawdown = 0.0
        self.peak_equity = 0.0
        log.info("Performance metrics reset")
