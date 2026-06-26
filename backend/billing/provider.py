"""
backend/billing/provider.py
Phase 10 — Payment Provider Abstraction

Supports multiple providers:
  - Stripe  (international)
  - ZarinPal (Iran)
  - Manual  (bank transfer / crypto — admin confirms)
  - Mock    (testing)

All providers return a unified PaymentResult.
New providers: subclass PaymentProvider, register in _REGISTRY.
"""

from __future__ import annotations

import abc
import enum
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# Enums
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

class PaymentStatus(str, enum.Enum):
    PENDING   = "pending"
    SUCCESS   = "success"
    FAILED    = "failed"
    REFUNDED  = "refunded"
    CANCELLED = "cancelled"


class ProviderName(str, enum.Enum):
    STRIPE    = "stripe"
    ZARINPAL  = "zarinPal"
    MANUAL    = "manual"
    MOCK      = "mock"


class Currency(str, enum.Enum):
    USD = "USD"
    EUR = "EUR"
    IRR = "IRR"   # Iranian Rial (ZarinPal)
    IRT = "IRT"   # Toman (ZarinPal display)


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# Data models
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

@dataclass(frozen=True)
class PaymentRequest:
    amount:        int            # smallest unit (cents / rials)
    currency:      Currency
    user_id:       str
    plan_id:       str
    idempotency_key: str          # caller must supply — UUID/order-id
    description:   str = ""
    metadata:      dict = field(default_factory=dict)
    callback_url:  str = ""       # redirect after 3DS / ZarinPal
    webhook_url:   str = ""


@dataclass
class PaymentResult:
    status:          PaymentStatus
    provider:        ProviderName
    provider_ref:    str           # Stripe PaymentIntent ID / ZarinPal Authority
    idempotency_key: str
    amount:          int
    currency:        Currency
    user_id:         str
    plan_id:         str
    redirect_url:    str = ""      # for hosted pages
    error_message:   str = ""
    raw_response:    dict = field(default_factory=dict)
    created_at:      float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "status":           self.status.value,
            "provider":         self.provider.value,
            "provider_ref":     self.provider_ref,
            "idempotency_key":  self.idempotency_key,
            "amount":            self.amount,
            "currency":          self.currency.value,
            "user_id":           self.user_id,
            "plan_id":           self.plan_id,
            "redirect_url":      self.redirect_url,
            "error_message":     self.error_message,
            "created_at":        self.created_at,
        }


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# Abstract Base
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

class PaymentProvider(abc.ABC):
    """All providers must implement these methods."""

    @abc.abstractmethod
    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        ...

    @abc.abstractmethod
    def verify_payment(self, provider_ref: str) -> PaymentResult:
        ...

    @abc.abstractmethod
    def refund(self, provider_ref: str, amount: int) -> PaymentResult:
        ...

    @abc.abstractmethod
    def verify_webhook_signature(self, payload: bytes, sig: str) -> bool:
        ...

    @property
    @abc.abstractmethod
    def name(self) -> ProviderName:
        ...


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# Mock Provider (testing)
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

