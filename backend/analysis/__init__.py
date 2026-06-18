"""Analysis package — SMC, Price Action, Decision Engine."""
# Phase-4 patch: ensures SMCScoreResult.order_block_count/fvg_count
# and DecisionEngine.make_decision are always available.
try:
    from . import decision_engine_patch as _dep  # noqa: F401
except Exception:
    pass

from .decision_engine import (
    DecisionEngine,
    DecisionInput,
    DecisionOutput,
    SMCContext,
    PriceActionContext,
    SessionContext,
    LicenseContext,
    RiskContext,
    SymbolPolicy,
    VolatilityContext,
    MultiTimeframeContext,
    LiquidityContext,
)

__all__ = [
    'DecisionEngine',
    'DecisionInput',
    'DecisionOutput',
    'SMCContext',
    'PriceActionContext',
    'SessionContext',
    'LicenseContext',
    'RiskContext',
    'SymbolPolicy',
    'VolatilityContext',
    'MultiTimeframeContext',
    'LiquidityContext',
]
