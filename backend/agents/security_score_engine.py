"""
agents/security_score_engine.py -- Re-export Shim
Phase D Fix (ARCH-6):

BEFORE: Two duplicate SecurityScoreEngine implementations.
AFTER:  Canonical stays in security_reporting/security_score_engine.py.
        This shim exists only for backward-compat imports.

DO NOT add logic here.
"""

from __future__ import annotations

from backend.security_reporting.security_score_engine import (  # noqa: F401
    ScoreDimension,
    SecurityScore,
    SecurityScoreEngine,
    security_score_engine,
)

__all__ = [
    "SecurityScoreEngine",
    "SecurityScore",
    "ScoreDimension",
    "security_score_engine",
]
