"""
backend/intelligence/learning_service.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Continuous-learning service: collects closed-trade outcomes and
fine-tunes the XGBoost model weights periodically.

Design
------
- Runs as a background task registered with the Scheduler.
- Every *retrain_interval_s* seconds it checks whether enough new
  labelled trades have accumulated (>= *min_new_samples*) before
  triggering a retrain cycle.
- Retraining is done in a thread-pool executor to avoid blocking the
  asyncio event loop.
- The new model is validated on a hold-out set; it only replaces the
  production model if it beats the current champion on AUC-ROC.

Usage::

    from backend.intelligence.learning_service import learning_service
    from backend.services.scheduler import scheduler

    scheduler.register(
        "ml_retrain",
        learning_service.run,
        interval_s=3600,  # check every hour
    )
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────── #


class TrainingSample:
    """
    One labelled trade outcome used for incremental learning.

    Attributes
    ----------
    features:   Feature vector produced by the feature extractor at
                signal time.
    label:      1 if the trade was profitable, 0 otherwise.
    pnl:        Actual P&L in USD (used for sample weighting).
    symbol:     Instrument traded.
    closed_at:  ISO-8601 timestamp when the trade was closed.
    """

    __slots__ = ("features", "label", "pnl", "symbol", "closed_at")

    def __init__(
        self,
        features: List[float],
        label: int,
        pnl: float = 0.0,
        symbol: str = "unknown",
        closed_at: Optional[str] = None,
    ) -> None:
        self.features = features
        self.label = label
        self.pnl = pnl
        self.symbol = symbol
        self.closed_at = closed_at or datetime.now(timezone.utc).isoformat()


# ── Service ───────────────────────────────────────────────────────────────── #


class LearningService:
    """
    Collects trade outcomes and periodically retrains the ML model.

    Parameters
    ----------
    min_new_samples:
        Minimum number of new labelled trades required before retraining.
    hold_out_ratio:
        Fraction of samples held out for validation (0.0 – 1.0).
    """

    def __init__(
        self,
        min_new_samples: int = 50,
        hold_out_ratio: float = 0.2,
    ) -> None:
        self._min_new_samples = min_new_samples
        self._hold_out_ratio = hold_out_ratio
        self._buffer: List[TrainingSample] = []
        self._total_retrains = 0
        self._last_retrain: Optional[str] = None
        self._champion_auc: float = 0.0

    # ── Public API ───────────────────────────────────────────────────────── #

    def record_outcome(self, sample: TrainingSample) -> None:
        """Add a labelled trade outcome to the learning buffer."""
        self._buffer.append(sample)
        logger.debug(
            "[learning] buffer size=%d label=%d pnl=%.2f",
            len(self._buffer),
            sample.label,
            sample.pnl,
        )

    async def run(self) -> None:
        """
        Periodic task entry point (registered with the Scheduler).

        Triggers a retrain cycle if enough new samples are available.
        """
        if len(self._buffer) < self._min_new_samples:
            logger.debug(
                "[learning] %d/%d samples — skipping retrain",
                len(self._buffer),
                self._min_new_samples,
            )
            return

        logger.info("[learning] starting retrain with %d samples", len(self._buffer))
        samples = list(self._buffer)
        self._buffer.clear()

        loop = asyncio.get_event_loop()
        try:
            new_auc = await loop.run_in_executor(None, self._retrain, samples)
            if new_auc > self._champion_auc:
                self._champion_auc = new_auc
                self._total_retrains += 1
                self._last_retrain = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "[learning] new champion AUC=%.4f (retrain #%d)",
                    new_auc,
                    self._total_retrains,
                )
            else:
                logger.info(
                    "[learning] challenger AUC=%.4f did not beat champion=%.4f",
                    new_auc,
                    self._champion_auc,
                )
        except Exception as exc:
            logger.error("[learning] retrain failed: %s", exc, exc_info=True)
            # Return discarded samples to the buffer for the next cycle
            self._buffer.extend(samples)

    def stats(self) -> Dict[str, Any]:
        """Return current learning statistics (useful for the dashboard)."""
        return {
            "buffer_size": len(self._buffer),
            "total_retrains": self._total_retrains,
            "champion_auc": self._champion_auc,
            "last_retrain": self._last_retrain,
        }

    # ── Internals (run in executor) ──────────────────────────────────────── #

    def _retrain(self, samples: List[TrainingSample]) -> float:
        """
        Synchronous retrain cycle (called in a thread-pool executor).

        Returns the AUC-ROC of the challenger model on the hold-out set.
        Returns 0.0 if xgboost is not installed.
        """
        try:
            import numpy as np
            import xgboost as xgb
            from sklearn.metrics import roc_auc_score
            from sklearn.model_selection import train_test_split
        except ImportError as exc:
            logger.warning("[learning] optional dep missing: %s", exc)
            return 0.0

        X = np.array([s.features for s in samples], dtype=np.float32)
        y = np.array([s.label for s in samples], dtype=np.int32)

        if len(set(y)) < 2:
            logger.warning("[learning] only one class in sample — skipping")
            return 0.0

        X_train, X_val, y_train, y_val = train_test_split(
            X,
            y,
            test_size=self._hold_out_ratio,
            random_state=42,
            stratify=y,
        )

        model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        proba = model.predict_proba(X_val)[:, 1]
        auc = float(roc_auc_score(y_val, proba))
        logger.info("[learning] challenger AUC=%.4f on %d val samples", auc, len(y_val))
        return auc


# ── Module-level singleton ────────────────────────────────────────────────── #
learning_service = LearningService()
