"""
backend/api/routes/billing.py
Phase 10 -- Billing API Routes

Customer routes (/billing/checkout, /subscription, /invoices, /cancel)
Admin routes (/admin/confirm, /admin/suspend, /admin/revoke)
Webhook routes (/webhook/{provider})
"""
from __future__ import annotations
import json, time
from typing import Optional
try:
    from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
    from pydantic import BaseModel, Field
    _FASTAPI = True
except ImportError:
    _FASTAPI = False
    class APIRouter:
        def __init__(self, **kw): pass
        def post(self, *a, **kw): return lambda f: f
        def get(self, *a, **kw): return lambda f: f
    class BaseModel:
        pass
    def Field(*a, **kw): return None

from ...billing.engine import BillingEngine, Currency, PLANS, SubscriptionStatus
from ...billing.provider import MockProvider, ProviderName, get_provider, ManualProvider
from ...billing.webhook import WebhookProcessor, sign_payload

class CheckoutRequest(BaseModel):
    plan_id: str
    currency: str = "USD"
    callback_url: str = ""

def _build_engine(provider_name: str = "mock", **kwargs) -> BillingEngine:
    try: provider = get_provider(provider_name, **kwargs)
    except: provider = MockProvider()
    return BillingEngine(provider)

_DEFAULT_ENGINE = _build_engine("mock")
_DEFAULT_WEBHOOK_SECRET = "test-webhook-secret"

def get_engine() -> BillingEngine: return _DEFAULT_ENGINE
def get_webhook_secret() -> str: return _DEFAULT_WEBHOOK_SECRET

router = APIRouter(prefix="/billing", tags=["billing"])

def _checkout_impl(user_id: str, req: CheckoutRequest, engine: BillingEngine) -> dict:
    try: currency = Currency(req.currency.upper())
    except ValueError: raise ValueError(f"Unsupported currency: {req.currency!r}")
    if req.plan_id not in PLANS: raise KeyError(f"Unknown plan: {req.plan_id!r}")
    inv, sub = engine.checkout(user_id=user_id, plan_id=req.plan_id, currency=currency, callback_url=req.callback_url)
    redirect_url = (inv.raw or {}).get("redirect_url", "") if inv.raw else ""
    return {"invoice_id": inv.invoice_id, "status": inv.status.value, "redirect_url": redirect_url or None, "subscription": {"sub_id": sub.sub_id, "plan_id": sub.plan_id, "status": sub.status.value, "expires_at": sub.expires_at, "days_remaining": sub.days_remaining, "license_key": sub.license_key}}

def _get_subscription_impl(user_id: str, engine: BillingEngine) -> dict:
    sub = engine.get_subscription(user_id)
    if sub is None: raise KeyError("no_subscription")
    return {"sub_id": sub.sub_id, "plan_id": sub.plan_id, "status": sub.status.value, "expires_at": sub.expires_at, "days_remaining": sub.days_remaining, "license_key": sub.license_key}

def _list_invoices_impl(user_id: str, engine: BillingEngine) -> list[dict]:
    return [{"invoice_id": i.invoice_id, "plan_id": i.plan_id, "amount": i.amount, "currency": i.currency.value, "status": i.status.value, "created_at": i.created_at, "paid_at": i.paid_at} for i in engine.list_user_invoices(user_id)]

def _admin_confirm_impl(user_id: str, invoice_id: str, engine: BillingEngine) -> dict:
    inv = engine.admin_confirm_manual(user_id, invoice_id)
    return {"success": True, "invoice_id": inv.invoice_id, "status": inv.status.value}

def _admin_suspend_impl(user_id: str, reason: str, engine: BillingEngine) -> dict:
    sub = engine.suspend_subscription(user_id, reason)
    return {"success": True, "status": sub.status.value}

def _admin_revoke_impl(user_id: str, reason: str, engine: BillingEngine) -> dict:
    sub = engine.revoke_subscription(user_id, reason)
    return {"success": True, "status": sub.status.value}

def _webhook_impl(provider_name: str, payload: bytes, signature: str, event_id: str, timestamp: str, engine: BillingEngine, secret: str) -> dict:
    try: provider = get_provider(provider_name)
    except ValueError: return {"accepted": False, "error": f"unknown_provider:{provider_name}"}
    proc = WebhookProcessor(provider=provider, engine=engine, webhook_secret=secret)
    headers = {"x-webhook-signature": signature, "x-event-id": event_id, "x-webhook-timestamp": timestamp, "stripe-signature": signature}
    result = proc.process(payload, headers)
    return {"accepted": result.accepted, "event_id": result.event_id, "event_type": result.event_type, "duplicate": result.duplicate, "invoice_id": result.invoice_id, "error": result.error}
