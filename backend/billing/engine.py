from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .provider import (
    Currency,
    PaymentProvider,
    PaymentRequest,
    PaymentResult,
    PaymentStatus,
    ProviderName,
)


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REVOKED = "revoked"


_SUB_FSM: Dict[SubscriptionStatus, set] = {
    SubscriptionStatus.TRIAL: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.EXPIRED,
        SubscriptionStatus.CANCELLED,
    },
    SubscriptionStatus.ACTIVE: {
        SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.EXPIRED,
        SubscriptionStatus.CANCELLED,
        SubscriptionStatus.SUSPENDED,
    },
    SubscriptionStatus.PAST_DUE: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.SUSPENDED,
        SubscriptionStatus.EXPIRED,
        SubscriptionStatus.CANCELLED,
    },
    SubscriptionStatus.SUSPENDED: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.REVOKED,
        SubscriptionStatus.CANCELLED,
    },
    SubscriptionStatus.EXPIRED: {SubscriptionStatus.ACTIVE},
    SubscriptionStatus.CANCELLED: {SubscriptionStatus.ACTIVE},
    SubscriptionStatus.REVOKED: set(),
}


class SubscriptionTransitionError(Exception):
    pass


@dataclass
class Subscription:
    sub_id: str
    user_id: str
    plan_id: str
    status: SubscriptionStatus
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    trial_ends_at: float = 0.0
    cancelled_at: Optional[float] = None
    dunning_count: int = 0
    license_key: str = ""
    transitions: List = field(default_factory=list)

    def transition(self, new_status: SubscriptionStatus, reason: str = "") -> None:
        allowed = _SUB_FSM.get(self.status, set())
        if new_status not in allowed:
            raise SubscriptionTransitionError(
                f"Transition {self.status!r} -> {new_status!r} is not allowed"
            )
        self.transitions.append(
            {
                "from": self.status,
                "to": new_status,
                "ts": time.time(),
                "reason": reason,
            }
        )
        self.status = new_status

    @property
    def is_active(self) -> bool:
        return self.status in {
            SubscriptionStatus.TRIAL,
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.PAST_DUE,
        }

    @property
    def days_remaining(self) -> int:
        if not self.expires_at:
            return 0
        return max(0, int((self.expires_at - time.time()) / 86400))

    @property
    def is_terminal(self) -> bool:
        return self.status == SubscriptionStatus.REVOKED


PLANS: Dict[str, Dict] = {
    "trial": {
        "price_usd": 0,
        "price_irr": 0,
        "days": 14,
        "label": "Trial",
        "features": ["signals_read", "signals_write", "dashboard"],
        "max_devices": 1,
        "max_positions": 3,
    },
    "basic": {
        "price_usd": 2900,
        "price_irr": 4_900_000,
        "days": 30,
        "label": "Basic",
        "features": ["signals_read", "signals_write", "dashboard", "mt5"],
        "max_devices": 2,
        "max_positions": 10,
    },
    "pro": {
        "price_usd": 7900,
        "price_irr": 12_900_000,
        "days": 30,
        "label": "Pro",
        "features": ["signals_read", "signals_write", "dashboard", "mt5", "ai", "analytics"],
        "max_devices": 5,
        "max_positions": 50,
    },
    "vip": {
        "price_usd": 14900,
        "price_irr": 24_900_000,
        "days": 30,
        "label": "VIP",
        "features": [
            "signals_read",
            "signals_write",
            "dashboard",
            "mt5",
            "ai",
            "analytics",
            "institutional",
        ],
        "max_devices": 10,
        "max_positions": 200,
    },
    "annual": {
        "price_usd": 79900,
        "price_irr": 129_900_000,
        "days": 365,
        "label": "Annual Pro",
        "features": [
            "signals_read",
            "signals_write",
            "dashboard",
            "mt5",
            "ai",
            "analytics",
            "institutional",
        ],
        "max_devices": 10,
        "max_positions": 500,
    },
}

DUNNING_THRESHOLD = 3


@dataclass
class Invoice:
    invoice_id: str
    user_id: str
    plan_id: str
    amount: int
    currency: Currency
    provider: ProviderName
    status: PaymentStatus
    checkout_url: str = ""
    created_at: float = field(default_factory=time.time)
    confirmed_at: Optional[float] = None
    raw: Dict = field(default_factory=dict)
    idempotency_key: str = ""


