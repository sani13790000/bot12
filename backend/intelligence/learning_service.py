"""
intelligence/learning_service.py -- Re-export Shim
Phase D Fix (ARCH-5):

Canonical LearningService implementation consolidated into
backend/self_learning/learning_service.py.

This file is a backward-compatibility shim.
DO NOT add business logic here.
"""
from __future__ import annotations

from backend.self_learning.learning_service import (  # noqa: F401
    LearningService,
    LearningCycleResult,
    LearningStats,
)

__all__ = ["LearningService", "LearningCycleResult", "LearningStats"]
