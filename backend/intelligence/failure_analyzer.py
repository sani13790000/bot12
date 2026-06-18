"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: FailureAnalyzer — تحلیل شکست معاملات

قانون اصلی:
  زیان ≠ اشتباه
  اشتباه فقط زمانی است که:
    • قوانین ورود نقض شده باشند
    • شرایط بازار نامعتبر بوده باشد
    • ریسک به درستی محاسبه نشده باشد
    • خبر مهم نادیده گرفته شده باشد

  یک معامله زیان‌ده که تمام قوانین رعایت شده،
  اشتباه نیست — بخشی از توزیع احتمالاتی بازار است.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .trade_memory import TradeContext, TradeOutcome, MarketCondition
from ..core.logger import get_logger

logger = get_logger("intelligence.failure_analyzer")


class FailureType(str, Enum):
    """
    نوع شکست معامله.
    VALID_LOSS یعنی معامله درست بوده اما بازار موافقت نکرده.
    """
    VALID_LOSS = "VALID_LOSS"                       # زیان معتبر — اشتباه نیست
    LOW_CONFIDENCE_ENTRY = "LOW_CONFIDENCE_ENTRY"   # ورود با امتیاز پایین
    BAD_SESSION = "BAD_SESSION"                     # ورود خارج از سشن مناسب
    HIGH_SPREAD = "HIGH_SPREAD"                     # اسپرد بیش از حد
    NO_HTF_ALIGNMENT = "NO_HTF_ALIGNMENT"           # عدم هم‌راستایی HTF
    NEWS_IGNORED = "NEWS_IGNORED"                   # خبر مهم نادیده گرفته شد
    NO_LIQUIDITY_SWEEP = "NO_LIQUIDITY_SWEEP"       # ورود بدون sweep نقدینگی
    POOR_ORDER_BLOCK = "POOR_ORDER_BLOCK"           # کیفیت پایین Order Block
    HIGH_PORTFOLIO_RISK = "HIGH_PORTFOLIO_RISK"     # ریسک کل پرتفولیو بالا
    WRONG_MARKET_CONDITION = "WRONG_MARKET_CONDITION"  # شرایط نامناسب بازار
    CONSECUTIVE_LOSS_IGNORED = "CONSECUTIVE_LOSS_IGNORED"  # نادیده گرفتن زیان‌های متوالی


@dataclass
class FailureReport:
    """
    گزارش کامل تحلیل شکست یک معامله.
    """
    trade_id: str
    symbol: str
    outcome: TradeOutcome

    # تشخیص اصلی
    is_valid_loss: bool = True              # آیا زیان معتبر است (نه اشتباه)
    failure_types: List[FailureType] = field(default_factory=list)
    rule_violations: List[str] = field(default_factory=list)

    # امتیاز کیفیت ورود (0-100)
    entry_quality_score: float = 0.0

    # جزئیات تحلیل
    confidence_at_entry: float = 0.0
    htf_alignment_at_entry: float = 0.0
    spread_ratio: float = 0.0             # spread / ATR
    portfolio_risk_at_entry: float = 0.0

    # توصیه‌ها
    recommendations: List[str] = field(default_factory=list)

    # خلاصه متنی
    summary: str = ""

    @property
    def severity(self) -> str:
        """شدت شکست"""
        violations = len(self.rule_violations)
        if violations == 0:
            return "NONE"       # زیان معتبر
        elif violations == 1:
            return "LOW"        # یک نقض جزئی
        elif violations <= 3:
            return "MEDIUM"     # چند نقض
        else:
            return "HIGH"       # نقض‌های متعدد


