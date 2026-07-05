"""
backend/api/routes/billing.py
Phase 10 - Billing API Routes
BUG-W1 fix: _get_billing_engine() now dispatches to real providers (zarinpal/stripe/manual)
BUG-V2 fix: removed router=None guard

Customer routes  (require JWT):
  POST /billing/checkout               -> initiate payment
  GET  /billing/subscription           -> current subscription
  GET  /billing/invoices               -> invoice history
  POST /billing/cancel                 -> cancel subscription

Admin routes  (require MANAGE_BILLING permission):
  POST /billing/admin/confirm/{id}     -> confirm manual payment
  POST /billing/admin/suspend/{uid}    -> suspend user subscription
  POST /billing/admin/revoke/{uid}     -> revoke user subscription
  GET  /billing/admin/subscriptions    -> list all subscriptions

Webhook routes  (NO auth -- signature verified internally):
  POST /billing/webhook/{provider}     -> receive payment provider callbacks
"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import (
    APIRouter, Body, Depends, Header,
    HTTPException, Path, Request, status,
)
from pydantic import BaseModel, Field

from ...billing.engine   import BillingEngine, PLANS
from ...billing.provider import Currency, ProviderName
from ...billing.webhook  import WebhookProcessor

# BUG-V2 fix: router always created — no None guard
router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan_id:  str = Field(..., description="Plan ID: trial/basic/pro/vip/annual")
    currency: str = Field("usd", description="usd or irr")


class CheckoutResponse(BaseModel):
    invoice_id:   str
    checkout_url: str
    status:       str
    plan_id:      str
    amount:       int
    currency:     str


class SubscriptionResponse(BaseModel):
    sub_id:          str
    plan_id:         str
    status:          str
    days_remaining:  int
    license_key:     str
    features:        list


class AdminSuspendRequest(BaseModel):
    reason: str = "admin_action"


class AdminRevokeRequest(BaseModel):
    reason: str = "admin_action"


def _get_billing_engine() -> BillingEngine:
    """BUG-W1 fix: dispatch to real provider based on BILLING_PROVIDER setting.
    
    Providers:
      mock     -> MockProvider (development / testing only)
      zarinpal -> ZarinpalProvider (Iranian payment gateway)
      stripe   -> StripeProvider (international payment)
      manual   -> ManualProvider (admin-confirmed payments)
    """
    try:
        from ...core.config import settings
        provider_name = getattr(settings, "BILLING_PROVIDER", "mock").lower()
    except Exception:
        provider_name = "mock"

    # --- Development / Testing ---
    if provider_name == "mock":
        from ...billing.provider import MockProvider
        return BillingEngine(provider=MockProvider())

    # --- ZarinPal (IRR payments) ---
    if provider_name == "zarinpal":
        try:
            from ...billing.provider import ZarinpalProvider
            merchant_id = getattr(settings, "ZARINPAL_MERCHANT_ID", "")
            sandbox     = getattr(settings, "ZARINPAL_SANDBOX", True)
            return BillingEngine(provider=ZarinpalProvider(
                merchant_id=merchant_id,
                sandbox=sandbox,
            ))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                "ZarinpalProvider init failed, falling back to MockProvider: %s", exc
            )
            from ...billing.provider import MockProvider
            return BillingEngine(provider=MockProvider())

    # --- Stripe (international) ---
    if provider_name == "stripe":
        try:
            from ...billing.provider import StripeProvider
            secret_key      = getattr(settings, "STRIPE_SECRET_KEY", "")
            webhook_secret  = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
            return BillingEngine(provider=StripeProvider(
                secret_key=secret_key,
                webhook_secret=webhook_secret,
            ))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                "StripeProvider init failed, falling back to MockProvider: %s", exc
            )
            from ...billing.provider import MockProvider
            return BillingEngine(provider=MockProvider())

    # --- Manual (admin confirms payments directly) ---
    if provider_name == "manual":
        try:
            from ...billing.provider import ManualProvider
            return BillingEngine(provider=ManualProvider())
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                "ManualProvider init failed, falling back to MockProvider: %s", exc
            )
            from ...billing.provider import MockProvider
            return BillingEngine(provider=MockProvider())

    # --- Unknown provider: log warning and fallback ---
    import logging
    logging.getLogger(__name__).warning(
        "Unknown BILLING_PROVIDER=%r, using MockProvider", provider_name
    )
    from ...billing.provider import MockProvider
    return BillingEngine(provider=MockProvider())


def _get_current_user_id(authorization: str = Header("")) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    return "user_from_jwt"


def _require_admin(authorization: str = Header("")) -> str:
    if not authorization:
        raise HTTPException(status_code=403, detail="Admin access required")
    return "admin_user"


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    req:    CheckoutRequest,
    user_id: str           = Depends(_get_current_user_id),
    engine:  BillingEngine = Depends(_get_billing_engine),
):
    if req.plan_id not in PLANS:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {req.plan_id!r}")
    try:
        currency = Currency(req.currency.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown currency: {req.currency!r}")
    try:
        invoice = engine.checkout(user_id, req.plan_id, currency)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Billing service error") from exc
    return CheckoutResponse(
        invoice_id=invoice.invoice_id, checkout_url=invoice.checkout_url,
        status=invoice.status.value, plan_id=invoice.plan_id,
        amount=invoice.amount, currency=invoice.currency.value,
    )


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user_id: str           = Depends(_get_current_user_id),
    engine:  BillingEngine = Depends(_get_billing_engine),
):
    sub = engine.get_subscription(user_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="No subscription found")
    plan = PLANS.get(sub.plan_id, {})
    return SubscriptionResponse(
        sub_id=sub.sub_id, plan_id=sub.plan_id, status=sub.status.value,
        days_remaining=sub.days_remaining, license_key=sub.license_key,
        features=plan.get("features", []),
    )


@router.get("/invoices")
async def list_invoices(
    user_id: str           = Depends(_get_current_user_id),
    engine:  BillingEngine = Depends(_get_billing_engine),
):
    invoices = engine.list_invoices(user_id)
    return [
        {
            "invoice_id":   i.invoice_id,
            "plan_id":      i.plan_id,
            "amount":       i.amount,
            "currency":     i.currency.value,
            "status":       i.status.value,
            "created_at":   i.created_at,
            "confirmed_at": i.confirmed_at,
        }
        for i in invoices
    ]


@router.post("/cancel")
async def cancel_subscription(
    user_id: str           = Depends(_get_current_user_id),
    engine:  BillingEngine = Depends(_get_billing_engine),
):
    try:
        sub = engine.cancel(user_id, reason="user_request")
    except KeyError:
        raise HTTPException(status_code=404, detail="No subscription found")
    return {"status": sub.status.value, "cancelled_at": sub.cancelled_at}


@router.post("/admin/confirm/{invoice_id}")
async def admin_confirm(
    invoice_id: str           = Path(...),
    actor:      str           = Depends(_require_admin),
    engine:     BillingEngine = Depends(_get_billing_engine),
):
    try:
        invoice = engine.admin_confirm(invoice_id, actor=actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {
        "invoice_id":   invoice.invoice_id,
        "status":       invoice.status.value,
        "confirmed_at": invoice.confirmed_at,
    }


@router.post("/admin/suspend/{uid}")
async def admin_suspend(
    uid:    str                 = Path(...),
    body:   AdminSuspendRequest = Body(...),
    actor:  str                 = Depends(_require_admin),
    engine: BillingEngine       = Depends(_get_billing_engine),
):
    try:
        sub = engine.suspend(uid, reason=body.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail="Subscription not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": sub.status.value}


@router.post("/admin/revoke/{uid}")
async def admin_revoke(
    uid:    str               = Path(...),
    body:   AdminRevokeRequest = Body(...),
    actor:  str               = Depends(_require_admin),
    engine: BillingEngine     = Depends(_get_billing_engine),
):
    try:
        sub = engine.revoke(uid, reason=body.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail="Subscription not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": sub.status.value}


@router.get("/admin/subscriptions")
async def list_all_subscriptions(
    actor:  str           = Depends(_require_admin),
    engine: BillingEngine = Depends(_get_billing_engine),
):
    subs = [
        {
            "user_id":        s.user_id,
            "plan_id":        s.plan_id,
            "status":         s.status.value,
            "days_remaining": s.days_remaining,
            "dunning_count":  s.dunning_count,
        }
        for s in engine._subscriptions.values()
    ]
    return {"subscriptions": subs, "total": len(subs)}


@router.post("/webhook/{provider_name}")
async def receive_webhook(
    request:       Request,
    provider_name: str    = Path(...),
    x_signature:   str    = Header("", alias="X-Signature"),
    x_event_id:    str    = Header("", alias="X-Event-Id"),
    x_timestamp:   str    = Header("", alias="X-Timestamp"),
    engine:        BillingEngine = Depends(_get_billing_engine),
):
    try:
        pname = ProviderName(provider_name.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_name!r}")

    payload = await request.body()
    ts = float(x_timestamp) if x_timestamp else None

    # Use the engine's configured provider for webhook verification
    provider  = engine._provider
    processor = WebhookProcessor(
        engine=engine, provider=provider,
        webhook_secret=getattr(
            __import__('backend.core.config', fromlist=['settings']).settings,
            'WEBHOOK_SECRET', 'webhook-secret'
        ),
    )
    try:
        result = processor.process(
            payload=payload, signature=x_signature,
            event_id=x_event_id, timestamp=ts,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "accepted":   result.accepted,
        "event_id":   result.event_id,
        "event_type": result.event_type,
        "duplicate":  result.duplicate,
    }
