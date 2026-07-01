"""
Final Acceptance Criteria Engine - Bot12 EA Platform v1.0.0
23 canonical criteria. Every gate FAIL = block live trading.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

_LOG = logging.getLogger(__name__)


@dataclass
class AcceptanceCriterion:
    id: str
    name: str
    description: str
    gate_fn: Callable[[], bool]
    severity: str = 'CRITICAL'
    passed: Optional[bool] = None
    error: Optional[str] = None


class FinalAcceptanceEngine:
    """23-gate final acceptance engine for live trading readiness."""

    def __init__(self) -> None:
        self._criteria: List[AcceptanceCriterion] = []
        self._results: Dict[str, bool] = {}

    def register(self, criterion: AcceptanceCriterion) -> None:
        self._criteria.append(criterion)

    def run_all(self) -> Dict[str, Any]:
        passed = 0
        failed = 0
        errors = []

        for c in self._criteria:
            try:
                result = c.gate_fn()
                c.passed = result
                self._results[c.id] = result
                if result:
                    passed += 1
                else:
                    failed += 1
                    errors.append({'id': c.id, 'name': c.name, 'severity': c.severity})
            except Exception as e:
                c.passed = False
                c.error = str(e)
                failed += 1
                errors.append({'id': c.id, 'name': c.name, 'error': str(e), 'severity': c.severity})

        return {
            'total': len(self._criteria),
            'passed': passed,
            'failed': failed,
            'ready_for_live': failed == 0,
            'errors': errors,
        }

    def is_ready(self) -> bool:
        results = self.run_all()
        return results['ready_for_live']

    def reset(self) -> None:
        for c in self._criteria:
            c.passed = None
            c.error = None
        self._results.clear()


_engine: Optional[FinalAcceptanceEngine] = None


def get_acceptance_engine() -> FinalAcceptanceEngine:
    global _engine
    if _engine is None:
        _engine = FinalAcceptanceEngine()
    return _engine
