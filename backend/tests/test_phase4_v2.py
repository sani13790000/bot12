# Phase 4 v2 — Risk Engine Extended Tests
import pytest, threading
from dataclasses import dataclass

class KillSwitchActivatedError(Exception): pass

@dataclass
class KSConfig:
    equity_floor_usd: float = 500.0
    max_drawdown_pct: float = 10.0
    admin_token: str = "admin-secret"
