"""
Phase 10 — License Manager
Enforces user subscription tiers and feature access.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from backend.observability import get_logger

logger = get_logger("security.license")


class PlanTier(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    ADMIN = "admin"


@dataclass
class PlanLimits:
    tier: PlanTier
    max_signals_per_day: int
    max_backtests_per_day: int
    max_positions: int
    can_use_ml: bool
    can_use_research: bool
    can_use_mt5: bool
    can_export_data: bool
    features: Set[str] = field(default_factory=set)


_PLAN_LIMITS: Dict[PlanTier, PlanLimits] = {
    PlanTier.FREE: PlanLimits(
        tier=PlanTier.FREE,
        max_signals_per_day=5,
        max_backtests_per_day=1,
        max_positions=1,
        can_use_ml=False,
        can_use_research=False,
        can_use_mt5=False,
        can_export_data=False,
        features={"signals_read", "dashboard"},
    ),
    PlanTier.BASIC: PlanLimits(
        tier=PlanTier.BASIC,
        max_signals_per_day=20,
        max_backtests_per_day=5,
        max_positions=3,
        can_use_ml=False,
        can_use_research=True,
        can_use_mt5=False,
        can_export_data=False,
        features={"signals_read", "dashboard", "research", "analytics"},
    ),
    PlanTier.PRO: PlanLimits(
        tier=PlanTier.PRO,
        max_signals_per_day=100,
        max_backtests_per_day=20,
        max_positions=10,
        can_use_ml=True,
        can_use_research=True,
        can_use_mt5=True,
        can_export_data=True,
        features={"signals_read", "signals_write", "dashboard", "research",
                  "analytics", "ml", "mt5", "export", "agents"},
    ),
    PlanTier.ENTERPRISE: PlanLimits(
        tier=PlanTier.ENTERPRISE,
        max_signals_per_day=1000,
        max_backtests_per_day=100,
        max_positions=50,
        can_use_ml=True,
        can_use_research=True,
        can_use_mt5=True,
        can_export_data=True,
        features={"*"},  # All features
    ),
    PlanTier.ADMIN: PlanLimits(
        tier=PlanTier.ADMIN,
        max_signals_per_day=99999,
        max_backtests_per_day=99999,
        max_positions=9999,
        can_use_ml=True,
        can_use_research=True,
        can_use_mt5=True,
        can_export_data=True,
        features={"*"},
    ),
}

# In-memory usage counters (reset daily)
_daily_usage: Dict[str, Dict[str, int]] = {}
_usage_date: Dict[str, str] = {}


def _today() -> str:
    from datetime import date
    return str(date.today())


def _get_usage(user_id: str) -> Dict[str, int]:
    today = _today()
    if _usage_date.get(user_id) != today:
        _daily_usage[user_id] = {"signals": 0, "backtests": 0}
        _usage_date[user_id] = today
    return _daily_usage.setdefault(user_id, {"signals": 0, "backtests": 0})


def get_plan_limits(tier: str) -> PlanLimits:
    """Get limits for a plan tier string."""
    try:
        return _PLAN_LIMITS[PlanTier(tier)]
    except (ValueError, KeyError):
        return _PLAN_LIMITS[PlanTier.FREE]


def check_signal_limit(user_id: str, tier: str) -> bool:
    """True if user can generate more signals today."""
    limits = get_plan_limits(tier)
    usage = _get_usage(user_id)
    return usage["signals"] < limits.max_signals_per_day


def record_signal_usage(user_id: str) -> None:
    usage = _get_usage(user_id)
    usage["signals"] = usage.get("signals", 0) + 1


def check_backtest_limit(user_id: str, tier: str) -> bool:
    limits = get_plan_limits(tier)
    usage = _get_usage(user_id)
    return usage["backtests"] < limits.max_backtests_per_day


def record_backtest_usage(user_id: str) -> None:
    usage = _get_usage(user_id)
    usage["backtests"] = usage.get("backtests", 0) + 1


def check_feature_access(tier: str, feature: str) -> bool:
    """True if tier has access to feature."""
    limits = get_plan_limits(tier)
    return "*" in limits.features or feature in limits.features


def get_usage_summary(user_id: str, tier: str) -> Dict:
    limits = get_plan_limits(tier)
    usage = _get_usage(user_id)
    return {
        "tier": tier,
        "signals_used": usage.get("signals", 0),
        "signals_limit": limits.max_signals_per_day,
        "backtests_used": usage.get("backtests", 0),
        "backtests_limit": limits.max_backtests_per_day,
        "features": list(limits.features),
        "date": _today(),
    }
