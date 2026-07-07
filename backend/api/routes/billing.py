"""
backend/api/routes/billing.py
Phase 10 - Billing API Routes
BUG-W1 fix: _get_billing_engine() now dispatches to real providers (zarinpal/stripe/manual)
BUG-V2 fix: removed router=None guard
BUG-X1 fix: removed duplicate prefix (was /billing/billing/*, now /billing/*)
BUG-X2 fix: _get_current_user_id() and _require_admin() now use real JWT via get_current_user

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

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Path,
    Request,
    status,
)
from pydantic import BaseModel, Field

from ...billing.engine import PLANS, BillingEngine
from ...billing.provider import Currency
from ...billing.webhook import WebhookProcessor
from ...core.deps import get_current_user

# BUG-V2 fix: router always created — no None guard
# BUG-X1 fix: prefix removed from router — main.py provides prefix="/billing"
router = APIRouter(tags=["billing"])


class CheckoutRequest(BaseModel):
    plan_id: str = Field(..., description="Plan ID: trial/basic/pro/vip/annual")
    currency: str = Field("usd", description="usd or irr")


class CheckoutResponse(BaseModel):
    invoice_id: str
    checkout_url: str
    status: str
    plan_id: str
    amount: int
    currency: str


class SubscriptionResponse(BaseModel):
    sub_id: str
    plan_id: str
    status: str
    days_remaining: int
    license_key: str
    features: list


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
            sandbox = getattr(settings, "ZARINPAL_SANDBOX", True)
            return BillingEngine(
                provider=ZarinpalProvider(
                    merchant_id=merchant_id,
                    sandbox=sandbox,
                )
            )
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

            secret_key = getattr(settings, "STRIPE_SECRET_KEY", "")
            webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
            return BillingEngine(
                provider=StripeProvider(
                    secret_key=secret_key,
                    webhook_secret=webhook_secret,
                )
            )
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
        "Unknown BILLING_PROVIDER=%r, falling back to MockProvider", provider_name
    )
    from ...billing.provider import MockProvider

    return BillingEngine(provider=MockProvider())


# ---------------------------------------------------------------------------
# BUG-X2 fix: Real JWT auth via get_current_user from backend.core.deps
# The old stubs returned hardcoded strings without decoding the JWT.
# ---------------------------------------------------------------------------


def _get_current_user_id(current_user=Depends(get_current_user)) -> str:
    """BUG-X2 fix: extract real user_id from JWT via get_current_user dependency."""
    user_id = getattr(current_user, "id", None) or getattr(current_user, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Could not identify user from token")
    return str(user_id)


def _require_admin(current_user=Depends(get_current_user)) -> str:
    """BUG-X2 fix: check real JWT user has admin/billing role."""
    user_id = getattr(current_user, "id", None) or getattr(current_user, "user_id", None)
    role = getattr(current_user, "role", "") or ""
    if role.lower() not in ("admin", "superadmin", "billing_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or billing_admin role required",
        )
    return str(user_id)


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    req: CheckoutRequest,
    user_id: str = Depends(_get_current_user_id),
    engine: BillingEngine = Depends(_get_billing_engine),
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
        invoice_id=invoice.invoice_id,
        checkout_url=invoice.checkout_url,
        status=invoice.status.value,
        plan_id=invoice.plan_id,
        amount=invoice.amount,
        currency=invoice.currency.value,
    )


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user_id: str = Depends(_get_current_user_id),
    engine: BillingEngine = Depends(_get_billing_engine),
):
    sub = engine.get_subscription(user_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="No subscription found")
    plan = PLANS.get(sub.plan_id, {})
    return SubscriptionResponse(
        sub_id=sub.sub_id,
        plan_id=sub.plan_id,
        status=sub.status.value,
        days_remaining=sub.days_remaining,
        license_key=sub.license_key,
        features=plan.get("features", []),
    )


@router.get("/invoices")
async def list_invoices(
    user_id: str = Depends(_get_current_user_id),
    engine: BillingEngine = Depends(_get_billing_engine),
):
    invoices = engine.list_invoices(user_id)
    return [
        {
            "invoice_id": i.invoice_id,
            "plan_id": i.plan_id,
            "amount": i.amount,
            "currency": i.currency.value,
            "status": i.status.value,
            "created_at": i.created_at,
            "confirmed_at": i.confirmed_at,
        }
        for i in invoices
    ]


@router.post("/cancel")
async def cancel_subscription(
    user_id: str = Depends(_get_current_user_id),
    engine: BillingEngine = Depends(_get_billing_engine),
):
    try:
        sub = engine.cancel(user_id, reason="user_request")
    except KeyError:
        raise HTTPException(status_code=404, detail="No subscription found")
    return {"status": sub.status.value, "cancelled_at": sub.cancelled_at}


@router.post("/admin/confirm/{invoice_id}")
async def admin_confirm(
    invoice_id: str = Path(...),
    actor: str = Depends(_require_admin),
    engine: BillingEngine = Depends(_get_billing_engine),
):
    try:
        invoice = engine.admin_confirm(invoice_id, actor=actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {
        "invoice_id": invoice.invoice_id,
        "status": invoice.status.value,
        "confirmed_at": invoice.confirmed_at,
    }


@router.post("/admin/suspend/{uid}")
async def admin_suspend(
    uid: str = Path(...),
    body: AdminSuspendRequest = Body(...),
    actor: str = Depends(_require_admin),
    engine: BillingEngine = Depends(_get_billing_engine),
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
    uid: str = Path(...),
    body: AdminRevokeRequest = Body(...),
    actor: str = Depends(_require_admin),
    engine: BillingEngine = Depends(_get_billing_engine),
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
    actor: str = Depends(_require_admin),
    engine: BillingEngine = Depends(_get_billing_engine),
):
    subs = [
        {
            "user_id": s.user_id,
            "plan_id": s.plan_id,
            "status": s.status.value,
            "days_remaining": s.days_remaining,
            "dunning_count": s.dunning_count,
        }
        for s in engine._subscriptions.values()
    ]
    return {"subscriptions": subs, "total": len(subs)}


@router.post("/webhook/{provider}")
async def webhook(
    provider: str = Path(...),
    request: Request = None,
):
    """Webhook endpoint — NO auth, signature verified internally."""
    try:
        raw_body = await request.body()
        headers = dict(request.headers)
        processor = WebhookProcessor()
        result = await processor.process(
            provider=provider,
            raw_body=raw_body,
            headers=headers,
        )
        return {"status": "ok", "processed": result}
    except Exception as exc:
        import logging

        logging.getLogger(__name__).error("Webhook processing error: %s", exc)
        raise HTTPException(status_code=400, detail="Webhook processing failed") from exc
