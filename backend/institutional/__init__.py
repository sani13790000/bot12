"""
Galaxy Vast Institutional Trading Framework.

Provides institutional-grade modules:
- Market Replay Engine
- Tick-level Backtesting
- Walk Forward Optimization
- Performance Metrics
- AI Explainability
- Reinforcement Learning Agent
- Portfolio Management
- Correlation Engine
- Monte Carlo Simulation
- Risk Engine
- Data persistence to PostgreSQL/Supabase
"""

from .market_replay import MarketReplay, ReplayState, ReplayConfig
from .tick_backtest import TickBacktestEngine, TickBacktestConfig
from .walk_forward import WalkForwardOptimizer, WalkForwardConfig
from .performance_metrics import PerformanceMetrics, EquityCurve
from .explainability import ExplainabilityEngine, SignalReason
from .rl_agent import RLTradingAgent, RLAgentConfig
from .portfolio import PortfolioManager, PortfolioAllocation
from .correlation import CorrelationEngine
from .monte_carlo import MonteCarloSimulator, MonteCarloConfig
from .risk_engine import InstitutionalRiskEngine
from .data_store import InstitutionalDataStore

__all__ = [
    "MarketReplay",
    "ReplayState",
    "ReplayConfig",
    "TickBacktestEngine",
    "TickBacktestConfig",
    "WalkForwardOptimizer",
    "WalkForwardConfig",
    "PerformanceMetrics",
    "EquityCurve",
    "ExplainabilityEngine",
    "SignalReason",
    "RLTradingAgent",
    "RLAgentConfig",
    "PortfolioManager",
    "PortfolioAllocation",
    "CorrelationEngine",
    "MonteCarloSimulator",
    "MonteCarloConfig",
    "InstitutionalRiskEngine",
    "InstitutionalDataStore",
]
