"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Agent 6: News Agent
مسئولیت: فیلتر اخبار، High Impact Events، NFP، FOMC
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .base_agent import AgentVote, AgentStatus, BaseAgent


class NewsAgent(BaseAgent):
    """
    فیلتر اخبار:
    - اخبار High Impact (NFP، CPI، FOMC، GDP)
    - پنجره زمانی قبل/بعد از خبر
    - کاهش امتیاز در زمان اخبار
    - بلاک کردن معامله در صورت تنظیم

    اگر news_filter_enabled=False باشد → score=100 (فیلتر خاموش)
    """

    HIGH_IMPACT_EVENTS = {"NFP", "FOMC", "CPI", "GDP", "RATE_DECISION", "PMI", "UNEMPLOYMENT"}

    def __init__(self, weight: float = 0.10, enabled: bool = True,
                 block_on_high_impact: bool = False,
                 minutes_before: int = 30,
                 minutes_after: int = 15) -> None:
        super().__init__(name="News", weight=weight, enabled=enabled)
        self.block_on_high_impact = block_on_high_impact
        self.minutes_before = minutes_before
        self.minutes_after  = minutes_after

    async def analyze(self, context: Dict[str, Any]) -> AgentVote:
        # اگر فیلتر خبر خاموش باشد
        if not context.get("news_filter_enabled", True):
            return AgentVote(
                score=80.0, confidence=60.0,
                direction=context.get("direction", "NEUTRAL"),
                status=AgentStatus.OK,
                reason="News filter disabled",
                metadata={"filter_active": False},
            )

        score      = 90.0
        confidence = 70.0
        reasons    = []
        blocked    = False

        # اخبار آینده نزدیک
        upcoming_news: List[Dict] = context.get("upcoming_news", [])
        now = datetime.now(timezone.utc)

        for event in upcoming_news:
            impact    = str(event.get("impact", "LOW")).upper()
            event_name = str(event.get("name", ""))
            minutes_to = float(event.get("minutes_to_event", 999))
            minutes_since = float(event.get("minutes_since_event", 999))

            if impact == "HIGH" or event_name.upper() in self.HIGH_IMPACT_EVENTS:
                if minutes_to <= self.minutes_before:
                    score -= 40.0
                    reasons.append(f"High impact event in {minutes_to:.0f}min: {event_name}")
                    if self.block_on_high_impact and minutes_to <= 15:
                        blocked = True
                        score   = 0.0
                        reasons.append(f"BLOCKED: {event_name} < 15min away")
                elif minutes_since <= self.minutes_after:
                    score -= 25.0
                    reasons.append(f"Post-event cooldown ({minutes_since:.0f}min): {event_name}")
            elif impact == "MEDIUM":
                if minutes_to <= 15:
                    score -= 10.0
                    reasons.append(f"Medium event soon: {event_name}")

        if not upcoming_news:
            score = 90.0
            reasons.append("No significant news nearby")

        score      = max(0.0, min(100.0, score))
        confidence = max(0.0, min(100.0, confidence))
        status     = AgentStatus.ERROR if blocked else AgentStatus.OK

        return AgentVote(
            score=score,
            confidence=confidence,
            direction=context.get("direction", "NEUTRAL"),
            status=status,
            reason=" | ".join(reasons) if reasons else "News clear",
            metadata={
                "blocked": blocked,
                "events_count": len(upcoming_news),
                "block_on_high_impact": self.block_on_high_impact,
            },
        )
