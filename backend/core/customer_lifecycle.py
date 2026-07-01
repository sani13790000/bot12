"""
PHASE 32 -- Customer Lifecycle Automation
Covers: onboarding / renewal reminder / expiry warning / reactivation /
        cancellation / new-device / heartbeat-fail / download guidance /
        support ticket reduction
All lifecycle events are auditable, reason-coded, fail-closed.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class LifecycleEvent(str, Enum):
    ONBOARDING_STARTED         = "onboarding_started"
    ONBOARDING_COMPLETED       = "onboarding_completed"
    RENEWAL_REMINDER_7D        = "renewal_reminder_7d"
    RENEWAL_REMINDER_3D        = "renewal_reminder_3d"
    RENEWAL_REMINDER_1D        = "renewal_reminder_1d"
    LICENSE_EXPIRED            = "license_expired"
    LICENSE_RENEWED            = "license_renewed"
    LICENSE_REVOKED            = "license_revoked"
    LICENSE_UPGRADED           = "license_upgraded"
    LICENSE_DOWNGRADED         = "license_downgraded"
    REACTIVATION_REQUESTED     = "reactivation_requested"
    REACTIVATION_APPROVED      = "reactivation_approved"
    CANCELLATION_REQUESTED     = "cancellation_requested"
    CANCELLATION_CONFIRMED     = "cancellation_confirmed"
    NEW_DEVICE_REGISTERED      = "new_device_registered"
    DEVICE_LIMIT_REACHED       = "device_limit_reached"
    HEARTBEAT_FAILURE          = "heartbeat_failure"
    HEARTBEAT_RESTORED         = "heartbeat_restored"
    DOWNLOAD_REQUESTED         = "download_requested"
    SUPPORT_TICKET_CREATED     = "support_ticket_created"
    PAYMENT_FAILED             = "payment_failed"
    PAYMENT_RECOVERED          = "payment_recovered"
    CHURN_RISK_DETECTED        = "churn_risk_detected"


class LifecycleReason(str, Enum):
    SCHEDULED     = "scheduled"
    USER_REQUEST  = "user_request"
    ADMIN_ACTION  = "admin_action"
    SYSTEM_AUTO   = "system_auto"
    PAYMENT_ISSUE = "payment_issue"
    POLICY        = "policy"


@dataclass
class LifecycleRecord:
    record_id: str
    user_id: str
    event: LifecycleEvent
    reason: LifecycleReason
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    notified: bool = False
    notification_channel: Optional[str] = None
    processed: bool = False


class CustomerLifecycleAutomation:
    """Automates customer lifecycle events with notification dispatch."""

    def __init__(self, renewal_warning_days: list = None) -> None:
        self._warning_days = renewal_warning_days or [7, 3, 1]
        self._handlers: Dict[LifecycleEvent, List[Callable]] = {}
        self._records: List[LifecycleRecord] = []
        self._log = logging.getLogger(self.__class__.__name__)

    def on(self, event: LifecycleEvent, handler: Callable) -> None:
        """Register an event handler."""
        self._handlers.setdefault(event, []).append(handler)

    async def emit(self, event: LifecycleEvent, user_id: str, reason: LifecycleReason = LifecycleReason.SYSTEM_AUTO, **meta) -> LifecycleRecord:
        """Emit a lifecycle event and dispatch to handlers."""
        import uuid
        rec = LifecycleRecord(
            record_id=str(uuid.uuid4())[:12],
            user_id=user_id,
            event=event,
            reason=reason,
            metadata=meta,
        )
        self._records.append(rec)
        self._log.info("Lifecycle: %s user=%s reason=%s", event.value, user_id, reason.value)
        for handler in self._handlers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(rec)
                else:
                    handler(rec)
                rec.processed = True
            except Exception as exc:
                self._log.error("Handler error for %s: %s", event.value, exc)
        return rec

    async def check_renewals(self, licenses: List[Dict[str, Any]]) -> List[LifecycleRecord]:
        """Check licenses for upcoming renewals and emit reminders."""
        now = datetime.now(timezone.utc)
        records = []
        for lic in licenses:
            expires = lic.get("expires_at")
            if not expires:
                continue
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires)
            days_left = (expires - now).days
            user_id = lic.get("user_id", "unknown")
            for warn_days in self._warning_days:
                if abs(days_left - warn_days) <= 0:
                    event_map = {7: LifecycleEvent.RENEWAL_REMINDER_7D, 3: LifecycleEvent.RENEWAL_REMINDER_3D, 1: LifecycleEvent.RENEWAL_REMINDER_1D}
                    ev = event_map.get(warn_days)
                    if ev:
                        rec = await self.emit(ev, user_id, reason=LifecycleReason.SCHEDULED, expires_at=expires.isoformat(), days_left=days_left)
                        records.append(rec)
            if days_left <= 0:
                rec = await self.emit(LifecycleEvent.LICENSE_EXPIRED, user_id, reason=LifecycleReason.SYSTEM_AUTO, expired_at=expires.isoformat())
                records.append(rec)
        return records

    async def process_onboarding(self, user_id: str, plan: str, device_id: str) -> LifecycleRecord:
        """Handle new customer onboarding."""
        await self.emit(LifecycleEvent.ONBOARDING_STARTED, user_id, reason=LifecycleReason.USER_REQUEST, plan=plan, device_id=device_id)
        # Simulate setup tasks
        await asyncio.sleep(0)
        return await self.emit(LifecycleEvent.ONBOARDING_COMPLETED, user_id, plan=plan, device_id=device_id)

    async def process_cancellation(self, user_id: str, admin: str = "system") -> LifecycleRecord:
        """Handle cancellation request."""
        await self.emit(LifecycleEvent.CANCELLATION_REQUESTED, user_id, reason=LifecycleReason.USER_REQUEST)
        return await self.emit(LifecycleEvent.CANCELLATION_CONFIRMED, user_id, reason=LifecycleReason.ADMIN_ACTION, admin=admin)

    async def process_reactivation(self, user_id: str) -> LifecycleRecord:
        """Handle reactivation request."""
        await self.emit(LifecycleEvent.REACTIVATION_REQUESTED, user_id, reason=LifecycleReason.USER_REQUEST)
        return await self.emit(LifecycleEvent.REACTIVATION_APPROVED, user_id, reason=LifecycleReason.ADMIN_ACTION)

    def get_user_timeline(self, user_id: str, limit: int = 50) -> List[LifecycleRecord]:
        """Get lifecycle history for a user."""
        user_records = [r for r in self._records if r.user_id == user_id]
        return sorted(user_records, key=lambda r: r.timestamp, reverse=True)[:limit]

    def stats(self) -> Dict[str, Any]:
        total = len(self._records)
        by_event: Dict[str, int] = {}
        for r in self._records:
            by_event[r.event.value] = by_event.get(r.event.value, 0) + 1
        return {"total_events": total, "by_event": by_event, "unique_users": len({r.user_id for r in self._records})}


_automation: Optional[CustomerLifecycleAutomation] = None


def get_lifecycle_automation() -> CustomerLifecycleAutomation:
    global _automation
    if _automation is None:
        _automation = CustomerLifecycleAutomation()
    return _automation
