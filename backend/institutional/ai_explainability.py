"""AI Explainability Service — human-readable reasons for every trade decision."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SMCSignal:
    bos_detected: bool = False
    choch_detected: bool = False
    order_block_price: Optional[float] = None
    order_block_strength: float = 0.0
    fvg_detected: bool = False
    fvg_top: Optional[float] = None
    fvg_bottom: Optional[float] = None
    liquidity_sweep: bool = False
    sweep_level: Optional[float] = None
    in_premium_zone: Optional[bool] = None   # True=premium, False=discount, None=neutral
    pd_zone_pct: float = 0.0                 # 0-100, position in premium/discount range
    structure_score: float = 0.0             # 0-100


@dataclass
class PASignal:
    pattern_name: Optional[str] = None
    pattern_strength: float = 0.0
    trend_alignment: bool = False
    session_alignment: bool = False


@dataclass
class MLSignal:
    prediction: Optional[str] = None   # "BUY" | "SELL" | "NEUTRAL"
    confidence: float = 0.0
    top_features: List[Dict] = field(default_factory=list)
    # [{feature: "atr_14", importance: 0.23, value: 12.5}, ...]
    drift_status: str = "STABLE"


@dataclass
class RiskSignal:
    within_daily_limit: bool = True
    account_risk_pct: float = 0.0
    open_trades_count: int = 0
    session_volatility: str = "NORMAL"  # LOW | NORMAL | HIGH


@dataclass
class TradeExplanation:
    """Complete human-readable explanation for a trade decision."""
    decision: str              # "BUY" | "SELL" | "NO_TRADE"
    confidence_score: float    # 0-100
    total_score: float         # 0-100

    # SMC reasons
    smc_reasons: List[str] = field(default_factory=list)
    smc_score: float = 0.0

    # Price Action reasons
    pa_reasons: List[str] = field(default_factory=list)
    pa_score: float = 0.0

    # ML reasons
    ml_reasons: List[str] = field(default_factory=list)
    ml_score: float = 0.0
    ml_top_features: List[Dict] = field(default_factory=list)

    # Risk reasons
    risk_reasons: List[str] = field(default_factory=list)
    risk_ok: bool = True

    # Blockers (reasons for NO_TRADE)
    blockers: List[str] = field(default_factory=list)

    # Summary
    summary: str = ""
    emoji_summary: str = ""

    def to_dict(self) -> Dict:
        return {
            "decision": self.decision,
            "confidence_score": self.confidence_score,
            "total_score": self.total_score,
            "smc": {"score": self.smc_score, "reasons": self.smc_reasons},
            "price_action": {"score": self.pa_score, "reasons": self.pa_reasons},
            "ml": {"score": self.ml_score, "reasons": self.ml_reasons, "top_features": self.ml_top_features},
            "risk": {"ok": self.risk_ok, "reasons": self.risk_reasons},
            "blockers": self.blockers,
            "summary": self.summary,
            "emoji_summary": self.emoji_summary,
        }


class AIExplainabilityService:
    """
    Generates human-readable explanations for every trade decision.

    Receives raw signals from all agents and builds a structured explanation
    showing WHY the bot decided to BUY / SELL / NO_TRADE.
    """

    SMC_WEIGHT = 0.35
    PA_WEIGHT = 0.20
    ML_WEIGHT = 0.30
    RISK_WEIGHT = 0.15

    @classmethod
    def explain(
        cls,
        decision: str,
        confidence: float,
        smc: SMCSignal,
        pa: PASignal,
        ml: MLSignal,
        risk: RiskSignal,
        raw_agent_votes: Optional[Dict] = None,
    ) -> TradeExplanation:

        smc_reasons, smc_score = cls._explain_smc(smc)
        pa_reasons, pa_score = cls._explain_pa(pa)
        ml_reasons, ml_score = cls._explain_ml(ml)
        risk_reasons, risk_ok = cls._explain_risk(risk)
        blockers = cls._find_blockers(smc, pa, ml, risk, decision)

        total_score = (
            smc_score * cls.SMC_WEIGHT +
            pa_score * cls.PA_WEIGHT +
            ml_score * cls.ML_WEIGHT +
            (100 if risk_ok else 0) * cls.RISK_WEIGHT
        )

        summary = cls._build_summary(decision, smc_reasons, pa_reasons, ml_reasons, blockers)
        emoji = cls._build_emoji_summary(decision, smc, pa, ml, risk)

        return TradeExplanation(
            decision=decision,
            confidence_score=round(confidence, 1),
            total_score=round(total_score, 1),
            smc_reasons=smc_reasons,
            smc_score=round(smc_score, 1),
            pa_reasons=pa_reasons,
            pa_score=round(pa_score, 1),
            ml_reasons=ml_reasons,
            ml_score=round(ml_score, 1),
            ml_top_features=ml.top_features,
            risk_reasons=risk_reasons,
            risk_ok=risk_ok,
            blockers=blockers,
            summary=summary,
            emoji_summary=emoji,
        )

    @staticmethod
    def _explain_smc(smc: SMCSignal):
        reasons = []
        score = 0.0

        if smc.bos_detected:
            reasons.append("✅ BOS (Break of Structure) confirmed — market shifted direction")
            score += 25
        if smc.choch_detected:
            reasons.append("✅ CHoCH (Change of Character) detected — trend reversal signal")
            score += 20
        if smc.order_block_price is not None:
            strength_label = "strong" if smc.order_block_strength > 70 else "moderate"
            reasons.append(f"✅ Order Block at {smc.order_block_price:.2f} ({strength_label}, score={smc.order_block_strength:.0f})")
            score += min(25, smc.order_block_strength * 0.25)
        if smc.fvg_detected:
            reasons.append(f"✅ Fair Value Gap (FVG) between {smc.fvg_bottom:.2f} – {smc.fvg_top:.2f}")
            score += 15
        if smc.liquidity_sweep:
            reasons.append(f"✅ Liquidity Sweep at {smc.sweep_level:.2f} — stop hunt detected")
            score += 15
        if smc.in_premium_zone is True:
            reasons.append(f"⚠️ Price in Premium Zone ({smc.pd_zone_pct:.0f}%) — favorable for SELL")
            score += 10
        elif smc.in_premium_zone is False:
            reasons.append(f"✅ Price in Discount Zone ({smc.pd_zone_pct:.0f}%) — favorable for BUY")
            score += 10

        if not reasons:
            reasons.append("❌ No SMC structure confirmed")

        return reasons, min(score, 100)

    @staticmethod
    def _explain_pa(pa: PASignal):
        reasons = []
        score = 0.0

        if pa.pattern_name:
            strength_label = "strong" if pa.pattern_strength > 70 else "moderate"
            reasons.append(f"✅ {pa.pattern_name} pattern ({strength_label}, score={pa.pattern_strength:.0f})")
            score += min(60, pa.pattern_strength * 0.6)
        if pa.trend_alignment:
            reasons.append("✅ Pattern aligned with higher-timeframe trend")
            score += 25
        if pa.session_alignment:
            reasons.append("✅ Active trading session (London/NY overlap)")
            score += 15

        if not reasons:
            reasons.append("❌ No Price Action pattern detected")

        return reasons, min(score, 100)

    @staticmethod
    def _explain_ml(ml: MLSignal):
        reasons = []
        score = 0.0

        if ml.prediction:
            reasons.append(f"✅ ML model predicts: {ml.prediction} (confidence {ml.confidence:.1f}%)")
            score += ml.confidence * 0.7
        if ml.drift_status == "STABLE":
            reasons.append("✅ Model is STABLE (no concept drift)")
            score += 20
        elif ml.drift_status == "WARNING":
            reasons.append("⚠️ Model drift WARNING — confidence reduced")
            score += 5
        elif ml.drift_status == "DRIFTED":
            reasons.append("❌ Model DRIFTED — retraining recommended")
            score -= 20
        if ml.top_features:
            top = ml.top_features[0]
            reasons.append(f"📊 Top feature: {top.get('feature', 'N/A')} (importance {top.get('importance', 0):.2f})")

        return reasons, max(0, min(score, 100))

    @staticmethod
    def _explain_risk(risk: RiskSignal):
        reasons = []
        ok = True

        if not risk.within_daily_limit:
            reasons.append("❌ Daily loss limit reached — trading halted")
            ok = False
        else:
            reasons.append(f"✅ Within daily risk limit (current: {risk.account_risk_pct:.1f}%)")
        if risk.open_trades_count > 2:
            reasons.append(f"⚠️ {risk.open_trades_count} trades already open")
        if risk.session_volatility == "HIGH":
            reasons.append("⚠️ High volatility session — wider spreads expected")

        return reasons, ok

    @staticmethod
    def _find_blockers(smc, pa, ml, risk, decision):
        blockers = []
        if decision == "NO_TRADE":
            if not smc.bos_detected and not smc.choch_detected:
                blockers.append("No market structure break detected")
            if smc.order_block_price is None:
                blockers.append("No valid Order Block found")
            if ml.confidence < 50:
                blockers.append(f"ML confidence too low ({ml.confidence:.1f}% < 50%)")
            if not risk.within_daily_limit:
                blockers.append("Daily risk limit breached")
        return blockers

    @staticmethod
    def _build_summary(decision, smc_reasons, pa_reasons, ml_reasons, blockers):
        action = {"BUY": "Enter LONG", "SELL": "Enter SHORT", "NO_TRADE": "Skip trade"}.get(decision, decision)
        key_smc = next((r for r in smc_reasons if "✅" in r), "")
        key_pa = next((r for r in pa_reasons if "✅" in r), "")
        key_ml = next((r for r in ml_reasons if "✅" in r), "")

        parts = [p for p in [key_smc, key_pa, key_ml] if p]
        if blockers:
            return f"{action}: blocked because {blockers[0]}"
        if parts:
            return f"{action}: " + " | ".join(p.replace("✅ ", "") for p in parts[:2])
        return f"{action}: insufficient signal"

    @staticmethod
    def _build_emoji_summary(decision, smc, pa, ml, risk):
        icons = []
        if decision == "BUY":
            icons.append("🟢 BUY")
        elif decision == "SELL":
            icons.append("🔴 SELL")
        else:
            icons.append("⏸️ SKIP")

        if smc.bos_detected:
            icons.append("💥BOS")
        if smc.choch_detected:
            icons.append("🔄CHoCH")
        if smc.order_block_price:
            icons.append("🟦OB")
        if smc.fvg_detected:
            icons.append("⚪ FVG")
        if smc.liquidity_sweep:
            icons.append("🌊 LSweep")
        if ml.confidence > 65:
            icons.append(f"🤖{ml.confidence:.0f}%")
        if not risk.within_daily_limit:
            icons.append("🛑RISK")

        return " ".join(icons)