class MockProvider(PaymentProvider):
    """
    Deterministic mock for tests.
    Control with:
        mock.force_status = PaymentStatus.FAILED
        mock.force_verify = PaymentStatus.SUCCESS
    """

    def __init__(self, secret: str = "mock-secret") as None:
        self._secret         = secret
        self.force_status    = PaymentStatus.SUCCESS
        self.force_verify    = PaymentStatus.SUCCESS
        self._log:            list[PaymentResult] = []
        self._refs:           dict[str, PaymentResult] = {}
        self._refund_log:     list = []

    @property
    def name(self) -> ProviderName:
        return ProviderName.MOCK

    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        ref = f"mock_{req.idempotency_key}"
        res = PaymentResult(
            status=self.force_status,
            provider=ProviderName.MOCK,
            provider_ref=ref,
            idempotency_key=req.idempotency_key,
            amount=req.amount,
            currency=req.currency,
            user_id=req.user_id,
            plan_id=req.plan_id,
            redirect_url=f"https://mock.pay/checkout/{ref}" if self.force_status == PaymentStatus.PENDING else "",
        )
        self._log.append(res)
        self._refs[ref] = res
        return res

    def verify_payment(self, provider_ref: str) -> PaymentResult:
        if provider_ref in self._refs:
            res = self._refs[provider_ref]
            res.status = self.force_verify
            return res
        return PaymentResult(
            status=PaymentStatus.FAILED,
            provider=ProviderName.MOCK,
            provider_ref=provider_ref,
            idempotency_key="",
            amount=0,
            currency=Currency.USD,
            user_id="",
            plan_id="",
            error_message="not_found",
        )

    def refund(self, provider_ref: str, amount: int) -> PaymentResult:
        self._refund_log.append({"ref": provider_ref, "amount": amount})
        if provider_ref in self._refs:
            res = self._refs[provider_ref]
            res.status = PaymentStatus.REFUNDED
            return res
        return PaymentResult(
            status=PaymentStatus.FAILED,
            provider=ProviderName.MOCK,
            provider_ref=provider_ref,
            idempotency_key="",
            amount=0,
            currency=Currency.USD,
            user_id="",
            plan_id="",
            error_message="not_found",
        )

    def verify_webhook_signature(self, payload: bytes, sig: str) -> bool:
        expected = hmac.new(self._secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)

    @property
    def log(self) -> list[PaymentResult]:
        return list(self._log)


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# Stripe Provider
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

class StripeProvider(PaymentProvider):
    """
    Stripe PaymentIntent API.
    Requires: secret_key (sk_...)
    Install: pip install stripe
    """

    def __init__(self, secret_key: str, webhook_secret: str = "") -> None:
        self._key             = secret_key
        self._wh_secret       = webhook_secret
        try:
            import stripe
            stripe.api_key = secret_key
            self._stripe = stripe
        except ImportError:
            self._stripe = None  # test env fallback

    @property
    def name(self) -> ProviderName:
        return ProviderName.STRIPE

    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        if not self._stripe:
            raise RuntimeError("stripe package not installed")
        try:
            intent = self._stripe.PaymentIntent.create(
                amount=req.amount,
                currency=req.currency.value.lower(),
                metadata={
                    "user_id": req.user_id,
                    "plan_id": req.plan_id,
                    "idempotency_key": req.idempotency_key,
                },
                idempotency_key=req.idempotency_key,
            )
            return PaymentResult(
                status=PaymentStatus.PENDING,
                provider=ProviderName.STRIPE,
                provider_ref=intent["id"],
                idempotency_key=req.idempotency_key,
                amount=req.amount,
                currency=req.currency,
                user_id=req.user_id,
                plan_id=req.plan_id,
                redirect_url=intent.get("client_secret", ""),
            )
        except Exception as e:
            return PaymentResult(
                status=PaymentStatus.FAILED,
                provider=ProviderName.STRIPE,
                provider_ref="",
                idempotency_key=req.idempotency_key,
                amount=req.amount,
                currency=req.currency,
                user_id=req.user_id,
                plan_id=req.plan_id,
                error_message=str(e),
            )

    def verify_payment(self, provider_ref: str) -> PaymentResult:
        if not self._stripe:
            raise RuntimeError("stripe not installed")
        try:
            intent = self._stripe.PaymentIntent.retrieve(provider_ref)
            status_map = {
                "succeeded":       PaymentStatus.SUCCESS,
                "requires_payment_method": PaymentStatus.FAILED,
                "canceled":        PaymentStatus.CANCELLED,
            }
            status = status_map.get(intent["status"], PaymentStatus.PENDING)
            return PaymentResult(
                status=status,
                provider=ProviderName.STRIPE,
                provider_ref=provider_ref,
                idempotency_key=intent["metadata"].get("idempotency_key", ""),
                amount=intent["amount"],
                currency=Currency(intent["currency"].upper()),
                user_id=intent["metadata"].get("user_id", ""),
                plan_id=intent["metadata"].get("plan_id", ""),
            )
        except Exception as e:
            return PaymentResult(
                status=PaymentStatus.FAILED,
                provider=ProviderName.STRIPE,
                provider_ref=provider_ref,
                idempotency_key="",
                amount=0,
                currency=Currency.USD,
                user_id="",
                plan_id="",
                error_message=str(e),
            )

    def refund(self, provider_ref: str, amount: int) -> PaymentResult:
        if not self._stripe:
            raise RuntimeError("stripe not installed")
        try:
            r = self._stripe.Refund.create(payment_intent=provider_ref, amount=amount)
            return PaymentResult(
                status=PaymentStatus.REFUNDED,
                provider=ProviderName.STRIPE,
                provider_ref=r.get("id", provider_ref),
                idempotency_key="",
                amount=amount,
                currency=Currency.USD,
                user_id="",
                plan_id="",
            )
        except Exception as e:
            return PaymentResult(
                status=PaymentStatus.FAILED,
                provider=ProviderName.STRIPE,
                provider_ref="",
                idempotency_key="",
                amount=0,
                currency=Currency.USD,
                user_id="",
                plan_id="",
                error_message=str(e),
            )

    def verify_webhook_signature(self, payload: bytes, sig: str) -> bool:
        if not self._wh_secret:
            return False
        try:
            self._stripe.Webhook.construct_event(payload, sig, self._wh_secret)
            return True
        except Exception:
            return False


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# ZarinPal Provider
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

