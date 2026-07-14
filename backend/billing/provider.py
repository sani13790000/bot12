from __future__ import annotations

import enum
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class Currency(str, enum.Enum):
    USD = "usd"
    IRR = "irr"
    EUR = "eur"


class PaymentStatus(str, enum.Enum):
    PENDING   = "pending"
    SUCCEEDED = "succeeded"
    FAILED    = "failed"
    REFUNDED  = "refunded"
    CANCELLED = "cancelled"


class ProviderName(str, enum.Enum):
    STRIPE    = "stripe"
    ZARINPAL  = "zarinpal"
    MANUAL    = "manual"
    MOCK      = "mock"


class WebhookEventType(str, enum.Enum):
    PAYMENT_SUCCEEDED      = "payment.succeeded"
    PAYMENT_FAILED         = "payment.failed"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    REFUND_ISSUED          = "refund.issued"


@dataclass
class PaymentRequest:
    user_id:         str
    plan_id:         str
    amount:          int
    currency:        Currency
    description:     str  = ""
    metadata:        Dict = field(default_factory=dict)
    idempotency_key: str  = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class PaymentResult:
    provider:     ProviderName
    invoice_id:   str
    status:       PaymentStatus
    checkout_url: str  = ""
    raw:          Dict = field(default_factory=dict)
    error:        str  = ""


@dataclass
class WebhookEvent:
    provider:    ProviderName
    event_type:  WebhookEventType
    invoice_id:  str
    user_id:     str      = ""
    amount:      int      = 0
    currency:    Currency = Currency.USD
    raw:         Dict     = field(default_factory=dict)
    received_at: float    = field(default_factory=time.time)


class PaymentProvider:
    name: ProviderName = ProviderName.MOCK

    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        raise NotImplementedError("Subclass must implement this method")

    def confirm_payment(self, invoice_id: str, raw: Dict) -> PaymentResult:
        raise NotImplementedError("Subclass must implement this method")

    def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        raise NotImplementedError("Subclass must implement this method")

    def parse_webhook(self, payload: bytes) -> WebhookEvent:
        raise NotImplementedError("Subclass must implement this method")

    @staticmethod
    def _hmac_sha256(secret: str, data: bytes) -> str:
        return hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()


class MockProvider(PaymentProvider):
    name = ProviderName.MOCK

    def __init__(self, auto_succeed: bool = True):
        self._auto_succeed = auto_succeed
        self._store: Dict[str, PaymentResult] = {}

    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        invoice_id = f"mock_{req.idempotency_key[:8]}"
        status = PaymentStatus.SUCCEEDED if self._auto_succeed else PaymentStatus.PENDING
        result = PaymentResult(
            provider=self.name,
            invoice_id=invoice_id,
            status=status,
            checkout_url=f"https://mock.pay/{invoice_id}",
            raw={"amount": req.amount, "currency": req.currency, "plan": req.plan_id},
        )
        self._store[invoice_id] = result
        return result

    def confirm_payment(self, invoice_id: str, raw: Dict) -> PaymentResult:
        if invoice_id in self._store:
            self._store[invoice_id].status = PaymentStatus.SUCCEEDED
            return self._store[invoice_id]
        return PaymentResult(
            provider=self.name, invoice_id=invoice_id,
            status=PaymentStatus.FAILED, error="invoice_not_found",
        )

    def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        expected = self._hmac_sha256(secret, payload)
        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, payload: bytes) -> WebhookEvent:
        data = json.loads(payload)
        evt_type = data.get("event", "payment.succeeded")
        try:
            etype = WebhookEventType(evt_type)
        except ValueError:
            etype = WebhookEventType.PAYMENT_SUCCEEDED
        return WebhookEvent(
            provider=self.name,
            event_type=etype,
            invoice_id=data.get("invoice_id", ""),
            user_id=data.get("user_id", ""),
            amount=data.get("amount", 0),
            currency=Currency(data.get("currency", "usd")),
            raw=data,
        )

    def force_fail(self, invoice_id: str) -> None:
        if invoice_id in self._store:
            self._store[invoice_id].status = PaymentStatus.FAILED

    def force_refund(self, invoice_id: str) -> None:
        if invoice_id in self._store:
            self._store[invoice_id].status = PaymentStatus.REFUNDED


class ManualProvider(PaymentProvider):
    name = ProviderName.MANUAL

    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        invoice_id = f"man_{uuid.uuid4().hex[:12]}"
        return PaymentResult(
            provider=self.name, invoice_id=invoice_id,
            status=PaymentStatus.PENDING, checkout_url="",
            raw={"amount": req.amount, "currency": req.currency, "plan": req.plan_id},
        )

    def confirm_payment(self, invoice_id: str, raw: Dict) -> PaymentResult:
        return PaymentResult(
            provider=self.name, invoice_id=invoice_id,
            status=PaymentStatus.SUCCEEDED, raw=raw,
        )

    def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        return False

    def parse_webhook(self, payload: bytes) -> WebhookEvent:
        raise NotImplementedError("Subclass must implement this method")("Manual provider has no webhook")


