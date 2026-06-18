"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Risk Management Package — Complete Suite

Modules:
    lot_sizing         → Dynamic & ATR-based position sizing
    equity_protection  → Drawdown guard + consecutive loss halt
    correlation_filter → Currency correlation exposure control
    volatility_filter  → ATR-based volatility gate
    exposure_control   → Portfolio exposure limits
    daily_limits       → Daily/Weekly/Monthly loss limits
    portfolio_risk     → Cross-symbol portfolio risk
    risk_orchestrator  → Master orchestrator (single entry point)
"""
from .lot_sizing         import DynamicLotSizer, LotSizingConfig, LotSizingMethod, LotSizingResult, get_lot_sizer
from .equity_protection  import EquityProtectionEngine, EquityProtectionConfig, ProtectionLevel, get_equity_protection
from .correlation_filter import CorrelationFilter, CorrelationFilterConfig, CorrelationCheckResult, get_correlation_filter
from .volatility_filter  import VolatilityFilter, VolatilityFilterConfig, VolatilityLevel, get_volatility_filter
from .exposure_control   import ExposureControlEngine, ExposureControlConfig, ExposurePosition, get_exposure_control
from .daily_limits       import DailyLimitsEngine
from .portfolio_risk     import PortfolioRiskManager
from .risk_orchestrator  import RiskOrchestrator, RiskInput, RiskDecision, get_risk_orchestrator

__all__ = [
    "DynamicLotSizer", "LotSizingConfig", "LotSizingMethod", "LotSizingResult", "get_lot_sizer",
    "EquityProtectionEngine", "EquityProtectionConfig", "ProtectionLevel", "get_equity_protection",
    "CorrelationFilter", "CorrelationFilterConfig", "CorrelationCheckResult", "get_correlation_filter",
    "VolatilityFilter", "VolatilityFilterConfig", "VolatilityLevel", "get_volatility_filter",
    "ExposureControlEngine", "ExposureControlConfig", "ExposurePosition", "get_exposure_control",
    "DailyLimitsEngine", "PortfolioRiskManager",
    "RiskOrchestrator", "RiskInput", "RiskDecision", "get_risk_orchestrator",
]
