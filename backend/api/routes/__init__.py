"""Route modules — imported explicitly by main.py.

All route modules are listed here so that:
  from backend.api.routes import auth, signals, ...
works without ambiguity.
"""
from backend.api.routes import (
    agents,
    ai_prediction,
    analysis,
    analytics,
    auth,
    backtest_engine,
    dashboard,
    decision,
    institutional,
    institutional_backtest,
    intelligence,
    license,
    reports,
    research,
    risk,
    self_learning,
    signals,
    trade_report,
    trades,
    users,
    websocket_routes,
)

__all__ = [
    "agents",
    "ai_prediction",
    "analysis",
    "analytics",
    "auth",
    "backtest_engine",
    "dashboard",
    "decision",
    "institutional",
    "institutional_backtest",
    "intelligence",
    "license",
    "reports",
    "research",
    "risk",
    "self_learning",
    "signals",
    "trade_report",
    "trades",
    "users",
    "websocket_routes",
]