class StripeProvider(PaymentProvider):
    name = ProviderName.STRIPE

    def __init__(self, api_key: str, webhook_secret: str):
        self._api_key        = api_key
        self._webhook_secret = webhook_secret

    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        invoice_id = f"cs_{uuid.uuid4().hex[:24]}"
        return PaymentResult(
            provider=self.name, invoice_id=invoice_id,
            status=PaymentStatus.PENDING,
            checkout_url=f"https://checkout.stripe.com/pay/{invoice_id}",
            raw={"amount": req.amount, "currency": req.currency.value},
        )

    def confirm_payment(self, invoice_id: str, raw: Dict) -> PaymentResult:
        status_map = {
            "complete":          PaymentStatus.SUCCEEDED,
            "payment_succeeded": PaymentStatus.SUCCEEDED,
            "payment_failed":    PaymentStatus.FAILED,
            "refunded":          PaymentStatus.REFUNDED,
        }
        pstatus = status_map.get(raw.get("status", ""), PaymentStatus.PENDING)
        return PaymentResult(
            provider=self.name, invoice_id=invoice_id, status=pstatus, raw=raw,
        )

    def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        parts = {p.split("=")[0]: p.split("=")[1]
                 for p in signature.split(",") if "=" in p}
        ts  = parts.get("t", "0")
        v1  = parts.get("v1", "")
        signed   = f"{ts}.".encode() + payload
        expected = self._hmac_sha256(secret, signed)
        return hmac.compare_digest(expected, v1)

    def parse_webhook(self, payload: bytes) -> WebhookEvent:
        data = json.loads(payload)
        event_map = {
            "checkout.session.completed":    WebhookEventType.PAYMENT_SUCCEEDED,
            "payment_intent.payment_failed": WebhookEventType.PAYMENT_FAILED,
            "customer.subscription.deleted": WebhookEventType.SUBSCRIPTION_CANCELLED,
            "charge.refunded":               WebhookEventType.REFUND_ISSUED,
        }
        evt = event_map.get(data.get("type", ""), WebhookEventType.PAYMENT_SUCCEEDED)
        obj = data.get("data", {}).get("object", {})
        return WebhookEvent(
            provider=self.name, event_type=evt,
            invoice_id=obj.get("id", data.get("id", "")),
            amount=obj.get("amount_total", 0),
            currency=Currency(obj.get("currency", "usd")),
            raw=data,
        )


class ZarinpalProvider(PaymentProvider):
    name = ProviderName.ZARINPAL

    def __init__(self, merchant_id: str, webhook_secret: str, sandbox: bool = False):
        self._merchant_id    = merchant_id
        self._webhook_secret = webhook_secret
        self._sandbox        = sandbox

    @property
    def _base(self) -> str:
        return (
            "https://sandbox.zarinpal.com/pg" if self._sandbox
            else "https://api.zarinpal.com/pg"
        )

    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        authority = f"ZAP_{uuid.uuid4().hex[:24]}"
        return PaymentResult(
            provider=self.name, invoice_id=authority,
            status=PaymentStatus.PENDING,
            checkout_url=f"{self._base}/StartPay/{authority}",
            raw={"amount": req.amount, "currency": "IRR"},
        )

    def confirm_payment(self, invoice_id: str, raw: Dict) -> PaymentResult:
        ok = raw.get("Status") == "OK" or raw.get("data", {}).get("code") == 100
        return PaymentResult(
            provider=self.name, invoice_id=invoice_id,
            status=PaymentStatus.SUCCEEDED if ok else PaymentStatus.FAILED,
            raw=raw,
        )

    def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        expected = self._hmac_sha256(secret, payload)
        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, payload: bytes) -> WebhookEvent:
        data = json.loads(payload)
        invoice_id = data.get("Authority", data.get("invoice_id", ""))
        ok = data.get("Status") == "OK"
        return WebhookEvent(
            provider=self.name,
            event_type=(
                WebhookEventType.PAYMENT_SUCCEEDED if ok
                else WebhookEventType.PAYMENT_FAILED
            ),
            invoice_id=invoice_id,
            amount=data.get("Amount", 0),
            currency=Currency.IRR,
            raw=data,
        )


def get_provider(name: ProviderName, config: Dict) -> PaymentProvider:
    if name == ProviderName.STRIPE:
        return StripeProvider(
            api_key=config["api_key"],
            webhook_secret=config.get("webhook_secret", ""),
        )
    if name == ProviderName.ZARINPAL:
        return ZarinpalProvider(
            merchant_id=config["merchant_id"],
            webhook_secret=config.get("webhook_secret", ""),
            sandbox=config.get("sandbox", False),
        )
    if name == ProviderName.MANUAL:
        return ManualProvider()
    if name == ProviderName.MOCK:
        return MockProvider(auto_succeed=config.get("auto_succeed", True))
    raise ValueError(f"Unknown provider: {name!r}")
