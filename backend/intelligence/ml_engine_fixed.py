"""
intelligence/ml_engine_fixed.py -- Async Training Wrapper
Phase D Fix (TECH-4):

PROBLEM:
  MLEngine.train() calls sklearn GradientBoostingClassifier.fit()
  which is CPU-bound (50-500ms). Running it in async context blocks
  the event loop, stalling all WebSocket + API responses.

SOLUTION:
  Patches MLEngine and UnifiedMLEngine with .train_async() that uses
  asyncio.to_thread(). Also provides standalone helper.

USAGE:
  from backend.intelligence.ml_engine_fixed import train_ml_engine_async
  result = await train_ml_engine_async(ml_engine_instance, contexts)
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, List

logger = logging.getLogger(__name__)


def _patch_ml_engine_async() -> None:
    """Patch MLEngine/UnifiedMLEngine with train_async(). Idempotent."""
    try:
        _mod = sys.modules.get("backend.intelligence.ml_engine")
        if _mod is None:
            try:
                from backend.intelligence import ml_engine as _mod  # type: ignore[assignment]
            except ImportError:
                logger.warning("ml_engine_fixed: ml_engine module not found -- skip patch")
                return

        for cls_name in ("MLEngine", "UnifiedMLEngine"):
            cls = getattr(_mod, cls_name, None)
            if cls is None or getattr(cls, "_async_patched", False):
                continue
            _orig = cls.train

            def _make(orig):
                async def train_async(self, contexts: List[Any]) -> Any:
                    """Offloads CPU-bound sklearn training to thread pool."""
                    return await asyncio.to_thread(orig, self, contexts)
                return train_async

            cls.train_async = _make(_orig)
            cls._async_patched = True
            logger.debug("%s.train_async patched", cls_name)

    except Exception as exc:
        logger.warning("ml_engine_fixed: patch failed -- %s", exc)


_patch_ml_engine_async()


async def train_ml_engine_async(engine: Any, contexts: List[Any]) -> Any:
    """
    Async wrapper for any MLEngine-compatible object.
    Prefers .train_async() if available, else asyncio.to_thread(engine.train).
    """
    if hasattr(engine, "train_async"):
        return await engine.train_async(contexts)
    return await asyncio.to_thread(engine.train, contexts)


async def should_retrain_async(engine: Any) -> bool:
    """Non-blocking readiness check."""
    fn = getattr(engine, "should_retrain", None)
    if fn is None:
        return False
    if asyncio.iscoroutinefunction(fn):
        return await fn()
    return bool(fn())
