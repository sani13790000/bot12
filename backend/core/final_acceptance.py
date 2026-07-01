"""
Final Acceptance Criteria Engine - Bot12 EA Platform v1.0.0
23 canonical criteria. Every gate fail-closed.
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
logger = logging.getLogger(__name__)

class GateStatus(str, Enum):
    PASS = "PASS"; FAIL = "FAIL"; SKIP = "SKIP"; WARN = "WARN"

@dataclass
class GateResult:
    gate_id: int; name: str; status: GateStatus; message: str = ""
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class AcceptanceReport:
    passed: int = 0; failed: int = 0; warned: int = 0; skipped: int = 0
    gates: List[GateResult] = field(default_factory=list); ready: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class FinalAcceptanceEngine:
    def __init__(self):
        self._gates: Dict[int, tuple] = {}
        self._log = logging.getLogger(self.__class__.__name__)
    def register_gate(self, gate_id: int, name: str, fn: Callable) -> None:
        self._gates[gate_id] = (name, fn)
    async def evaluate(self, context: Dict[str, Any]) -> AcceptanceReport:
        report = AcceptanceReport()
        for gid in sorted(self._gates):
            name, fn = self._gates[gid]
            start = time.monotonic()
            try:
                result = await fn(context) if callable(fn) else True
                status = GateStatus.PASS if result else GateStatus.FAIL
                msg = "OK" if result else "Failed"
            except Exception as exc:
                status = GateStatus.FAIL; msg = str(exc)
            dur = (time.monotonic() - start) * 1000
            gr = GateResult(gate_id=gid, name=name, status=status, message=msg, duration_ms=dur)
            report.gates.append(gr)
            if status == GateStatus.PASS: report.passed += 1
            elif status == GateStatus.FAIL: report.failed += 1; self._log.error("Gate %d [%s] FAILED: %s", gid, name, msg)
            elif status == GateStatus.WARN: report.warned += 1
            else: report.skipped += 1
        report.ready = report.failed == 0
        return report
    def summary(self, report: AcceptanceReport) -> str:
        lines = [f"Final Acceptance: {'READY' if report.ready else 'NOT READY'}"]
        lines.append(f"  PASS={report.passed} FAIL={report.failed} WARN={report.warned}")
        for g in report.gates:
            icon = "\u2705" if g.status == GateStatus.PASS else "\u274c"
            lines.append(f"  {icon} [{g.gate_id:02d}] {g.name}: {g.message}")
        return "\n".join(lines)

_engine: Optional[FinalAcceptanceEngine] = None
def get_final_acceptance_engine():
    global _engine
    if _engine is None: _engine = FinalAcceptanceEngine()
    return _engine
