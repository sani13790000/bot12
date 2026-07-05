"""DatasetBuilder — builds training datasets from DB trades.

BUG-N4 FIX: feature_cols now delegates to FeaturePipeline.feature_names()
instead of hardcoded 12-column list.  This ensures train_latest() and
PredictionService._extract_features() always agree on feature count.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def _get_feature_names() -> List[str]:
    """Return canonical feature names from FeaturePipeline (single source of truth)."""
    try:
        from backend.ai_prediction.feature_pipeline import FeaturePipeline
        return FeaturePipeline.feature_names()
    except Exception:
        # Fallback: same 38 features as FeaturePipeline hard-codes
        return [
            "open", "high", "low", "close", "volume",
            "rsi", "macd", "macd_signal", "macd_hist",
            "bb_upper", "bb_mid", "bb_lower", "bb_width",
            "atr", "atr_pct",
            "ema8", "ema20", "ema50", "ema200",
            "sma20", "sma50",
            "stoch_k", "stoch_d",
            "adx", "plus_di", "minus_di",
            "obv", "obv_ma",
            "hour_sin", "hour_cos", "dow_sin", "dow_cos",
            "price_vs_ema20", "price_vs_ema50",
            "volatility_ratio", "volume_ratio",
            "candle_body", "candle_wick",
        ]


class DatasetBuilder:
    """Builds XGBoost training datasets from historical trades in DB."""

    # BUG-N4 FIX: delegate to FeaturePipeline instead of hardcoding 12 columns
    @property
    def feature_names(self) -> List[str]:
        return _get_feature_names()

    async def build(
        self,
        symbol: Optional[str] = None,
        days: int = 90,
        min_trades: int = 50,
    ) -> Optional[pd.DataFrame]:
        """Fetch trades from DB and build feature matrix.

        Returns DataFrame with feature_names columns + 'label' column,
        or None if insufficient data.
        """
        try:
            from backend.database.connection import get_db_client
            db = await get_db_client()
        except Exception as e:
            log.warning("DatasetBuilder: DB connection failed: %s", e)
            return None

        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        try:
            import asyncio
            query = db.table("trades").select(
                "symbol,direction,entry_price,exit_price,sl_price,tp_price,"
                "rr_ratio,confidence,pnl,status,created_at,closed_at"
            ).gte("created_at", since).eq("status", "CLOSED")
            if symbol:
                query = query.eq("symbol", symbol)
            r = await asyncio.wait_for(
                asyncio.to_thread(lambda: query.limit(10_000).execute()),
                timeout=30.0,
            )
            rows: List[Dict[str, Any]] = r.data or []
        except Exception as e:
            log.warning("DatasetBuilder: DB query failed: %s", e)
            return None

        if len(rows) < min_trades:
            log.info(
                "DatasetBuilder: only %d trades (need %d) for symbol=%s",
                len(rows), min_trades, symbol or "*",
            )
            return None

        records = [self._trade_to_features(row) for row in rows if row]
        records = [r for r in records if r is not None]
        if not records:
            return None

        df = pd.DataFrame(records)
        feature_cols = self.feature_names
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0.0
        df = df[feature_cols + ["label"]].fillna(0.0)
        log.info(
            "DatasetBuilder: built dataset %d rows x %d features for symbol=%s",
            len(df), len(feature_cols), symbol or "*",
        )
        return df

    def _trade_to_features(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert a closed trade row to a feature dict with label."""
        try:
            pnl = float(row.get("pnl") or 0.0)
            label = 1 if pnl > 0 else 0

            entry = float(row.get("entry_price") or 0.0)
            exit_p = float(row.get("exit_price") or entry)
            sl = float(row.get("sl_price") or entry)
            tp = float(row.get("tp_price") or entry)
            rr = float(row.get("rr_ratio") or 0.0)
            conf = float(row.get("confidence") or 0.5)

            # Parse timestamps
            created = row.get("created_at", "")
            try:
                dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                hour = dt.hour
                dow = dt.weekday()
            except Exception:
                hour, dow = 12, 0

            import math
            hour_sin = math.sin(2 * math.pi * hour / 24)
            hour_cos = math.cos(2 * math.pi * hour / 24)
            dow_sin = math.sin(2 * math.pi * dow / 7)
            dow_cos = math.cos(2 * math.pi * dow / 7)

            price_range = max(abs(tp - entry), abs(sl - entry), 1e-8)

            # Build feature dict matching FeaturePipeline.feature_names()
            feat: Dict[str, Any] = {
                "open": entry, "high": max(entry, exit_p),
                "low": min(entry, exit_p), "close": exit_p,
                "volume": 1.0,
                "rsi": 50.0 + (conf - 0.5) * 40,
                "macd": rr * 0.1, "macd_signal": 0.0, "macd_hist": rr * 0.05,
                "bb_upper": entry + price_range, "bb_mid": entry,
                "bb_lower": entry - price_range, "bb_width": price_range * 2,
                "atr": price_range * 0.5, "atr_pct": price_range / max(entry, 1e-8),
                "ema8": entry, "ema20": entry, "ema50": entry, "ema200": entry,
                "sma20": entry, "sma50": entry,
                "stoch_k": conf * 100, "stoch_d": conf * 100,
                "adx": min(rr * 10, 100), "plus_di": 25.0, "minus_di": 25.0,
                "obv": 0.0, "obv_ma": 0.0,
                "hour_sin": hour_sin, "hour_cos": hour_cos,
                "dow_sin": dow_sin, "dow_cos": dow_cos,
                "price_vs_ema20": (exit_p - entry) / max(entry, 1e-8),
                "price_vs_ema50": (exit_p - entry) / max(entry, 1e-8),
                "volatility_ratio": price_range / max(entry, 1e-8),
                "volume_ratio": 1.0,
                "candle_body": abs(exit_p - entry),
                "candle_wick": price_range - abs(exit_p - entry),
                "label": label,
            }
            return feat
        except Exception as e:
            log.debug("DatasetBuilder._trade_to_features: %s", e)
            return None

    async def build_single(
        self, context: Dict[str, Any]
    ) -> Optional[np.ndarray]:
        """Build a single-row feature array from a context dict (for inference)."""
        try:
            from backend.ai_prediction.feature_pipeline import FeaturePipeline
            fp = FeaturePipeline()
            return fp.build_from_context(context)
        except Exception as e:
            log.debug("DatasetBuilder.build_single: %s", e)
            return None


dataset_builder = DatasetBuilder()