class ZarinPalProvider(PaymentProvider):
    """
    ZarinPal Rest API v4.
    Requires: merchant_id (UUID)
    Docs: https://dev.zarinpal.com/docs/zarinpal/rest
    """

    _BASE = "https://api.zarinpal.com/v4/payment"

    def __init__(self, merchant_id: str, sandbox: bool = False) -> None:
        self._mid     = merchant_id
        self._sandbox = sandbox
        if sandbox:
            self._BASE = "https://sandbox.zarinpal.com/v4/payment"

    @property
    def name(self) -> ProviderName:
        return ProviderName.ZARINPAL

    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        import urllib.request, json
        body = json.dumps({
            "merchant_id": self._mid,
            "amount": req.amount,
            "currency": req.currency.value,
            "description": req.description or f"Bot12 {req.plan_id} subscription",
            "callback_url": req.callback_url or "https://bot12.io/callback",
            "metadata": {"user_id": req.user_id, "plan_id": req.plan_id},
        }).encode()
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(
                    f"{self._BASE}/request.json",
                    data=body, headers={"Content-Type": "application/json"}
                ), timeout=10
            )
            data = json.loadr)
            authority = data["data"]["authority"]
            return PaymentResult(
                status=PaymentStatus.PENDING,
                provider=ProviderName.ZARINPAL,
                provider_ref=authority,
                idempotency_key=req.idempotency_key,
                amount=req.amount,
                currency=req.currency,
                user_id=req.user_id,
                plan_id=req.plan_id,
                redirect_url=f"https://www.zarinPal.com/Pg2StartPay/Gateway/Payment/{authority}",
            )
        except Exception as e:
            return PaymentResult(
                status=PaymentStatus.FAILED,
                provider=ProviderName.ZARINPAL,
                provider_ref="",
                idempotency_key=req.idempotency_key,
                amount=req.amount,
                currency=req.currency,
                user_id=req.user_id,
                plan_id=req.plan_id,
                error_message=str(e),
            )

    def verify_payment(self, provider_ref: str) -> PaymentResult:
        import urllib.request, json
        body = json.dumps({"merchant_id": self._mid, "amount": 0, "authority": provider_ref}).encode()
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(
                    f"{self._BASE}/verify.json",
                    data=body, headers={"Content-Type": "application/json"}
                ), timeout=10
            )
            data = json.load(r)
            ok = data["data"]["code"] == 100
            return PaymentResult(
                status=PaymentStatus.SUCCESS if ok else PaymentStatus.FAILED,
                provider=ProviderName.ZARINPAL,
                provider_ref=provider_ref,
                idempotency_key="",
                amount=data["data"].get("amount", 0),
                currency=Currency.IRR,
                user_id="",
                plan_id="",
            )
        except Exception as e:
            return PaymentResult(
                status=PaymentStatus.FAILED,
                provider=ProviderName.ZARINPAL,
                provider_ref=provider_ref,
                idempotency_key="",
                amount=0,
                currency=Currency.IRR,
                user_id="",
                plan_id="",
                error_message=str(e),
            )

    def refund(self, provider_ref: str, amount: int) -> PaymentResult:
        return PaymentResult(
            status=PaymentStatus.FAILED,
            provider=ProviderName.ZARINPAL,
            provider_ref=provider_ref,
            idempotency_key="",
            amount=0,
            currency=Currency.IRR,
            user_id="",
            plan_id="",
            error_message="ZarinPal does not support API refunds -- use panel",
        )

    def verify_webhook_signature(self, payload: bytes, sig: str) -> bool:
        # ZarinPal uses callback params; no HMAC webhook sig
        return True


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# Manual Provider
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

