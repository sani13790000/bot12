"""
Final Acceptance Criteria Engine - Bot12 EA Platform v1.0.0
23 canonical checks across all 36 phases.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


class CheckStatus(str, Enum):
    PASS    = "PASS"
    FAIL    = "FAIL"
    SKIP    = "SKIP"
    PENDING = "PENDING"


@dataclass
class AcceptanceCheck:
    name: str
    description: str
    fn: Callable
    critical: bool = True
    status: CheckStatus = CheckStatus.PENDING
    error: Optional[str] = None


@dataclass
class AcceptanceReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    checks: List[AcceptanceCheck] = field(default_factory=list)
    passed_all: bool = False

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


class FinalAcceptanceEngine:
    """Runs all 36-phase acceptance checks."""

    def __init__(self) -> None:
        self._checks: List[AcceptanceCheck] = []

    def register(self, name: str, description: str, fn: Callable, critical: bool = True) -> None:
        self._checks.append(AcceptanceCheck(name=name, description=description, fn=fn, critical=critical))

    async def run_all(self) -> AcceptanceReport:
        report = AcceptanceReport(total=len(self._checks))
        for check in self._checks:
            try:
                result = check.fn()
                if asyncio.iscoroutine(result):
                    result = await result
                if result is False:
                    check.status = CheckStatus.FAIL
                    report.failed += 1
                else:
                    check.status = CheckStatus.PASS
                    report.passed += 1
            except Exception as exc:
                check.status = CheckStatus.FAIL
                check.error = str(exc)
                report.failed += 1
                log.error("check_failed check=%s: %s", check.name, exc)
            report.checks.append(check)

        report.passed_all = report.failed == 0
        return report


final_acceptance_engine = FinalAcceptanceEngine()