class FailureAnalyzer:
    """
    تحلیل‌گر شکست معاملات Galaxy Vast.

    این کلاس هر معامله زیان‌ده را تحلیل می‌کند و تعیین می‌کند:
      آیا یک زیان معتبر (VALID_LOSS) است یا نقض قوانین سیستم.

    هدف: جلوگیری از overfitting به زیان‌های تصادفی.
    """

    # حداقل امتیاز اطمینان مجاز برای ورود
    MIN_CONFIDENCE_THRESHOLD: float = 70.0

    # حداکثر نسبت spread به ATR
    MAX_SPREAD_ATR_RATIO: float = 0.3

    # حداقل کیفیت Order Block
    MIN_ORDER_BLOCK_QUALITY: float = 0.5

    # حداقل هم‌راستایی HTF
    MIN_HTF_ALIGNMENT: float = 0.4

    # حداکثر ریسک کل پرتفولیو
    MAX_PORTFOLIO_RISK: float = 5.0

    # حداکثر زیان‌های متوالی مجاز
    MAX_CONSECUTIVE_LOSSES: int = 5

    # سشن‌های نامناسب برای معامله
    INVALID_SESSIONS = {"OFF_HOURS"}

    def analyze(self, trade: TradeContext) -> FailureReport:
        """
        تحلیل کامل یک معامله و تولید گزارش.

        Args:
            trade: context کامل معامله

        Returns:
            FailureReport با تمام جزئیات
        """
        report = FailureReport(
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            outcome=trade.outcome,
            confidence_at_entry=trade.confidence_score,
            htf_alignment_at_entry=trade.smc.htf_alignment,
            portfolio_risk_at_entry=trade.risk.portfolio_risk_at_entry,
        )

        # محاسبه نسبت spread به ATR
        if trade.risk.atr_at_entry > 0:
            report.spread_ratio = trade.risk.spread_at_entry / trade.risk.atr_at_entry
        else:
            report.spread_ratio = 0.0

        # اجرای همه چک‌ها
        self._check_confidence(trade, report)
        self._check_session(trade, report)
        self._check_spread(trade, report)
        self._check_htf_alignment(trade, report)
        self._check_news(trade, report)
        self._check_liquidity_sweep(trade, report)
        self._check_order_block_quality(trade, report)
        self._check_portfolio_risk(trade, report)
        self._check_market_condition(trade, report)
        self._check_consecutive_losses(trade, report)

        # تعیین امتیاز کیفیت ورود
        report.entry_quality_score = self._calculate_entry_quality(trade)

        # تعیین اینکه آیا زیان معتبر است
        report.is_valid_loss = len(report.rule_violations) == 0

        # تولید خلاصه
        report.summary = self._generate_summary(report)

        # تولید توصیه‌ها
        report.recommendations = self._generate_recommendations(report)

        if report.is_valid_loss:
            logger.info(
                f"زیان معتبر | {trade.symbol} | {trade.pnl_pips:+.1f}p | "
                f"کیفیت ورود: {report.entry_quality_score:.0f}/100"
            )
        else:
            logger.warning(
                f"نقض قوانین | {trade.symbol} | {len(report.rule_violations)} نقض | "
                f"{report.severity} | {report.failure_types}"
            )

        return report

    def analyze_batch(self, trades: List[TradeContext]) -> List[FailureReport]:
        """تحلیل دسته‌ای معاملات"""
        reports = []
        for trade in trades:
            if trade.outcome in (TradeOutcome.LOSS, TradeOutcome.BREAKEVEN):
                reports.append(self.analyze(trade))
        return reports

    def get_violation_frequency(
        self, reports: List[FailureReport]
    ) -> Dict[FailureType, float]:
        """
        محاسبه فراوانی هر نوع نقض در مجموعه گزارش‌ها.

        Returns:
            دیکشنری {FailureType: درصد فراوانی}
        """
        if not reports:
            return {}

        counts: Dict[FailureType, int] = {}
        for report in reports:
            for ft in report.failure_types:
                counts[ft] = counts.get(ft, 0) + 1

        total = len(reports)
        return {ft: count / total for ft, count in counts.items()}

    # ─── چک‌های خصوصی ──────────────────────────────────────────

    def _check_confidence(self, trade: TradeContext, report: FailureReport) -> None:
        """بررسی امتیاز اطمینان هنگام ورود"""
        if trade.confidence_score < self.MIN_CONFIDENCE_THRESHOLD:
            report.failure_types.append(FailureType.LOW_CONFIDENCE_ENTRY)
            report.rule_violations.append(
                f"امتیاز اطمینان {trade.confidence_score:.1f} کمتر از حداقل "
                f"{self.MIN_CONFIDENCE_THRESHOLD} بود"
            )

    def _check_session(self, trade: TradeContext, report: FailureReport) -> None:
        """بررسی سشن معاملاتی"""
        if trade.session.value in self.INVALID_SESSIONS:
            report.failure_types.append(FailureType.BAD_SESSION)
            report.rule_violations.append(
                f"ورود در سشن نامناسب: {trade.session.value}"
            )

    def _check_spread(self, trade: TradeContext, report: FailureReport) -> None:
        """بررسی اسپرد هنگام ورود"""
        if report.spread_ratio > self.MAX_SPREAD_ATR_RATIO:
            report.failure_types.append(FailureType.HIGH_SPREAD)
            report.rule_violations.append(
                f"اسپرد/ATR = {report.spread_ratio:.2f} بیشتر از حداکثر مجاز "
                f"{self.MAX_SPREAD_ATR_RATIO}"
            )

    def _check_htf_alignment(self, trade: TradeContext, report: FailureReport) -> None:
        """بررسی هم‌راستایی با HTF"""
        if trade.smc.htf_alignment < self.MIN_HTF_ALIGNMENT:
            report.failure_types.append(FailureType.NO_HTF_ALIGNMENT)
            report.rule_violations.append(
                f"هم‌راستایی HTF {trade.smc.htf_alignment:.2f} کمتر از حداقل "
                f"{self.MIN_HTF_ALIGNMENT}"
            )

    def _check_news(self, trade: TradeContext, report: FailureReport) -> None:
        """بررسی وضعیت خبر"""
        if trade.news_active:
            report.failure_types.append(FailureType.NEWS_IGNORED)
            report.rule_violations.append("ورود هنگام خبر مهم اقتصادی")

    def _check_liquidity_sweep(
        self, trade: TradeContext, report: FailureReport
    ) -> None:
        """بررسی اینکه آیا liquidity قبل از ورود جاروب شد"""
        if not trade.smc.liquidity_swept and trade.smc.structure_score > 0.6:
            # فقط اگر ساختار قوی بود و sweep نداشتیم
            report.failure_types.append(FailureType.NO_LIQUIDITY_SWEEP)
            report.rule_violations.append(
                "ورود بدون sweep نقدینگی قبلی — ریسک manipulation بالاتر است"
            )

    def _check_order_block_quality(
        self, trade: TradeContext, report: FailureReport
    ) -> None:
        """بررسی کیفیت Order Block"""
        if (
            trade.smc.order_block_quality > 0
            and trade.smc.order_block_quality < self.MIN_ORDER_BLOCK_QUALITY
        ):
            report.failure_types.append(FailureType.POOR_ORDER_BLOCK)
            report.rule_violations.append(
                f"کیفیت Order Block {trade.smc.order_block_quality:.2f} "
                f"زیر حداقل {self.MIN_ORDER_BLOCK_QUALITY}"
            )

    def _check_portfolio_risk(
        self, trade: TradeContext, report: FailureReport
    ) -> None:
        """بررسی ریسک کل پرتفولیو"""
        if trade.risk.portfolio_risk_at_entry > self.MAX_PORTFOLIO_RISK:
            report.failure_types.append(FailureType.HIGH_PORTFOLIO_RISK)
            report.rule_violations.append(
                f"ریسک پرتفولیو {trade.risk.portfolio_risk_at_entry:.1f}٪ "
                f"بیشتر از حداکثر {self.MAX_PORTFOLIO_RISK}٪"
            )

    def _check_market_condition(
        self, trade: TradeContext, report: FailureReport
    ) -> None:
        """بررسی شرایط بازار"""
        bad_conditions = {MarketCondition.HIGH_VOLATILITY, MarketCondition.POST_NEWS}
        if trade.market_condition in bad_conditions:
            report.failure_types.append(FailureType.WRONG_MARKET_CONDITION)
            report.rule_violations.append(
                f"ورود در شرایط نامناسب بازار: {trade.market_condition.value}"
            )

    def _check_consecutive_losses(
        self, trade: TradeContext, report: FailureReport
    ) -> None:
        """بررسی زیان‌های متوالی"""
        if trade.previous_consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            report.failure_types.append(FailureType.CONSECUTIVE_LOSS_IGNORED)
            report.rule_violations.append(
                f"{trade.previous_consecutive_losses} زیان متوالی — "
                "باید trading pause می‌شد"
            )

    def _calculate_entry_quality(self, trade: TradeContext) -> float:
        """
        محاسبه امتیاز کیفیت ورود (0-100).
        هر چه بالاتر، ورود با کیفیت‌تر بوده.
        """
        score = 0.0

        # امتیاز اطمینان (30٪ وزن)
        score += (trade.confidence_score / 100.0) * 30

        # ساختار SMC (30٪ وزن)
        smc_score = (
            trade.smc.structure_score * 0.4
            + trade.smc.htf_alignment * 0.3
            + trade.smc.order_block_quality * 0.2
            + trade.smc.fvg_quality * 0.1
        )
        score += smc_score * 30

        # Price Action (20٪ وزن)
        pa_score = (
            trade.price_action.pattern_quality * 0.6
            + trade.price_action.rejection_strength * 0.4
        )
        score += pa_score * 20

        # ریسک و مدیریت (20٪ وزن)
        risk_score = 1.0
        if trade.risk.portfolio_risk_at_entry > self.MAX_PORTFOLIO_RISK:
            risk_score *= 0.5
        if report_spread_ratio := (
            trade.risk.spread_at_entry / max(trade.risk.atr_at_entry, 1e-9)
        ):
            risk_score *= max(0.3, 1.0 - report_spread_ratio)
        score += risk_score * 20

        return min(100.0, max(0.0, score))

    def _generate_summary(self, report: FailureReport) -> str:
        """تولید خلاصه متنی گزارش"""
        if report.is_valid_loss:
            return (
                f"زیان معتبر — تمام قوانین رعایت شده. "
                f"کیفیت ورود: {report.entry_quality_score:.0f}/100. "
                "این معامله بخشی از توزیع احتمالاتی طبیعی است."
            )
        else:
            violations_text = " | ".join(report.rule_violations[:3])
            return (
                f"نقض قوانین ({len(report.rule_violations)} مورد): "
                f"{violations_text}"
            )

    def _generate_recommendations(self, report: FailureReport) -> List[str]:
        """تولید توصیه‌های عملی"""
        recs = []
        for ft in report.failure_types:
            if ft == FailureType.LOW_CONFIDENCE_ENTRY:
                recs.append("آستانه حداقل امتیاز را بررسی و در صورت لزوم افزایش دهید")
            elif ft == FailureType.BAD_SESSION:
                recs.append("فیلتر سشن را فعال نگه دارید — فقط London/NY معامله کنید")
            elif ft == FailureType.HIGH_SPREAD:
                recs.append("حداکثر اسپرد مجاز را کاهش دهید یا Spread Filter را سخت‌تر کنید")
            elif ft == FailureType.NO_HTF_ALIGNMENT:
                recs.append("وزن HTF alignment در Decision Engine را افزایش دهید")
            elif ft == FailureType.NEWS_IGNORED:
                recs.append("News Filter را فعال کنید — ۳۰ دقیقه قبل و بعد از خبر معامله نکنید")
            elif ft == FailureType.NO_LIQUIDITY_SWEEP:
                recs.append("صبر کنید تا liquidity جاروب شود قبل از ورود")
            elif ft == FailureType.HIGH_PORTFOLIO_RISK:
                recs.append("Portfolio Risk Manager را بررسی کنید — حد کل ریسک را رعایت کنید")
        return recs
