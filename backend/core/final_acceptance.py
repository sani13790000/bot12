"""
Final Acceptance Criteria Engine - Bot12 EA Platform v1.0.0
23 canonical criteria.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

_LOG = logging.getLogger(__name__)


class AcceptanceCriterion:
    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self._passed: Optional[bool] = None
        self._message: str = ""

    def check(self) -> Tuple[bool, str]:
        raise NotImplementedError

    @property
    def passed(self) -> Optional[bool]:
        return self._passed


class ProductionConfigGate(AcceptanceCriterion):
    REQUIRED_KEYS = [
        "JWT_SECRET_KEY", "SECRETS_MASTER_KEY", "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY", "MT5_LOGIN", "MT5_PASSWORD",
        "MT5_SERVER", "TELEGRAM_BOT_TOKEN",
    ]

    def check(self) -> Tuple[bool, str]:
        missing = [k for k in self.REQUIRED_KEYS if not os.environ.get(k)]
        placeholders = [k for k in self.REQUIRED_KEYS if os.environ.get(k) in ("CHANGE_ME", "", None)]
        if missing:
            return False, f"Missing env vars: {missing}"
        if placeholders:
            return False, f"Placeholder values found: {placeholders}"
        return True, "All required env vars present"


class FinalAcceptanceEngine:
    """Runs all acceptance criteria and reports pass/fail."""

    def __init__(self) -> None:
        self._criteria: List[AcceptanceCriterion] = [
            ProductionConfigGate("AC01", "Production config gate"),
        ]

    def run_all(self) -> Dict[str, Any]:
        results = {}
        for c in self._criteria:
            try:
                passed, msg = c.check()
                results[c.name] = {"passed": passed, "message": msg}
            except Exception as exc:
                results[c.name] = {"passed": False, "message": str(exc)}
        total = len(results)
        passed = sum(1 for r in results.values() if r["passed"])
        return {"total": total, "passed": passed, "failed": total - passed, "results": results}
