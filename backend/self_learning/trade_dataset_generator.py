"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Trade Dataset Generator
هدف: ذخیره معاملات بسته‌شده در PostgreSQL و ساخت Dataset برای ML
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
import numpy as np

from ..core.logger import get_logger

logger = get_logger("self_learning.dataset_generator")


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class TradeDirection(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


class TradeResult(str, Enum):
    WIN  = "WIN"
    LOSS = "LOSS"
    BE   = "BE"          # Break Even


class MarketSession(str, Enum):
    ASIAN   = "ASIAN"
    LONDON  = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP  = "OVERLAP"
    OFF      = "OFF"


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SMCFeatures:
    """ویژگی‌های Smart Money Concept در زمان ورود."""
    bos_detected:          bool  = False
    bos_strength:          float = 0.0   # 0.0 – 1.0
    choch_detected:        bool  = False
    choch_strength:        float = 0.0
    order_block_present:   bool  = False
    order_block_quality:   float = 0.0
    order_block_tested:    bool  = False
    breaker_block:         bool  = False
    fvg_present:           bool  = False
    fvg_quality:           float = 0.0
    ifvg_present:          bool  = False
    liquidity_sweep:       bool  = False
    sweep_quality:         float = 0.0
    internal_liquidity:    bool  = False
    external_liquidity:    bool  = False
    in_premium_zone:       bool  = False
    in_discount_zone:      bool  = False
    equilibrium_distance:  float = 0.0
    structure_score:       float = 0.0


@dataclass
class MarketConditions:
    """شرایط بازار در زمان ورود به معامله."""
    symbol:            str          = "XAUUSD"
    session:           MarketSession = MarketSession.OFF
    in_kill_zone:      bool         = False
    atr_value:         float        = 0.0
    atr_normalized:    float        = 0.0   # ATR / price
    spread_pips:       float        = 0.0
    spread_ratio:      float        = 0.0   # spread / ATR
    volatility_ratio:  float        = 1.0   # current / avg volatility
    trend_direction:   int          = 0     # 1=UP, -1=DOWN, 0=NEUTRAL
    trend_strength:    float        = 0.0
    htf_alignment:     bool         = False
    htf_score:         float        = 0.0
    hour_of_day:       int          = 0
    day_of_week:       int          = 0     # 0=Monday
    news_active:       bool         = False


@dataclass
class TradeRecord:
    """رکورد کامل یک معامله بسته‌شده."""
    # شناسه‌ها
    trade_id:         str       = field(default_factory=lambda: str(uuid.uuid4()))
    mt5_ticket:       int       = 0

    # اطلاعات معامله
    symbol:           str       = "XAUUSD"
    direction:        TradeDirection = TradeDirection.BUY
    result:           TradeResult   = TradeResult.LOSS

    # قیمت‌ها
    entry_price:      float = 0.0
    exit_price:       float = 0.0
    stop_loss:        float = 0.0
    take_profit:      float = 0.0
    lot_size:         float = 0.01

    # نتیجه مالی
    profit_loss:      float = 0.0
    profit_pips:      float = 0.0
    risk_reward_actual: float = 0.0

    # زمان
    entry_time:       datetime = field(default_factory=datetime.utcnow)
    exit_time:        datetime = field(default_factory=datetime.utcnow)
    duration_minutes: int      = 0

    # امتیاز سیستم
    confidence_score: float = 0.0
    decision_score:   float = 0.0

    # ویژگی‌های ML
    smc:              SMCFeatures     = field(default_factory=SMCFeatures)
    market:           MarketConditions = field(default_factory=MarketConditions)

    # متادیتا
    model_version:    str = "unknown"
    is_rule_violation: bool = False
    violation_reason: str  = ""
    created_at:       datetime = field(default_factory=datetime.utcnow)

    def to_ml_features(self) -> Dict[str, float]:
        """تبدیل رکورد به ۳۸ ویژگی عددی برای ML."""
        s = self.smc
        m = self.market
        return {
            # SMC
            "bos":              float(s.bos_detected),
            "bos_strength":     s.bos_strength,
            "choch":            float(s.choch_detected),
            "choch_strength":   s.choch_strength,
            "structure_score":  s.structure_score,
            "structure_count":  float(s.bos_detected) + float(s.choch_detected),
            # Order Block
            "ob_present":       float(s.order_block_present),
            "ob_quality":       s.order_block_quality,
            "ob_tested":        float(s.order_block_tested),
            "breaker":          float(s.breaker_block),
            # FVG
            "fvg_present":      float(s.fvg_present),
            "fvg_quality":      s.fvg_quality,
            "ifvg":             float(s.ifvg_present),
            # نقدینگی
            "sweep":            float(s.liquidity_sweep),
            "sweep_quality":    s.sweep_quality,
            "internal_liq":     float(s.internal_liquidity),
            "external_liq":     float(s.external_liquidity),
            # موقعیت قیمت
            "in_discount":      float(s.in_discount_zone),
            "in_premium":       float(s.in_premium_zone),
            "eq_distance":      s.equilibrium_distance,
            # بازار
            "atr_norm":         m.atr_normalized,
            "spread_ratio":     m.spread_ratio,
            "volatility_ratio": m.volatility_ratio,
            "trend_strength":   m.trend_strength,
            "htf_aligned":      float(m.htf_alignment),
            "htf_score":        m.htf_score,
            # زمان
            "session_quality":  self._session_quality(m.session),
            "kill_zone":        float(m.in_kill_zone),
            "hour_sin":         np.sin(2 * np.pi * m.hour_of_day / 24),
            "hour_cos":         np.cos(2 * np.pi * m.hour_of_day / 24),
            "day_of_week":      float(m.day_of_week),
            # کلی
            "confidence_score": self.confidence_score / 100.0,
            "decision_score":   self.decision_score / 100.0,
            "duration_min":     float(min(self.duration_minutes, 1440)) / 1440.0,
            "news_active":      float(m.news_active),
            "lot_norm":         min(self.lot_size, 10.0) / 10.0,
            "rr_planned":       min(abs(self.take_profit - self.entry_price) /
                                    max(abs(self.stop_loss - self.entry_price), 0.0001), 10.0) / 10.0,
            "is_rule_violation": float(self.is_rule_violation),
        }

    @staticmethod
    def _session_quality(session: MarketSession) -> float:
        weights = {
            MarketSession.OVERLAP:  1.0,
            MarketSession.LONDON:   0.85,
            MarketSession.NEW_YORK: 0.80,
            MarketSession.ASIAN:    0.40,
            MarketSession.OFF:      0.10,
        }
        return weights.get(session, 0.10)

    def is_win(self) -> bool:
        return self.result == TradeResult.WIN


# ─────────────────────────────────────────────────────────────────────────────
# Trade Dataset Generator
# ─────────────────────────────────────────────────────────────────────────────

class TradeDatasetGenerator:
    """
    ذخیره معاملات بسته‌شده در PostgreSQL و تولید Dataset برای ML.

    مسئولیت‌ها:
    • ذخیره هر معامله با تمام context آن
    • ساخت numpy dataset برای training
    • فیلتر معاملات valid (بدون نقض قوانین)
    • بازیابی dataset بر اساس symbol / timerange
    """

    # DDL — ساختار جدول
    _CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS self_learning_trades (
            trade_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            mt5_ticket        BIGINT       NOT NULL DEFAULT 0,
            symbol            VARCHAR(20)  NOT NULL,
            direction         VARCHAR(4)   NOT NULL,
            result            VARCHAR(4)   NOT NULL,
            entry_price       NUMERIC(20,8) NOT NULL,
            exit_price        NUMERIC(20,8) NOT NULL,
            stop_loss         NUMERIC(20,8) NOT NULL DEFAULT 0,
            take_profit       NUMERIC(20,8) NOT NULL DEFAULT 0,
            lot_size          NUMERIC(10,4) NOT NULL,
            profit_loss       NUMERIC(12,4) NOT NULL,
            profit_pips       NUMERIC(10,2) NOT NULL DEFAULT 0,
            risk_reward_actual NUMERIC(8,4) NOT NULL DEFAULT 0,
            entry_time        TIMESTAMPTZ  NOT NULL,
            exit_time         TIMESTAMPTZ  NOT NULL,
            duration_minutes  INTEGER      NOT NULL DEFAULT 0,
            confidence_score  NUMERIC(5,2) NOT NULL DEFAULT 0,
            decision_score    NUMERIC(5,2) NOT NULL DEFAULT 0,
            smc_features      JSONB        NOT NULL DEFAULT '{}',
            market_conditions JSONB        NOT NULL DEFAULT '{}',
            ml_features       JSONB        NOT NULL DEFAULT '{}',
            model_version     VARCHAR(50)  NOT NULL DEFAULT 'unknown',
            is_rule_violation BOOLEAN      NOT NULL DEFAULT FALSE,
            violation_reason  TEXT         NOT NULL DEFAULT '',
            created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_slt_symbol    ON self_learning_trades (symbol);
        CREATE INDEX IF NOT EXISTS idx_slt_result    ON self_learning_trades (result);
        CREATE INDEX IF NOT EXISTS idx_slt_entry     ON self_learning_trades (entry_time);
        CREATE INDEX IF NOT EXISTS idx_slt_valid     ON self_learning_trades (symbol, is_rule_violation);
    """

    def __init__(self, db_pool: asyncpg.Pool) -> None:
        self._pool = db_pool
        logger.info("TradeDatasetGenerator initialized")

    # ─── Schema ───────────────────────────────────────────────────────────────

    async def ensure_schema(self) -> None:
        """اطمینان از وجود جدول در PostgreSQL."""
        async with self._pool.acquire() as conn:
            await conn.execute(self._CREATE_TABLE_SQL)
        logger.info("self_learning_trades schema ready")

    # ─── ذخیره ───────────────────────────────────────────────────────────────

    async def save_trade(self, record: TradeRecord) -> str:
        """ذخیره یک معامله بسته‌شده در PostgreSQL."""
        ml_features = record.to_ml_features()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO self_learning_trades (
                    trade_id, mt5_ticket, symbol, direction, result,
                    entry_price, exit_price, stop_loss, take_profit, lot_size,
                    profit_loss, profit_pips, risk_reward_actual,
                    entry_time, exit_time, duration_minutes,
                    confidence_score, decision_score,
                    smc_features, market_conditions, ml_features,
                    model_version, is_rule_violation, violation_reason
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                    $11,$12,$13,$14,$15,$16,$17,$18,
                    $19,$20,$21,$22,$23,$24
                )
                ON CONFLICT (trade_id) DO UPDATE SET
                    result            = EXCLUDED.result,
                    exit_price        = EXCLUDED.exit_price,
                    profit_loss       = EXCLUDED.profit_loss,
                    profit_pips       = EXCLUDED.profit_pips,
                    risk_reward_actual= EXCLUDED.risk_reward_actual,
                    exit_time         = EXCLUDED.exit_time,
                    duration_minutes  = EXCLUDED.duration_minutes,
                    ml_features       = EXCLUDED.ml_features
                RETURNING trade_id
                """,
                record.trade_id, record.mt5_ticket,
                record.symbol, record.direction.value, record.result.value,
                record.entry_price, record.exit_price,
                record.stop_loss, record.take_profit, record.lot_size,
                record.profit_loss, record.profit_pips, record.risk_reward_actual,
                record.entry_time, record.exit_time, record.duration_minutes,
                record.confidence_score, record.decision_score,
                json.dumps(asdict(record.smc)),
                json.dumps({
                    "symbol":          record.market.symbol,
                    "session":         record.market.session.value,
                    "in_kill_zone":    record.market.in_kill_zone,
                    "atr_value":       record.market.atr_value,
                    "atr_normalized":  record.market.atr_normalized,
                    "spread_pips":     record.market.spread_pips,
                    "spread_ratio":    record.market.spread_ratio,
                    "volatility_ratio":record.market.volatility_ratio,
                    "trend_direction": record.market.trend_direction,
                    "trend_strength":  record.market.trend_strength,
                    "htf_alignment":   record.market.htf_alignment,
                    "htf_score":       record.market.htf_score,
                    "hour_of_day":     record.market.hour_of_day,
                    "day_of_week":     record.market.day_of_week,
                    "news_active":     record.market.news_active,
                }),
                json.dumps(ml_features),
                record.model_version,
                record.is_rule_violation,
                record.violation_reason,
            )

        trade_id = str(row["trade_id"])
        logger.info(f"Trade saved: {trade_id} | {record.symbol} {record.result.value} | P/L={record.profit_loss:.2f}")
        return trade_id

    # ─── Dataset ──────────────────────────────────────────────────────────────

    async def build_dataset(
        self,
        symbol:              Optional[str]      = None,
        valid_only:          bool               = True,
        min_confidence:      float              = 0.0,
        start_date:          Optional[datetime] = None,
        end_date:            Optional[datetime] = None,
        exclude_be:          bool               = True,
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        ساخت (X, y, feature_names) برای training.

        Returns:
            X:             (n_samples, n_features) float64
            y:             (n_samples,) int   — 1=WIN, 0=LOSS
            feature_names: لیست نام ویژگی‌ها
        """
        conditions = ["ml_features != '{}'"]
        params: List[Any] = []
        idx = 1

        if symbol:
            conditions.append(f"symbol = ${idx}")
            params.append(symbol); idx += 1

        if valid_only:
            conditions.append("is_rule_violation = FALSE")

        if exclude_be:
            conditions.append("result != 'BE'")

        if min_confidence > 0:
            conditions.append(f"confidence_score >= ${idx}")
            params.append(min_confidence); idx += 1

        if start_date:
            conditions.append(f"entry_time >= ${idx}")
            params.append(start_date); idx += 1

        if end_date:
            conditions.append(f"entry_time <= ${idx}")
            params.append(end_date); idx += 1

        where = " AND ".join(conditions)
        query = f"""
            SELECT ml_features, result
            FROM   self_learning_trades
            WHERE  {where}
            ORDER  BY entry_time ASC
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        if not rows:
            logger.warning(f"Dataset empty for symbol={symbol}")
            return np.array([]), np.array([]), []

        feature_rows: List[Dict[str, float]] = []
        labels: List[int] = []

        for row in rows:
            features = json.loads(row["ml_features"])
            feature_rows.append(features)
            labels.append(1 if row["result"] == "WIN" else 0)

        feature_names = sorted(feature_rows[0].keys())
        X = np.array(
            [[r.get(k, 0.0) for k in feature_names] for r in feature_rows],
            dtype=np.float64,
        )
        y = np.array(labels, dtype=np.int32)

        logger.info(f"Dataset built: {len(X)} samples | symbol={symbol or 'ALL'} | win_rate={y.mean():.2%}")
        return X, y, feature_names

    # ─── آمار ─────────────────────────────────────────────────────────────────

    async def get_statistics(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """آمار کلی معاملات ذخیره‌شده."""
        params: List[Any] = []
        where = "WHERE is_rule_violation = FALSE"
        if symbol:
            where += " AND symbol = $1"
            params.append(symbol)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT
                    COUNT(*)                                              AS total,
                    COUNT(*) FILTER (WHERE result = 'WIN')               AS wins,
                    COUNT(*) FILTER (WHERE result = 'LOSS')              AS losses,
                    COUNT(*) FILTER (WHERE result = 'BE')                AS be_count,
                    ROUND(AVG(profit_pips)::numeric, 2)                  AS avg_pips,
                    ROUND(AVG(confidence_score)::numeric, 2)             AS avg_confidence,
                    ROUND(AVG(risk_reward_actual)::numeric, 4)           AS avg_rr,
                    MIN(entry_time)                                       AS first_trade,
                    MAX(entry_time)                                       AS last_trade
                FROM self_learning_trades
                {where}
                """,
                *params,
            )

        total = row["total"] or 1
        return {
            "total_trades":    row["total"],
            "wins":            row["wins"],
            "losses":          row["losses"],
            "be_count":        row["be_count"],
            "win_rate":        round(row["wins"] / total, 4),
            "avg_pips":        float(row["avg_pips"] or 0),
            "avg_confidence":  float(row["avg_confidence"] or 0),
            "avg_rr":          float(row["avg_rr"] or 0),
            "first_trade":     row["first_trade"].isoformat() if row["first_trade"] else None,
            "last_trade":      row["last_trade"].isoformat()  if row["last_trade"]  else None,
            "symbol":          symbol or "ALL",
        }

    async def count_trades(self, symbol: Optional[str] = None, valid_only: bool = True) -> int:
        """تعداد معاملات ذخیره‌شده."""
        params: List[Any] = []
        conditions = ["1=1"]
        if symbol:
            conditions.append("symbol = $1")
            params.append(symbol)
        if valid_only:
            conditions.append("is_rule_violation = FALSE")
        where = " AND ".join(conditions)

        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                f"SELECT COUNT(*) FROM self_learning_trades WHERE {where}", *params
            )
        return count or 0
