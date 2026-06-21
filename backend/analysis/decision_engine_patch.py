"""
decision_engine_patch.py -- Phase D Fix (ARCH-9)

Before: monkey-patching DecisionEngine.make_decision at module load time
        (fragile, mypy errors, fails on reload)
After:  _make_decision is already defined as a module-level function
        and assigned to DecisionEngine.make_decision at the end of
        decision_engine.py itself -- this file only adds computed
        properties to SMCScoreResult that are missing from the dataclass.

This file is safe to import multiple times (idempotent guards).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _patch_smc_score_result() -> None:
    """
    Add .order_block_count and .fvg_count computed properties to SMCScoreResult.
    These are used in _result_to_output() but are not dataclass fields.
    Idempotent -- safe to call multiple times.
    """
    try:
        from backend.analysis.decision_engine import SMCScoreResult

        if not hasattr(SMCScoreResult, "order_block_count"):

            @property  # type: ignore[misc]
            def order_block_count(self) -> int:
                """Derived: non-zero order_block_score implies >=1 OB present."""
                return 1 if getattr(self, "order_block_score", 0) > 0 else 0

            @property  # type: ignore[misc]
            def fvg_count(self) -> int:
                """Derived: non-zero fvg_score implies >=1 FVG present."""
                return 1 if getattr(self, "fvg_score", 0) > 0 else 0

            SMCScoreResult.order_block_count = order_block_count  # type: ignore[attr-defined]
            SMCScoreResult.fvg_count = fvg_count  # type: ignore[attr-defined]
            logger.debug("SMCScoreResult patched: order_block_count + fvg_count added")

    except ImportError as exc:
        logger.warning("decision_engine_patch: SMCScoreResult not found -- %s", exc)
    except Exception as exc:
        logger.warning("decision_engine_patch: patch skipped -- %s", exc)


def _verify_make_decision() -> None:
    """
    Verify that DecisionEngine.make_decision is properly bound.
    decision_engine.py already assigns it at module load, but if something
    went wrong during import (partial import), log a warning.
    Does NOT re-assign -- that would create a double-binding bug.
    """
    try:
        from backend.analysis.decision_engine import DecisionEngine
        if not hasattr(DecisionEngine, "make_decision"):
            logger.error(
                "DecisionEngine.make_decision is MISSING -- "
                "check decision_engine.py for the assignment at the bottom of the file. "
                "This will cause AttributeError when decision_service calls make_decision()."
            )
        else:
            logger.debug("DecisionEngine.make_decision: OK")
    except ImportError as exc:
        logger.warning("decision_engine_patch: DecisionEngine not found -- %s", exc)


# Apply all patches at import time (idempotent)
_patch_smc_score_result()
_verify_make_decision()
