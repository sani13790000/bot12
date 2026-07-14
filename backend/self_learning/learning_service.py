"""Learning Service - Orchestrates self-learning pipeline"""
import logging
from typing import Dict, Any, Optional

from .training_pipeline import TrainingPipeline, TrainingConfig
from .retraining_service import RetrainingService, RetainingConfig
from .performance_tracker import PerformanceTracker
from .trade_dataset_generator import TradeDatasetGenerator

log = logging.getLogger(__name__)


class LearningService:
    """
    Orchestrates complete self-learning pipeline.
    
    Integrates:
    - Data collection (TradeDatasetGenerator)
    - Model training (TrainingPipeline)
    - Automated retraining (RetrainingService)
    - Performance monitoring (PerformanceTracker)
    """
    
    def __init__(
        self,
        training_config: Optional[TrainingConfig] = None,
        retraining_config: Optional[RetainingConfig] = None,
    ):
        self.training_pipeline = TrainingPipeline(training_config)
        self.retraining_service = RetrainingService(retraining_config)
        self.performance_tracker = PerformanceTracker()
        self.dataset_generator = TradeDatasetGenerator()
        self.is_enabled = True
    
    async def initialize(self) -> bool:
        """Initialize learning service"""
        try:
            log.info("Initializing learning service...")
            
            # Load existing model if available
            await self.training_pipeline.load_model("./models/current_model.pkl")
            
            log.info("Learning service initialized")
            return True
        
        except Exception as e:
            log.error(f"Initialization error: {e}")
            return False
    
    async def record_trade(self, trade: Dict[str, Any]) -> None:
        """
        Record executed trade.
        
        Args:
            trade: Trade execution data
        """
        try:
            # Add to dataset
            await self.dataset_generator.add_trade(trade)
            
            # Record result for performance tracking
            profit = trade.get("profit_loss", 0)
            is_win = profit > 0
            await self.performance_tracker.record_trade_result(profit, is_win)
            
            # Check if retraining needed
            if await self.retraining_service.check_retrain_needed():
                await self._trigger_retraining()
        
        except Exception as e:
            log.error(f"Error recording trade: {e}")
    
    async def record_market_data(self, market_data: Dict[str, Any]) -> None:
        """
        Record market data snapshot.
        
        Args:
            market_data: OHLCV and indicator data
        """
        try:
            await self.dataset_generator.add_market_snapshot(market_data)
        except Exception as e:
            log.error(f"Error recording market data: {e}")
    
    async def record_prediction(
        self, predicted_signal: str, actual_signal: str, confidence: float
    ) -> None:
        """
        Record model prediction for accuracy tracking.
        
        Args:
            predicted_signal: Model prediction
            actual_signal: Actual market outcome
            confidence: Model confidence (0-1)
        """
        try:
            await self.performance_tracker.record_model_prediction(
                predicted_signal, actual_signal, confidence
            )
            
            # Update model performance
            accuracy = (1.0 if predicted_signal == actual_signal else 0.0)
            await self.retraining_service.update_model_performance(accuracy)
        
        except Exception as e:
            log.error(f"Error recording prediction: {e}")
    
    async def _trigger_retraining(self) -> bool:
        """Trigger model retraining"""
        try:
            log.info("Triggering model retraining...")
            
            # Get dataset
            dataset = await self.dataset_generator.generate_training_dataset()
            
            # Prepare data
            X, y = await self.training_pipeline.prepare_data(dataset)
            
            # Train model
            success = await self.training_pipeline.train_model(X, y)
            
            if success:
                # Save model
                await self.training_pipeline.save_model("./models/current_model.pkl")
                log.info("Model retraining completed successfully")
                return True
            else:
                log.error("Model training failed")
                return False
        
        except Exception as e:
            log.error(f"Retraining error: {e}")
            return False
    
    async def get_model_prediction(self, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get prediction from trained model.
        
        Args:
            features: Input features for prediction
        
        Returns:
            Prediction result (signal + confidence) or None
        """
        try:
            if not self.is_enabled or self.training_pipeline.model is None:
                return None
            
            # Here you would make actual model prediction
            # For now, returning simulated prediction
            prediction = {
                "signal": "BUY",  # or SELL, HOLD
                "confidence": 0.75,
                "model_version": "current",
                "timestamp": None
            }
            
            return prediction
        
        except Exception as e:
            log.error(f"Prediction error: {e}")
            return None
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        return {
            "trading_stats": self.performance_tracker.get_performance_summary(),
            "dataset_stats": self._get_dataset_stats_sync(),
            "retraining_stats": self.retraining_service.get_status(),
            "model_status": self.training_pipeline.get_status(),
            "is_enabled": self.is_enabled
        }
    
    def _get_dataset_stats_sync(self) -> Dict[str, Any]:
        """Get dataset stats (sync wrapper)"""
        import asyncio
        try:
            # This is a hack - ideally this would be async
            stats = {
                "samples": len(self.dataset_generator.trades),
                "winning_trades": sum(1 for t in self.dataset_generator.trades if t.get("result") == "WIN"),
                "total_profit": sum(t.get("profit_loss", 0) for t in self.dataset_generator.trades)
            }
            return stats
        except Exception as e:
            log.error(f"Dataset stats error: {e}")
            return {}
    
    async def shutdown(self) -> None:
        """Shutdown learning service"""
        log.info("Shutting down learning service...")
        self.is_enabled = False
        log.info("Learning service shutdown complete")
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall service status"""
        return {
            "enabled": self.is_enabled,
            "training_pipeline": self.training_pipeline.get_status(),
            "retraining_service": self.retraining_service.get_status(),
            "dataset_samples": len(self.dataset_generator.trades),
            "status": "operational" if self.is_enabled else "disabled"
        }
