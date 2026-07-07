"""
PHASE 32 -- Customer Lifecycle Automation
Covers: onboarding / renewal reminder / expiry warning / churn detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


class LifecycleStage(Enum):
    ONBOARDING = auto()
    ACTIVE = auto()
    AT_RISK = auto()
    CHURNED = auto()
    RENEWED = auto()
    EXPIRED = auto()


@dataclass
class CustomerRecord:
    customer_id: str
    email: str
    plan: str
    stage: LifecycleStage = LifecycleStage.ONBOARDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    last_active: Optional[datetime] = None
    churn_score: float = 0.0
    notes: list[str] = field(default_factory=list)

    def days_to_expiry(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.now(timezone.utc)
        return delta.days

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def is_at_risk(self, inactivity_days: int = 14) -> bool:
        if self.last_active is None:
            return False
        cutoff = datetime.now(timezone.utc) - timedelta(days=inactivity_days)
        return self.last_active < cutoff


class CustomerLifecycleManager:
    """Manage customer lifecycle stages and send timely notifications."""

    def __init__(
        self,
        renewal_warning_days: int = 14,
        expiry_warning_days: int = 3,
        inactivity_days: int = 14,
    ) -> None:
        self._customers: dict[str, CustomerRecord] = {}
        self._renewal_warning = renewal_warning_days
        self._expiry_warning = expiry_warning_days
        self._inactivity = inactivity_days

    def register(
        self, customer_id: str, email: str, plan: str, expires_in_days: int = 365
    ) -> CustomerRecord:
        rec = CustomerRecord(
            customer_id=customer_id,
            email=email,
            plan=plan,
            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        )
        self._customers[customer_id] = rec
        logger.info("Registered customer %s (plan=%s)", customer_id, plan)
        return rec

    def record_activity(self, customer_id: str) -> None:
        rec = self._customers.get(customer_id)
        if rec:
            rec.last_active = datetime.now(timezone.utc)
            if rec.stage == LifecycleStage.AT_RISK:
                rec.stage = LifecycleStage.ACTIVE

    def renew(self, customer_id: str, extend_days: int = 365) -> Optional[CustomerRecord]:
        rec = self._customers.get(customer_id)
        if rec is None:
            return None
        base = max(rec.expires_at or datetime.now(timezone.utc), datetime.now(timezone.utc))
        rec.expires_at = base + timedelta(days=extend_days)
        rec.stage = LifecycleStage.RENEWED
        logger.info("Renewed customer %s for %d days", customer_id, extend_days)
        return rec

    async def run_lifecycle_check(self) -> dict:
        """Scan all customers and update stages."""
        stats = {"renewed": 0, "at_risk": 0, "expired": 0, "warnings": []}
        for rec in self._customers.values():
            if rec.is_expired():
                rec.stage = LifecycleStage.EXPIRED
                stats["expired"] += 1
            elif rec.is_at_risk(self._inactivity):
                rec.stage = LifecycleStage.AT_RISK
                stats["at_risk"] += 1
            days = rec.days_to_expiry()
            if days is not None and 0 < days <= self._renewal_warning:
                stats["warnings"].append({"customer": rec.customer_id, "days": days})
        logger.info("Lifecycle check: %s", stats)
        return stats

    def get_all(self) -> list[CustomerRecord]:
        return list(self._customers.values())

    def get(self, customer_id: str) -> Optional[CustomerRecord]:
        return self._customers.get(customer_id)

    def churn_candidates(self, threshold: float = 0.7) -> list[CustomerRecord]:
        return [r for r in self._customers.values() if r.churn_score >= threshold]


customer_lifecycle = CustomerLifecycleManager()
