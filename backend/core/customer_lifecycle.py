"""
backend/core/customer_lifecycle.py
Galaxy Vast AI — Customer Lifecycle Automation

STUB VERSION: Full implementation is available in the published artifact.
Run .github/workflows/apply-large-fixes.yml on this branch to restore it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class LifecycleEvent(str, Enum):
    ONBOARDING_STARTED = "onboarding.started"
    ONBOARDING_COMPLETED = "onboarding.completed"
    TRIAL_STARTED = "trial.started"
    TRIAL_EXPIRED = "trial.expired"
    SUBSCRIPTION_RENEWED = "subscription.renewed"
    SUBSCRIPTION_EXPIRED = "subscription.expired"


class CustomerStatus(str, Enum):
    ONBOARDING = "onboarding"
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"


@dataclass
class CustomerRecord:
    customer_id: str
    tenant_id: str
    email: str
    status: CustomerStatus = CustomerStatus.ONBOARDING
    plan: str = "trial"
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    expires_at: Optional[float] = None
    max_devices: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LifecycleAuditEntry:
    entry_id: str
    event: str
    customer_id: str
    tenant_id: str
    actor: str
    reason: str
    detail: Dict[str, Any]
    ts: float


class CustomerStore:
    def __init__(self) -> None:
        self._customers: Dict[str, CustomerRecord] = {}

    def add(self, record: CustomerRecord) -> None:
        self._customers[record.customer_id] = record

    def get(self, customer_id: str) -> Optional[CustomerRecord]:
        return self._customers.get(customer_id)

    def list_all(self) -> List[CustomerRecord]:
        return list(self._customers.values())

    def list_by_status(self, status: CustomerStatus) -> List[CustomerRecord]:
        return [c for c in self._customers.values() if c.status == status]

    def list_expiring(self, within_days: float) -> List[CustomerRecord]:
        now = datetime.now(timezone.utc).timestamp()
        return [
            c for c in self._customers.values()
            if c.expires_at and 0 < (c.expires_at - now) / 86400 <= within_days
        ]

    def count_by_status(self) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for c in self._customers.values():
            result[c.status.value] = result.get(c.status.value, 0) + 1
        return result


class LifecycleAuditChain:
    def __init__(self, secret: str = "lifecycle-audit-secret-v32") -> None:
        self._secret = secret
        self._entries: List[LifecycleAuditEntry] = []

    def record(
        self,
        event: str,
        customer_id: str,
        tenant_id: str,
        actor: str,
        reason: str = "",
        detail: Optional[Dict[str, Any]] = None,
        ts: Optional[float] = None,
    ) -> LifecycleAuditEntry:
        entry = LifecycleAuditEntry(
            entry_id=f"{customer_id}-{event}-{ts or datetime.now(timezone.utc).timestamp()}",
            event=event,
            customer_id=customer_id,
            tenant_id=tenant_id,
            actor=actor,
            reason=reason,
            detail=detail or {},
            ts=ts or datetime.now(timezone.utc).timestamp(),
        )
        self._entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        return True


class NotificationEngine:
    def __init__(self, audit: Optional[LifecycleAuditChain] = None) -> None:
        self._audit = audit
        self._sent = 0

    def send(self, customer: CustomerRecord, event: str, body: str, actor: str = "system") -> bool:
        self._sent += 1
        if self._audit:
            self._audit.record(event, customer.customer_id, customer.tenant_id, actor)
        return True

    def count_sent(self) -> int:
        return self._sent


class OnboardingEngine:
    def __init__(
        self,
        store: CustomerStore,
        notifications: NotificationEngine,
        audit: Optional[LifecycleAuditChain] = None,
    ) -> None:
        self._store = store
        self._notifications = notifications
        self._audit = audit

    def start_onboarding(self, customer_id: str, tenant_id: str, email: str, actor: str = "system") -> CustomerRecord:
        record = CustomerRecord(customer_id=customer_id, tenant_id=tenant_id, email=email)
        self._store.add(record)
        if self._audit:
            self._audit.record(LifecycleEvent.ONBOARDING_STARTED, customer_id, tenant_id, actor)
        return record

    def complete_step(self, customer_id: str, step: str, actor: str = "system") -> Optional[CustomerRecord]:
        record = self._store.get(customer_id)
        if record:
            record.metadata.setdefault("onboarding_steps", []).append(step)
        return record


class SubscriptionLifecycleManager:
    def __init__(
        self,
        store: CustomerStore,
        notifications: NotificationEngine,
        audit: Optional[LifecycleAuditChain] = None,
    ) -> None:
        self._store = store
        self._notifications = notifications
        self._audit = audit

    def start_trial(self, customer_id: str, duration_days: int = 14, actor: str = "system") -> Optional[CustomerRecord]:
        record = self._store.get(customer_id)
        if not record:
            return None
        record.status = CustomerStatus.TRIAL
        record.expires_at = datetime.now(timezone.utc).timestamp() + duration_days * 86400
        if self._audit:
            self._audit.record(LifecycleEvent.TRIAL_STARTED, customer_id, record.tenant_id, actor)
        return record

    def send_renewal_reminder(self, customer: CustomerRecord, actor: str = "system") -> bool:
        return self._notifications.send(customer, LifecycleEvent.SUBSCRIPTION_RENEWED, "Renewal reminder")

    def send_expiry_warning(self, customer: CustomerRecord, actor: str = "system") -> bool:
        return self._notifications.send(customer, LifecycleEvent.SUBSCRIPTION_EXPIRED, "Expiry warning")

    def expire_subscription(self, customer: CustomerRecord, actor: str = "system") -> None:
        customer.status = CustomerStatus.EXPIRED
        if self._audit:
            self._audit.record(LifecycleEvent.SUBSCRIPTION_EXPIRED, customer.customer_id, customer.tenant_id, actor)


class DeviceHeartbeatManager:
    def __init__(
        self,
        store: CustomerStore,
        notifications: NotificationEngine,
        audit: Optional[LifecycleAuditChain] = None,
        heartbeat_timeout_s: float = 300.0,
    ) -> None:
        self._store = store
        self._notifications = notifications
        self._audit = audit
        self._timeout = heartbeat_timeout_s

    def register_heartbeat(self, customer_id: str) -> Optional[CustomerRecord]:
        record = self._store.get(customer_id)
        if record:
            record.metadata["last_heartbeat"] = datetime.now(timezone.utc).timestamp()
        return record

    def flag_heartbeat_fail(self, customer: CustomerRecord, actor: str = "system") -> None:
        if self._audit:
            self._audit.record("heartbeat.fail", customer.customer_id, customer.tenant_id, actor)

    def list_heartbeat_overdue(self) -> List[CustomerRecord]:
        now = datetime.now(timezone.utc).timestamp()
        return [
            c for c in self._store.list_all()
            if c.metadata.get("last_heartbeat", 0) < now - self._timeout
        ]


class ReactivationEngine:
    def __init__(
        self,
        store: CustomerStore,
        notifications: NotificationEngine,
        audit: Optional[LifecycleAuditChain] = None,
    ) -> None:
        self._store = store
        self._notifications = notifications
        self._audit = audit
        self._offers: List[Any] = []

    def create_offer(self, customer: CustomerRecord, actor: str = "system") -> Dict[str, Any]:
        offer = {
            "offer_id": f"offer-{customer.customer_id}",
            "customer_id": customer.customer_id,
            "discount_pct": 20,
            "valid_until": datetime.now(timezone.utc).timestamp() + 7 * 86400,
        }
        self._offers.append(offer)
        return offer

    def list_offers(self) -> List[Any]:
        return self._offers


class DunningManager:
    def __init__(
        self,
        store: CustomerStore,
        notifications: NotificationEngine,
        audit: Optional[LifecycleAuditChain] = None,
    ) -> None:
        self._store = store
        self._notifications = notifications
        self._audit = audit

    def start_dunning(self, customer: CustomerRecord, actor: str = "system") -> None:
        customer.status = CustomerStatus.EXPIRED
        if self._audit:
            self._audit.record("dunning.started", customer.customer_id, customer.tenant_id, actor)


class SupportTicketDeflector:
    def __init__(self, audit: Optional[LifecycleAuditChain] = None) -> None:
        self._audit = audit
        self._tickets: List[Any] = []

    def open_ticket(self, customer_id: str, tenant_id: str, category: str, subject: str, body: str) -> Any:
        ticket = {
            "ticket_id": f"ticket-{len(self._tickets)}",
            "customer_id": customer_id,
            "tenant_id": tenant_id,
            "category": category,
            "subject": subject,
            "body": body,
            "status": "open",
        }
        self._tickets.append(ticket)
        return ticket

    def list_tickets(self, status: Optional[str] = None) -> List[Any]:
        if status:
            return [t for t in self._tickets if t["status"] == status]
        return self._tickets

    def deflection_rate(self) -> float:
        if not self._tickets:
            return 0.0
        return sum(1 for t in self._tickets if t.get("self_served")) / len(self._tickets)


class LifecycleScheduler:
    def __init__(
        self,
        store: CustomerStore,
        sub_mgr: SubscriptionLifecycleManager,
        heartbeat: DeviceHeartbeatManager,
        reactivation: ReactivationEngine,
        audit: Optional[LifecycleAuditChain] = None,
        renewal_remind_days: float = 14.0,
        expiry_warn_days: float = 3.0,
    ) -> None:
        self._store = store
        self._sub = sub_mgr
        self._heartbeat = heartbeat
        self._reactivation = reactivation
        self._audit = audit
        self._renew_days = renewal_remind_days
        self._expiry_days = expiry_warn_days

    def run_daily(self, actor: str = "scheduler") -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for c in self._store.list_expiring(self._renew_days):
            days = (c.expires_at - datetime.now(timezone.utc).timestamp()) / 86400 if c.expires_at else 0
            if days > self._expiry_days:
                self._sub.send_renewal_reminder(c, actor=actor)
                counts["renewal_reminders"] = counts.get("renewal_reminders", 0) + 1
        for c in self._store.list_expiring(self._expiry_days):
            self._sub.send_expiry_warning(c, actor=actor)
            counts["expiry_warnings"] = counts.get("expiry_warnings", 0) + 1
        for c in self._store.list_by_status(CustomerStatus.ACTIVE):
            if c.is_expired() if hasattr(c, "is_expired") else False:
                self._sub.expire_subscription(c, actor=actor)
                counts["expired"] = counts.get("expired", 0) + 1
        for c in self._heartbeat.list_heartbeat_overdue():
            self._heartbeat.flag_heartbeat_fail(c, actor=actor)
            counts["heartbeat_fails"] = counts.get("heartbeat_fails", 0) + 1
        return counts


@dataclass
class LifecycleDashboard:
    total_customers: int
    status_breakdown: Dict[str, int]
    onboarding_complete: int
    expiring_7d: int
    heartbeat_overdue: int
    self_service_rate: float
    open_tickets: int
    audit_chain_ok: bool
    notification_count: int
    reactivation_offers: int
    generated_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


class LifecycleAdmin:
    def __init__(
        self,
        store: CustomerStore,
        notif: NotificationEngine,
        onboard: OnboardingEngine,
        sub_mgr: SubscriptionLifecycleManager,
        heartbeat: DeviceHeartbeatManager,
        reactivation: ReactivationEngine,
        deflector: SupportTicketDeflector,
        audit: LifecycleAuditChain,
    ) -> None:
        self._store = store
        self._notif = notif
        self._onboard = onboard
        self._sub = sub_mgr
        self._heartbeat = heartbeat
        self._reactivation = reactivation
        self._deflector = deflector
        self._audit = audit

    def dashboard(self) -> LifecycleDashboard:
        all_customers = self._store.list_all()
        onboarding_done = sum(1 for c in all_customers if c.metadata.get("onboarding_steps"))
        return LifecycleDashboard(
            total_customers=len(all_customers),
            status_breakdown=self._store.count_by_status(),
            onboarding_complete=onboarding_done,
            expiring_7d=len(self._store.list_expiring(7)),
            heartbeat_overdue=len(self._heartbeat.list_heartbeat_overdue()),
            self_service_rate=self._deflector.deflection_rate(),
            open_tickets=len(self._deflector.list_tickets("open")),
            audit_chain_ok=self._audit.verify_chain(),
            notification_count=self._notif.count_sent(),
            reactivation_offers=len(self._reactivation.list_offers()),
        )


def build_lifecycle_system(
    audit_secret: str = "lifecycle-audit-secret-v32",
    heartbeat_timeout_s: float = 300.0,
    renewal_remind_days: float = 14.0,
    expiry_warn_days: float = 3.0,
) -> Dict[str, Any]:
    audit = LifecycleAuditChain(secret=audit_secret)
    store = CustomerStore()
    notif = NotificationEngine(audit=audit)
    onboard = OnboardingEngine(store, notif, audit)
    sub_mgr = SubscriptionLifecycleManager(store, notif, audit)
    heartbeat = DeviceHeartbeatManager(store, notif, audit, heartbeat_timeout_s)
    reactivation = ReactivationEngine(store, notif, audit)
    dunning = DunningManager(store, notif, audit)
    deflector = SupportTicketDeflector(audit)
    scheduler = LifecycleScheduler(store, sub_mgr, heartbeat, reactivation, audit, renewal_remind_days, expiry_warn_days)
    admin = LifecycleAdmin(store, notif, onboard, sub_mgr, heartbeat, reactivation, deflector, audit)
    return {
        "audit": audit, "store": store, "notif": notif,
        "onboard": onboard, "sub": sub_mgr, "heartbeat": heartbeat,
        "reactivation": reactivation, "dunning": dunning, "deflector": deflector,
        "scheduler": scheduler, "admin": admin,
    }
