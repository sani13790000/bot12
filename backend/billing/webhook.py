"""
backend/billing/webhook.py
Phase 10 — Secure, Idempotent Webhook Processor

Security guarantees:
  P10-WH-1: HMAC signature verified BEFORE any processing
  P10-WH-2: Idempotency — event_id stored; duplicate delivery * 200 OK, no double-action
  P10-WH-3: Timestamp tolerance ±5 min (Stripe-style) to block replay attacks
  P10-WH-4: Payload size cap (1 MB) — prevents DoS via huge payloads
  P10-WH-5: All events stored for audit (bounded 10K)
  P10-WH-6: Unknown event types — log + 200 (don't 4xx — provider retries)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .engine import BillingEngine
from .provider import PaymentProvider, PaymentStatus


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# Constants
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

_MAX_PAYLOAD_BYTES   = 1_048_576   # 1 MB
_TIMESTAMP_TOLERANCE = 300         # 5 minutes
_MAX_EVENT_STORE     = 10_000
_PROCESSED_IDS:      set[str] = set()
_EVENT_LOG:          list[dict] = []


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# Data models
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

@dataclass
class WebhookResult:
    accepted:   bool
    event_id:   str
    event_type: str
    duplicate:  bool   = False
    error:      Optional[str] = None
    invoice_id: Optional[str] = None


# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐
# WebhookProcessor
# ┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐┐

class WebhookProcessor:
    """
    Stateless processor — pass payload bytes + headers per call.

    Usage:
        proc = WebhookProcessor(provider, engine, webhook_secret)
        result = proc.process(payload, headers)
        if result.accepted:
            return 200
        elif result.error == "invalid_signature":
            return 400
    """

    def __init__(
        self,
        provider:       PaymentProvider,
        engine:         BillingEngine,
        webhook_secret: str,
    ) -> None:
        self._provider = provider
        self._engine   = engine
        self._secret   = webhook_secret

    # — Main entry ---------------------------------------------------------

    def process(self, payload: bytes, headers: dict) -> WebhookResult:
        # P10-WH-4: size cap
        if len(payload) > _MAX_PAYLOAD_BYTES:
            return WebhookResult(accepted=False, event_id="", event_type="", error="payload_too_large")

        # P10-WH-1: HMAC signature
        sig = headers.get("X-Signature", "") or headers.get("X-Hub-Signature-256", "")
        if not self._provider.verify_webhook_signature(payload, sig):
            return WebhookResult(accepted=False, event_id="", event_type="", error="invalid_signature")

        # Parse payload
        try:
            data = json.loads(payload)
        except Exception:
            return WebhookResult(accepted=False, event_id="", event_type="", error="invalid_json")

        event_id   = data.get("id", str(uuid.uuid4()))
        event_type = data.get("type", "")
        ts         = data.get("created", 0) or data.get("ts", 0)

        # P10-WH-3: timestamp tolerance
        if ts and abs(time.time() - ts) > _TIMESTAMP_TOLERANCE:
            return WebhookResult(accepted=False, event_id=event_id, event_type=event_type, error="timestamp_out_of_tolerance")

        # P10-WH-2: idempotency
        if event_id in _PROCESSED_IDS:
            return WebhookResult(accepted=True, event_id=event_id, event_type=event_type, duplicate=True)

        # Dispatch
        invoice_id = self._dispatch(event_type, data)

        # Mark processed
        _PROCESSED_IDS.add(event_id)
        if len(_PROCESSED_IDS) > _MAX_EVENT_STORE:
            _PROCESSED_IDS.pop()

        # P10-WH-5: audit log
        _EVENT_LOG.append({"id": event_id, "type": event_type, "ts": time.time()})
        if len(_EVENT_LOG) > _MAX_EVENT_STORE:
            _EVENT_LOG.pop(0)

        return WebhookResult(accepted=True, event_id=event_id, event_type=event_type, invoice_id=invoice_id)

    def _dispatch(self, event_type: str, data: dict) -> Optional[str]:
        obj = data.get("data", {}).get("object", data)
        provider_ref = obj.get("id", "") or obj.get("authority", "")
        invoice_id   = obj.get("invoice_id", "")

        if event_type in {"payment_intent.succeeded", "charge.succeeded", "payment.success"}:
            inv = self._engine.payment_success(provider_ref=provider_ref, invoice_id=invoice_id)
            return inv.invoice_id if inv else None
        elif event_type in {"payment_intent.payment_failed", "charge.failed", "payment.failed"}:
            self._engine.payment_failed(provider_ref=provider_ref)
            return None
        # P10-WH-6: unknown events — log and 200
        return None


def sign_payload(payload: bytes, secret: str) -> str:
    """Sign payload with HMAC-SHA256. Used by tests to generate valid sigs."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
