"""
Final Acceptance Criteria Engine - Bot12 EA Platform v1.0
Verifies all system components are ready for production deployment.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)

@dataclass
class AcceptanceCriteria:
    name: str
    description: str
    check_fn: Callable[[], bool]
    critical: bool = True

@dataclass
class AcceptanceResult:
    criteria_name: str
    passed: bool
    critical: bool
    message: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class FinalAcceptanceEngine:
    """Run pre-deployment acceptance checks."""

    def __init__(self) -> None:
        self._criteria: list[AcceptanceCriteria] = []

    def register(self, criteria: AcceptanceCriteria) -> None:
        self._criteria.append(criteria)

    def run_all(self) -> list[AcceptanceResult]:
        results = []
        for c in self._criteria:
            try:
                passed = c.check_fn()
                msg = "PASS" if passed else "FAIL"
            except Exception as exc:
                passed = False
                msg = f"ERROR: {exc}"
            results.append(AcceptanceResult(criteria_name=c.name, passed=passed, critical=c.critical, message=msg))
        return results

    def all_passed(self, results: list[AcceptanceResult]) -> bool:
        return all(r.passed for r in results if r.critical)

    def summary(self, results: list[AcceptanceResult]) -> dict:
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        crit = sum(1 for r in results if r.critical and not r.passed)
        return {"total": total, "passed": passed, "failed": total - passed, "critical_failures": crit, "ready": crit == 0}

final_acceptance = FinalAcceptanceEngine()