class ManualProvider(PaymentProvider):
    """
    Bank transfer / crypto / offline payments.
    Admin must call confirm_manual_payment() to activate license.
    """

    def __init__(self) -> None:
        self._pending: dict[str, dict] = {}

    @property
    def name(self) -> ProviderName:
        return ProviderName.MANUAL

    def create_payment(self, req: PaymentRequest) -> PaymentResult:
        ref = f"MAN-{req.idempotency_key[:9]}"
        self._pending[ref] = {"req": req, "status": "pending"}
        return PaymentResult(
            status=PaymentStatus.PENDING,
            provider=ProviderName.MANUAL,
            provider_ref=ref,
            idempotency_key=req.idempotency_key,
            amount=req.amount,
            currency=req.currency,
            user_id=req.user_id,
            plan_id=req.plan_id,
        )

    def verify_payment(self, provider_ref: str) -> PaymentResult:
        pending = self._pending.get(provider_ref)
        if pending and pending["status"] == "success":
            req = pending["req"]
            return PaymentResult(
                status=PaymentStatus.SUCCESS,
                provider=ProviderName.MANUAL,
                provider_ref=provider_ref,
                idempotency_key=req.idempotency_key,
                amount=req.amount,
                currency=req.currency,
                user_id=req.user_id,
                plan_id=req.plan_id,
            )
        return PaymentResult(
            status=PaymentStatus.PENDING,
            provider=ProviderName.MANUAL,
            provider_ref=provider_ref,
            idempotency_key="",
            amount=0,
            currency=Currency.USD,
            user_id="",
            plan_id="",
        )

    def refund(self, provider_ref: str, amount: int) -> PaymentResult:
        return PaymentResult(
            status=PaymentStatus.FAILED,
            provider=ProviderName.MANUAL,
            provider_ref=provider_ref,
            idempotency_key="",
            amount=0,
            currency=Currency.USD,
            user_id="",
            plan_id="",
            error_message="Manual refunds are processed by admin",
        )

    def verify_webhook_signature(self, payload: bytes, sig: str) -> bool:
        return True

    def confirm(self, provider_ref: str) -> bool:
        """Admin confirms payment receipt."""
        if provider_ref in self._pending:
            self._pending[provider_ref]["status"] = "success"
            return True
        return False


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# Registry + Factory
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

_REGISTRY: dict[ProviderName, type] = {
    ProviderName.MOCK:     MockProvider,
    ProviderName.STRIPE:   StripeProvider,
    ProviderName.ZARINPAL: ZarinPalProvider,
    ProviderName.MANUAL:   ManualProvider,
}


def get_provider(name: str | ProviderName, **kwargs) -> PaymentProvider:
    """Factory — instantiate provider by name."""
    try:
        pn = ProviderName(name)
    except ValueError:
        raise ValueError(f"Unknown payment provider: {name!r} — valid: {list(_REGISTRY.keys())}")
    cls = _REGISTRY.get(pn)
    if cls is None:
        raise ValueError(f"Unknown payment provider: {name!r} — valid: {list(_REGISTRY.keys())}")
    return cls(**kwargs)
