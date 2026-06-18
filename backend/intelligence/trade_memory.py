from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("intelligence.trade_memory")


class TradeOutcome(str, Enum):
    WIN       = "WIN"
    LOSS      = "LOSS"
    BREAKEVEN = "BE"
    PARTIAL   = "PARTIAL"


class MarketSession(str, Enum):
    ASIAN             = "ASIAN"
    LONDON            = "LONDON"
    NEW_YORK          = "NEW_YORK"
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"
    OFF_HOURS         = "OFF_HOURS"


class MarketCondition(str, Enum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGING          = "RANGING"
    HIGH_VOLATILITY  = "HIGH_VOLATILITY"
    LOW_VOLATILITY   = "LOW_VOLATILITY"
    POST_NEWS        = "POST_NEWS"


@dataclass
class SMCContext:
    bos_detected:        bool  = False
    choch_detected:      bool  = False
    order_block_quality: float = 0.0
    fvg_quality:         float = 0.0
    liquidity_swept:     bool  = False
    in_premium_zone:     bool  = False
    in_discount_zone:    bool  = False
    kill_zone_active:    bool  = False
    structure_score:     float = 0.0
    htf_alignment:       float = 0.0


@dataclass
class PAContext:
    primary_pattern:       str       = ""
    pattern_quality:       float     = 0.0
    confirmation_patterns: List[str] = field(default_factory=list)
    rejection_strength:    float     = 0.0
    momentum_alignment:    bool      = False


@dataclass
class RiskContext:
    lot_size:                float = 0.0
    risk_percent:            float = 0.0
    stop_loss_pips:          float = 0.0
    take_profit_pips:        float = 0.0
    risk_reward_ratio:       float = 0.0
    portfolio_risk_at_entry: float = 0.0
    atr_at_entry:            float = 0.0
    spread_at_entry:         float = 0.0


@dataclass
class TradeContext:
    trade_id:   str = field(default_factory=lambda: str(uuid.uuid4()))
    signal_id:  str = ""
    symbol:     str = ""
    entry_time:       Optional[datetime] = None
    exit_time:        Optional[datetime] = None
    duration_minutes: float = 0.0
    entry_price:  float = 0.0
    exit_price:   float = 0.0
    stop_loss:    float = 0.0
    take_profit:  float = 0.0
    direction:    str   = ""
    outcome:      TradeOutcome    = TradeOutcome.LOSS
    pnl_pips:     float = 0.0
    pnl_usd:      float = 0.0
    realized_rr:  float = 0.0
    confidence_score: float = 0.0
    session:          MarketSession   = MarketSession.OFF_HOURS
    market_condition: MarketCondition = MarketCondition.RANGING
    smc:          SMCContext  = field(default_factory=SMCContext)
    price_action: PAContext   = field(default_factory=PAContext)
    risk:         RiskContext = field(default_factory=RiskContext)
    news_active:                 bool = False
    previous_consecutive_losses: int  = 0
    notes:                       str  = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.entry_time:
            data["entry_time"] = self.entry_time.isoformat()
        if self.exit_time:
            data["exit_time"] = self.exit_time.isoformat()
        return data

    def to_ml_features(self) -> Dict[str, float]:
        session_map = {
            MarketSession.ASIAN: 0, MarketSession.LONDON: 1,
            MarketSession.NEW_YORK: 2, MarketSession.LONDON_NY_OVERLAP: 3,
            MarketSession.OFF_HOURS: 4,
        }
        condition_map = {
            MarketCondition.TRENDING_BULLISH: 0, MarketCondition.TRENDING_BEARISH: 1,
            MarketCondition.RANGING: 2, MarketCondition.HIGH_VOLATILITY: 3,
            MarketCondition.LOW_VOLATILITY: 4, MarketCondition.POST_NEWS: 5,
        }
        return {
            "bos_detected":              float(self.smc.bos_detected),
            "choch_detected":            float(self.smc.choch_detected),
            "order_block_quality":       self.smc.order_block_quality,
            "fvg_quality":               self.smc.fvg_quality,
            "liquidity_swept":           float(self.smc.liquidity_swept),
            "in_premium_zone":           float(self.smc.in_premium_zone),
            "in_discount_zone":          float(self.smc.in_discount_zone),
            "kill_zone_active":          float(self.smc.kill_zone_active),
            "structure_score":           self.smc.structure_score,
            "htf_alignment":             self.smc.htf_alignment,
            "pattern_quality":           self.price_action.pattern_quality,
            "rejection_strength":        self.price_action.rejection_strength,
            "momentum_alignment":        float(self.price_action.momentum_alignment),
            "num_confirmation_patterns": float(len(self.price_action.confirmation_patterns)),
            "risk_percent":              self.risk.risk_percent,
            "risk_reward_ratio":         self.risk.risk_reward_ratio,
            "portfolio_risk_at_entry":   self.risk.portfolio_risk_at_entry,
            "atr_normalized":            self.risk.atr_at_entry / max(self.entry_price, 1e-9),
            "spread_normalized":         self.risk.spread_at_entry / max(self.risk.atr_at_entry, 1e-9),
            "confidence_score":          self.confidence_score / 100.0,
            "session":                   float(session_map.get(self.session, 4)),
            "market_condition":          float(condition_map.get(self.market_condition, 2)),
            "news_active":               float(self.news_active),
            "previous_consecutive_losses": float(min(self.previous_consecutive_losses, 10)),
            "duration_minutes":          min(self.duration_minutes / 1440.0, 1.0),
        }


class TradeMemory:
    _DB_TABLE = "trade_memory"

    def __init__(self, max_memory: int = 10_000) -> None:
        self._max_memory = max_memory
        self._memory: List[TradeContext] = []
        self._db_available = False
        logger.info(f"TradeMemory initialized — capacity: {max_memory}")

    async def initialize(self) -> None:
        try:
            from ..database import db
            rows = await db.select_many(
                self._DB_TABLE,
                order_by="entry_time",
                order_desc=True,
                limit=self._max_memory,
            )
            if rows:
                loaded = []
                for row in reversed(rows):
                    try:
                        loaded.append(self._row_to_context(row))
                    except Exception as exc:
                        logger.debug(f"Skipping bad DB row: {exc}")
                self._memory = loaded
                self._db_available = True
                logger.info(f"TradeMemory: loaded {len(loaded)} trades from DB")
            else:
                self._db_available = True
                logger.info("TradeMemory: DB empty — fresh start")
        except Exception as exc:
            self._db_available = False
            logger.warning(f"TradeMemory: DB unavailable — in-memory only: {exc}")

    def record(self, context: TradeContext) -> None:
        self._memory.append(context)
        if len(self._memory) > self._max_memory:
            removed = self._memory.pop(0)
            logger.debug(f"Old trade evicted from RAM: {removed.trade_id}")
        logger.info(
            f"Trade recorded | {context.symbol} | {context.direction} | "
            f"{context.outcome.value} | PnL: {context.pnl_pips:+.1f} pips"
        )
        if self._db_available:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._persist_to_db(context))
            except Exception as exc:
                logger.debug(f"TradeMemory DB write skipped: {exc}")

    def get_all(self) -> List[TradeContext]:
        return list(self._memory)

    def get_by_symbol(self, symbol: str) -> List[TradeContext]:
        return [t for t in self._memory if t.symbol == symbol]

    def get_by_outcome(self, outcome: TradeOutcome) -> List[TradeContext]:
        return [t for t in self._memory if t.outcome == outcome]

    def get_recent(self, n: int = 100) -> List[TradeContext]:
        return self._memory[-n:]

    def get_win_rate(self, symbol: Optional[str] = None) -> float:
        trades = self.get_by_symbol(symbol) if symbol else self._memory
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.outcome == TradeOutcome.WIN)
        return wins / len(trades)

    def get_average_rr(self, symbol: Optional[str] = None) -> float:
        trades = self.get_by_symbol(symbol) if symbol else self._memory
        if not trades:
            return 0.0
        return sum(t.realized_rr for t in trades) / len(trades)

    def get_consecutive_losses(self) -> int:
        count = 0
        for trade in reversed(self._memory):
            if trade.outcome == TradeOutcome.LOSS:
                count += 1
            else:
                break
        return count

    def to_feature_matrix(self) -> tuple[List[Dict[str, float]], List[int]]:
        features, labels = [], []
        for trade in self._memory:
            if trade.outcome in (TradeOutcome.WIN, TradeOutcome.LOSS):
                features.append(trade.to_ml_features())
                labels.append(1 if trade.outcome == TradeOutcome.WIN else 0)
        return features, labels

    def get_stats(self) -> Dict[str, Any]:
        total  = len(self._memory)
        wins   = sum(1 for t in self._memory if t.outcome == TradeOutcome.WIN)
        losses = sum(1 for t in self._memory if t.outcome == TradeOutcome.LOSS)
        return {
            "total_trades":       total,
            "wins":               wins,
            "losses":             losses,
            "win_rate":           wins / total if total > 0 else 0.0,
            "avg_rr":             self.get_average_rr(),
            "consecutive_losses": self.get_consecutive_losses(),
            "memory_usage":       f"{total}/{self._max_memory}",
            "db_available":       self._db_available,
        }

    async def _persist_to_db(self, context: TradeContext) -> None:
        try:
            from ..database import db
            data = context.to_dict()
            data["smc"]          = json.dumps(data.get("smc", {}))
            data["price_action"] = json.dumps(data.get("price_action", {}))
            data["risk"]         = json.dumps(data.get("risk", {}))
            data["confirmation_patterns"] = json.dumps(
                context.price_action.confirmation_patterns
            )
            await db.insert(self._DB_TABLE, data)
        except Exception as exc:
            logger.debug(f"TradeMemory DB persist failed (non-fatal): {exc}")

    @staticmethod
    def _row_to_context(row: Dict[str, Any]) -> TradeContext:
        smc_data = row.get("smc", {})
        if isinstance(smc_data, str):
            smc_data = json.loads(smc_data)
        pa_data = row.get("price_action", {})
        if isinstance(pa_data, str):
            pa_data = json.loads(pa_data)
        risk_data = row.get("risk", {})
        if isinstance(risk_data, str):
            risk_data = json.loads(risk_data)
        entry_time = row.get("entry_time")
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)
        exit_time = row.get("exit_time")
        if isinstance(exit_time, str) and exit_time:
            exit_time = datetime.fromisoformat(exit_time)
        else:
            exit_time = None
        smc_fields  = {k: v for k, v in smc_data.items()  if k in SMCContext.__dataclass_fields__}
        pa_fields   = {k: v for k, v in pa_data.items()   if k in PAContext.__dataclass_fields__}
        risk_fields = {k: v for k, v in risk_data.items() if k in RiskContext.__dataclass_fields__}
        return TradeContext(
            trade_id=row.get("trade_id", str(uuid.uuid4())),
            signal_id=row.get("signal_id", ""),
            symbol=row.get("symbol", ""),
            entry_time=entry_time, exit_time=exit_time,
            duration_minutes=float(row.get("duration_minutes", 0.0)),
            entry_price=float(row.get("entry_price", 0.0)),
            exit_price=float(row.get("exit_price", 0.0)),
            stop_loss=float(row.get("stop_loss", 0.0)),
            take_profit=float(row.get("take_profit", 0.0)),
            direction=row.get("direction", ""),
            outcome=TradeOutcome(row.get("outcome", "LOSS")),
            pnl_pips=float(row.get("pnl_pips", 0.0)),
            pnl_usd=float(row.get("pnl_usd", 0.0)),
            realized_rr=float(row.get("realized_rr", 0.0)),
            confidence_score=float(row.get("confidence_score", 0.0)),
            session=MarketSession(row.get("session", "OFF_HOURS")),
            market_condition=MarketCondition(row.get("market_condition", "RANGING")),
            smc=SMCContext(**smc_fields),
            price_action=PAContext(**pa_fields),
            risk=RiskContext(**risk_fields),
            news_active=bool(row.get("news_active", False)),
            previous_consecutive_losses=int(row.get("previous_consecutive_losses", 0)),
            notes=row.get("notes", ""),
        )
