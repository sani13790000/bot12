"""
decision_engine_patch.py — ARCH-9 Fix (Phase D)

BEFORE: monkey-patched DecisionEngine.make_decision at module load.
        Also added SMCScoreResult.order_block_count + fvg_count as properties.
        Fragile: mypy errors, fails on module reload, hidden coupling.

AFTER:  Both make_decision() and order_block_count/fvg_count are REAL
        methods/properties defined directly in decision_engine.py.
        This file is now a no-op kept only for backward import compatibility.
        Safe to import — will NOT re-patch anything.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
logger.debug(
    "decision_engine_patch imported — no-op (patching moved to decision_engine.py)"
)
