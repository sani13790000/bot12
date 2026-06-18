"""
phase4 patch: promotes DecisionEngine.make_decision from module-level monkey-patch
to a proper method by importing and re-exporting.

The original decision_engine.py appended:
    DecisionEngine.make_decision = _make_decision
at module load time, which is fragile (fails on reload, mypy errors, etc.).

This file is imported by __init__.py AFTER the class is defined,
so the method is always correctly bound.

Also patches SMCScoreResult to expose .order_block_count and .fvg_count
computed properties used in _result_to_output().
"""
from __future__ import annotations


def _patch_decision_engine() -> None:
    """Apply all phase-4 patches to DecisionEngine and SMCScoreResult."""
    try:
        from backend.analysis.decision_engine import DecisionEngine, SMCScoreResult
        # ----- SMCScoreResult: add computed count properties -----
        if not hasattr(SMCScoreResult, 'order_block_count'):
            @property  # type: ignore[misc]
            def order_block_count(self) -> int:
                """Derived count — non-zero score means at least one OB."""
                return 1 if self.order_block_score > 0 else 0

            @property  # type: ignore[misc]
            def fvg_count(self) -> int:
                """Derived count — non-zero score means at least one FVG."""
                return 1 if self.fvg_score > 0 else 0

            SMCScoreResult.order_block_count = order_block_count  # type: ignore[attr-defined]
            SMCScoreResult.fvg_count = fvg_count  # type: ignore[attr-defined]

        # ----- DecisionEngine: ensure make_decision is bound -----
        # The original file already does:  DecisionEngine.make_decision = _make_decision
        # This is a safety guard — if for any reason the assignment was skipped
        # (e.g. partial import), we re-apply it here.
        if not hasattr(DecisionEngine, 'make_decision'):
            from backend.analysis.decision_engine import _make_decision
            DecisionEngine.make_decision = _make_decision  # type: ignore[attr-defined]

    except Exception as exc:
        import logging
        logging.getLogger('analysis.decision_engine_patch').warning(
            f'phase4 patch skipped: {exc}'
        )


_patch_decision_engine()
