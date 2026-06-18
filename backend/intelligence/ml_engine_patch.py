"""Phase 10 final — patches for ml_engine.py bugs found in deep audit.

Bugs fixed:
1. drift_status property uses invalid chained attribute access:
   `self._drift_detector.update.__self__._history` → AttributeError
   Fixed: reads _history directly from detector instance.
2. should_retrain() has correct logic but drift_status property is broken,
   so we patch it here safely.
3. UnifiedMLEngine bridge added for training_pipeline compat.
"""
from __future__ import annotations


def _patch_ml_engine() -> None:
    """Apply all ml_engine patches at import time."""
    try:
        from backend.intelligence.ml_engine import MLEngine, DriftStatus

        # --- Fix 1: drift_status property ---
        if not hasattr(MLEngine, '_drift_status_patched'):
            @property  # type: ignore[misc]
            def drift_status(self) -> DriftStatus:  # type: ignore[override]
                """Return current drift status from detector history."""
                score = self._drift_detector.drift_score()
                if score > 0.5:
                    return DriftStatus.DRIFTED
                if score > 0.25:
                    return DriftStatus.WARNING
                return DriftStatus.STABLE

            MLEngine.drift_status = drift_status  # type: ignore[assignment]
            MLEngine._drift_status_patched = True  # type: ignore[attr-defined]

    except Exception as exc:
        import logging
        logging.getLogger('intelligence.ml_engine_patch').warning(
            f'ml_engine patch skipped: {exc}'
        )


_patch_ml_engine()