class BillingEngine:
    _IDEMPOTENCY_WINDOW_S: int = 3600

    def __init__(
        self,
        provider: PaymentProvider,
        on_license_activate: Optional[Callable[[str, str], None]] = None,
        on_subscription_change: Optional[Callable[[Subscription], None]] = None,
    ) -> None:
        self._provider = provider
        self._on_activate = on_license_activate
        self._on_change = on_subscription_change
        self._invoices: Dict[str, Invoice] = {}
        self._subscriptions: Dict[str, Subscription] = {}
        self._idempotency: Dict[str, str] = {}
        self._audit: List[Dict] = []

    def checkout(
        self,
        user_id: str,
        plan_id: str,
        currency: Currency = Currency.USD,
    ) -> Invoice:
        plan = PLANS.get(plan_id)
        if plan is None:
            raise ValueError(f"Unknown plan: {plan_id!r}")

        # P10-BUG-2 FIX: idempotency check BEFORE creating PaymentRequest
        idem_key = self._idem_key(user_id, plan_id)
        if idem_key in self._idempotency:
            existing_id = self._idempotency[idem_key]
            if existing_id in self._invoices:
                return self._invoices[existing_id]

        amount = plan["price_irr"] if currency == Currency.IRR else plan["price_usd"]

        req = PaymentRequest(
            user_id=user_id,
            plan_id=plan_id,
            amount=amount,
            currency=currency,
            description=f"{plan['label']} subscription",
            metadata={"user_id": user_id, "plan_id": plan_id},
            idempotency_key=idem_key,
        )

        result: PaymentResult = self._provider.create_payment(req)

        invoice = Invoice(
            invoice_id=result.invoice_id,
            user_id=user_id,
            plan_id=plan_id,
            amount=amount,
            currency=currency,
            provider=result.provider,
            status=result.status,
            checkout_url=result.checkout_url,
            raw=result.raw,
            idempotency_key=idem_key,
        )
        self._invoices[result.invoice_id] = invoice
        self._idempotency[idem_key] = result.invoice_id

        self._audit_log(
            "CHECKOUT_CREATED",
            user_id=user_id,
            detail=f"plan={plan_id} invoice={result.invoice_id}",
        )

        if result.status == PaymentStatus.SUCCEEDED:
            self._activate(invoice)

        return invoice

    def confirm_from_webhook(self, invoice_id: str, raw: Dict) -> Invoice:
        invoice = self._invoices.get(invoice_id)
        if invoice is None:
            raise KeyError(f"Invoice not found: {invoice_id!r}")

        if invoice.status == PaymentStatus.SUCCEEDED:
            return invoice

        result = self._provider.confirm_payment(invoice_id, raw)
        invoice.status = result.status
        invoice.raw.update(raw)

        if result.status == PaymentStatus.SUCCEEDED:
            invoice.confirmed_at = time.time()
            self._activate(invoice)
            self._audit_log(
                "PAYMENT_CONFIRMED", user_id=invoice.user_id, detail=f"invoice={invoice_id}"
            )
        elif result.status == PaymentStatus.FAILED:
            self._handle_payment_failure(invoice)
        elif result.status == PaymentStatus.REFUNDED:
            self._handle_refund(invoice)

        return invoice

    def admin_confirm(self, invoice_id: str, actor: str = "admin") -> Invoice:
        invoice = self._invoices.get(invoice_id)
        if invoice is None:
            raise KeyError(f"Invoice not found: {invoice_id!r}")
        if invoice.status == PaymentStatus.SUCCEEDED:
            return invoice
        invoice.status = PaymentStatus.SUCCEEDED
        invoice.confirmed_at = time.time()
        self._activate(invoice)
        self._audit_log(
            "ADMIN_CONFIRMED", user_id=invoice.user_id, detail=f"invoice={invoice_id} actor={actor}"
        )
        return invoice

    def suspend(self, user_id: str, reason: str = "admin_action") -> Subscription:
        sub = self._get_or_raise(user_id)
        sub.transition(SubscriptionStatus.SUSPENDED, reason)
        self._notify(sub)
        self._audit_log("SUBSCRIPTION_SUSPENDED", user_id=user_id, detail=reason)
        return sub

    def revoke(self, user_id: str, reason: str = "admin_action") -> Subscription:
        sub = self._get_or_raise(user_id)
        if sub.status != SubscriptionStatus.SUSPENDED:
            if SubscriptionStatus.SUSPENDED in _SUB_FSM.get(sub.status, set()):
                sub.transition(SubscriptionStatus.SUSPENDED, "pre-revoke")
        sub.transition(SubscriptionStatus.REVOKED, reason)
        self._notify(sub)
        self._audit_log("SUBSCRIPTION_REVOKED", user_id=user_id, detail=reason)
        return sub

    def cancel(self, user_id: str, reason: str = "user_request") -> Subscription:
        sub = self._get_or_raise(user_id)
        sub.transition(SubscriptionStatus.CANCELLED, reason)
        sub.cancelled_at = time.time()
        self._notify(sub)
        self._audit_log("SUBSCRIPTION_CANCELLED", user_id=user_id, detail=reason)
        return sub

    def get_subscription(self, user_id: str) -> Optional[Subscription]:
        return self._subscriptions.get(user_id)

    def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        return self._invoices.get(invoice_id)

    def list_invoices(self, user_id: str) -> List[Invoice]:
        return [i for i in self._invoices.values() if i.user_id == user_id]

    def audit_log(self, user_id: Optional[str] = None) -> List[Dict]:
        if user_id:
            return [e for e in self._audit if e.get("user_id") == user_id]
        return list(self._audit)

    def _activate(self, invoice: Invoice) -> None:
        user_id = invoice.user_id
        plan = PLANS[invoice.plan_id]
        now = time.time()

        sub = self._subscriptions.get(user_id)

        if sub is None:
            is_trial = invoice.plan_id == "trial"
            status = SubscriptionStatus.TRIAL if is_trial else SubscriptionStatus.ACTIVE
            license_key = f"BOT12-{uuid.uuid4().hex[:16].upper()}"
            sub = Subscription(
                sub_id=str(uuid.uuid4()),
                user_id=user_id,
                plan_id=invoice.plan_id,
                status=status,
                expires_at=now + plan["days"] * 86400,
                trial_ends_at=(now + plan["days"] * 86400) if is_trial else 0.0,
                license_key=license_key,
            )
            self._subscriptions[user_id] = sub
        else:
            target = SubscriptionStatus.ACTIVE
            if sub.status in (
                SubscriptionStatus.TRIAL,
                SubscriptionStatus.PAST_DUE,
                SubscriptionStatus.EXPIRED,
                SubscriptionStatus.CANCELLED,
                SubscriptionStatus.SUSPENDED,
            ) and target in _SUB_FSM.get(sub.status, set()):
                sub.transition(target, f"payment_confirmed invoice={invoice.invoice_id}")
            sub.plan_id = invoice.plan_id
            sub.expires_at = now + plan["days"] * 86400
            sub.dunning_count = 0

        if self._on_activate and sub.license_key:
            self._on_activate(user_id, sub.license_key)

        self._notify(sub)

    def _handle_payment_failure(self, invoice: Invoice) -> None:
        sub = self._subscriptions.get(invoice.user_id)
        if sub is None:
            return

        sub.dunning_count += 1
        self._audit_log(
            "PAYMENT_FAILED", user_id=invoice.user_id, detail=f"dunning={sub.dunning_count}"
        )

        if sub.status == SubscriptionStatus.ACTIVE:
            sub.transition(
                SubscriptionStatus.PAST_DUE, f"payment_failed dunning={sub.dunning_count}"
            )
        elif sub.status == SubscriptionStatus.PAST_DUE:
            if sub.dunning_count >= DUNNING_THRESHOLD:
                sub.transition(
                    SubscriptionStatus.SUSPENDED,
                    f"dunning_threshold_reached count={sub.dunning_count}",
                )

        self._notify(sub)

    def _handle_refund(self, invoice: Invoice) -> None:
        sub = self._subscriptions.get(invoice.user_id)
        if sub is None:
            return
        self._audit_log(
            "PAYMENT_REFUNDED", user_id=invoice.user_id, detail=f"invoice={invoice.invoice_id}"
        )
        if sub.status == SubscriptionStatus.ACTIVE:
            if SubscriptionStatus.SUSPENDED in _SUB_FSM.get(sub.status, set()):
                sub.transition(SubscriptionStatus.SUSPENDED, "refund_issued")
        self._notify(sub)

    def _get_or_raise(self, user_id: str) -> Subscription:
        sub = self._subscriptions.get(user_id)
        if sub is None:
            raise KeyError(f"No subscription for user: {user_id!r}")
        return sub

    def _notify(self, sub: Subscription) -> None:
        if self._on_change:
            self._on_change(sub)

    def _idem_key(self, user_id: str, plan_id: str) -> str:
        window = int(time.time()) // self._IDEMPOTENCY_WINDOW_S
        return f"{user_id}:{plan_id}:{window}"

    def _audit_log(self, event: str, user_id: str = "", detail: str = "") -> None:
        self._audit.append(
            {
                "event": event,
                "user_id": user_id,
                "detail": detail,
                "ts": time.time(),
            }
        )
