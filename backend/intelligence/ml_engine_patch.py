"""
backend/intelligence/ml_engine_patch.py — Phase S patches
S-1a: walk-forward embargo (purge gap) — prevent lookahead leakage
S-1b: asyncio.to_thread() instead of loop.run_in_executor(None, ...)
S-1c: concurrent train/predict lock — prevent race on shared model state
S-1d: walk-forward split guard — raise if data too small

Backward compatible — no public API changes.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("intelligence.ml_engine")


def walk_forward_with_embargo(
    X: List,
    y: List,
    n_splits: int = 5,
    embargo_pct: float = 0.01,
) -> List[Tuple[List, List, List, List]]:
    """
    Walk-forward cross-validation with embargo/purge gap.

    Returns list of (X_train, y_train, X_test, y_test) tuples.
    Embargo gap = max(1, ceil(n * embargo_pct)) bars between train_end and test_start.
    """
    n = len(X)
    if n < n_splits * 4:
        raise ValueError(
            f"Not enough data for {n_splits} splits with embargo. "
            f"Need at least {n_splits * 4} samples, got {n}."
        )

    embargo_size = max(1, math.ceil(n * embargo_pct))
    split_size   = n // (n_splits + 1)
    folds: List[Tuple[List, List, List, List]] = []

    for i in range(n_splits):
        train_end  = split_size * (i + 1)
        test_start = train_end + embargo_size
        test_end   = min(test_start + split_size, n)

        if test_end <= test_start:
            logger.warning(
                "walk_forward_embargo: fold %d skipped — test_end(%d) <= test_start(%d)",
                i, test_end, test_start,
            )
            continue

        folds.append((
            X[:train_end],
            y[:train_end],
            X[test_start:test_end],
            y[test_start:test_end],
        ))
        logger.debug(
            "fold %d: train[0:%d] embargo[%d:%d] test[%d:%d]",
            i, train_end, train_end, test_start, test_start, test_end,
        )

    if not folds:
        raise ValueError("walk_forward_embargo produced 0 folds — check data size")

    return folds


class AsyncMLMixin:
    """
    Mixin for ML classes to add:
      - asyncio.to_thread() async wrappers (S-1b)
      - asyncio.Lock per instance (S-1c)
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._ml_lock: asyncio.Lock = asyncio.Lock()

    async def train_async(self, trade_contexts: List[Dict]) -> Any:
        """S-1b: non-blocking train via asyncio.to_thread."""
        async with self._ml_lock:
            return await asyncio.to_thread(self.train, trade_contexts)

    async def predict_async(self, features: Dict) -> Any:
        """S-1b: non-blocking predict via asyncio.to_thread."""
        async with self._ml_lock:
            return await asyncio.to_thread(self.predict, features)


def patch_ml_engine_class(cls: type) -> type:
    """
    Monkey-patch an existing MLEngine class to use:
      - walk_forward_with_embargo() (S-1a)
      - asyncio.to_thread() (S-1b)
      - per-instance asyncio.Lock (S-1c)
    Returns the patched class (same object).
    """
    import asyncio as _asyncio

    original_init = cls.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if not hasattr(self, "_ml_lock"):
            self._ml_lock = _asyncio.Lock()

    cls.__init__ = patched_init

    async def train_async(self, trade_contexts):
        async with self._ml_lock:
            return await _asyncio.to_thread(self.train, trade_contexts)

    async def predict_async(self, features):
        async with self._ml_lock:
            return await _asyncio.to_thread(self.predict, features)

    cls.train_async   = train_async
    cls.predict_async = predict_async

    if hasattr(cls, "_walk_forward_splits"):
        def _walk_forward_splits_patched(self, X, y):
            try:
                return walk_forward_with_embargo(
                    X, y,
                    n_splits=getattr(self, "WALK_FORWARD_SPLITS", 5),
                    embargo_pct=0.01,
                )
            except ValueError as exc:
                logger.warning("walk_forward_embargo: %s", exc)
                return []
        cls._walk_forward_splits = _walk_forward_splits_patched

    logger.debug("MLEngine class patched (S-1a/b/c): %s", cls.__name__)
    return cls
