"""Trade Dataset Generator - Generate training data from trades"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

log = logging.getLogger(__name__)


class TradeDatasetGenerator:
    """
    Generates ML training datasets from executed trades.
    
    Creates features from:
    - Market data (OHLCV)
    - Technical indicators
    - Trade execution data
    - Performance outcomes
    """
    
    def __init__(self):
        self.trades: List[Dict[str, Any]] = []
        self.market_data: List[Dict[str, Any]] = []
    
    async def add_trade(self, trade: Dict[str, Any]) -> None:
        """
        Add executed trade to dataset.
        
        Args:
            trade: Trade execution data
        """
        try:
            enriched_trade = {
                "timestamp": trade.get("timestamp", datetime.utcnow()),
                "symbol": trade.get("symbol", ""),
                "order_type": trade.get("order_type", "MARKET"),
                "volume": trade.get("volume", 0),
                "entry_price": trade.get("entry_price", 0),
                "exit_price": trade.get("exit_price", 0),
                "profit_loss": trade.get("profit_loss", 0),
                "duration_seconds": trade.get("duration_seconds", 0),
                "slippage": trade.get("slippage", 0),
                "result": trade.get("result", "LOSS"),  # WIN, LOSS, BREAKEVEN
            }
            
            self.trades.append(enriched_trade)
            log.debug(f"Trade added: {enriched_trade['result']} {enriched_trade['profit_loss']:+.2f}")
        
        except Exception as e:
            log.error(f"Error adding trade: {e}")
    
    async def add_market_snapshot(self, market_data: Dict[str, Any]) -> None:
        """
        Add market data snapshot.
        
        Args:
            market_data: Market OHLCV and indicators
        """
        try:
            snapshot = {
                "timestamp": market_data.get("timestamp", datetime.utcnow()),
                "symbol": market_data.get("symbol", ""),
                "open": market_data.get("open", 0),
                "high": market_data.get("high", 0),
                "low": market_data.get("low", 0),
                "close": market_data.get("close", 0),
                "volume": market_data.get("volume", 0),
                "rsi": market_data.get("rsi", 50),
                "macd": market_data.get("macd", 0),
                "bb_upper": market_data.get("bb_upper", 0),
                "bb_lower": market_data.get("bb_lower", 0),
                "trend": market_data.get("trend", "NEUTRAL"),
            }
            
            self.market_data.append(snapshot)
        
        except Exception as e:
            log.error(f"Error adding market snapshot: {e}")
    
    async def generate_training_dataset(self) -> List[Dict[str, Any]]:
        """
        Generate complete training dataset from collected trades and market data.
        
        Returns:
            List of training samples with features and labels
        """
        try:
            if not self.trades:
                log.warning("No trades to generate dataset from")
                return []
            
            dataset = []
            
            for trade in self.trades:
                sample = self._create_training_sample(trade)
                dataset.append(sample)
            
            log.info(f"Dataset generated: {len(dataset)} samples")
            return dataset
        
        except Exception as e:
            log.error(f"Dataset generation error: {e}")
            return []
    
    def _create_training_sample(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create training sample from trade.
        
        Returns:
            Feature vector + label
        """
        return {
            # Features
            "entry_price": trade.get("entry_price", 0),
            "exit_price": trade.get("exit_price", 0),
            "volume": trade.get("volume", 0),
            "duration_seconds": trade.get("duration_seconds", 0),
            "slippage": trade.get("slippage", 0),
            
            # Labels
            "profit_loss": trade.get("profit_loss", 0),
            "result": trade.get("result", "LOSS"),
            "is_winning": 1 if trade.get("result") == "WIN" else 0,
            
            # Metadata
            "timestamp": trade.get("timestamp"),
            "symbol": trade.get("symbol")
        }
    
    async def get_dataset_stats(self) -> Dict[str, Any]:
        """Get dataset statistics"""
        if not self.trades:
            return {"samples": 0}
        
        winning = sum(1 for t in self.trades if t.get("result") == "WIN")
        total_profit = sum(t.get("profit_loss", 0) for t in self.trades)
        avg_profit = total_profit / len(self.trades) if self.trades else 0
        
        return {
            "samples": len(self.trades),
            "winning_trades": winning,
            "losing_trades": len(self.trades) - winning,
            "win_rate_pct": (winning / len(self.trades) * 100) if self.trades else 0,
            "total_profit": total_profit,
            "average_profit_per_trade": avg_profit,
            "market_snapshots": len(self.market_data)
        }
    
    async def clear_old_data(self, max_samples: int = 10000) -> None:
        """
        Clear old data to manage memory.
        
        Args:
            max_samples: Keep only the most recent N samples
        """
        if len(self.trades) > max_samples:
            self.trades = self.trades[-max_samples:]
            log.info(f"Kept last {max_samples} trades, discarded older data")
        
        if len(self.market_data) > max_samples:
            self.market_data = self.market_data[-max_samples:]
            log.info(f"Kept last {max_samples} market snapshots")
