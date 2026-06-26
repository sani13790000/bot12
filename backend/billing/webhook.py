from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Optional, Set

from .provider import (
    PaymentProvider, ProviderName,
    WebhookEvent, WebhookEventType,
)
from .engine import BillingEngine


MAX_PAYLOAD_BYTES   = 1 * 1024 * 1024
TIMESTAMP_TOLERANCE = 300
NONCE_STORE_MAX     = 100_000


class WebhookError(Exception):
    pass

class InvalidSignatureError(WebhookError):
    pass

class ReplayAttackError(WebhookError):
    pass

class PayloadTooLargeError(WebhookError):
    pass

class StaleTimestampError(WebhookError):
    pass


@dataclass
class WebhookProcessResult:
    accepted:   bool
    event_id:   str
    event_type: str
    duplicate:  bool = False
    error:      str  = ""


class WebhookProcessor:
    def __init__(
        self,
        engine:         BillingEngine,
        provider:       PaymentProvider,
        webhook_secret: str,
    ) -> None:
        self._engine   = engine
        self._provider = provider
        self._secret   = webhook_secret
        self._seen_ids: Set[str] = set()
        self._audit: list = []

    def process(
        self,
        payload:   bytes,
        signature: str,
        event_id:  str            = "",
        timestamp: Optional[float] = None,
    ) -> WebhookProcessResult:
        # P10-WH-4: size cap
        if len(payload) > MAX_PAYLOAD_BYTES:
            self._audit_event("REJECTED_TOO_LARGE", event_id, error="payload_too_large")
            raise PayloadTooLargeError(
                f"Payload {len(payload)} bytes exceeds limit {MAX_PAYLOAD_BYTES}"
            )

        # P10-WH-3: timestamp tolerance
        if timestamp is not None:
            drift = abs(time.time() - timestamp)
            if drift > TIMESTAMP_TOLERANCE:
                self._audit_event("REJECTED_STALE_TS", event_id, error=f"drift={drift:.0f}s")
                raise StaleTimestampError(
                    f"Timestamp drift {drift:.0f}s exceeds +/-{TIMESTAMP_TOLERANCE}s"
                )

        # P10-WH-1: HMAC signature
        if not self._provider.verify_webhook(payload, signature, self._secret):
            self._audit_event("REJECTED_BAD_SIG", event_id, error="invalid_signature")
            raise InvalidSignatureError("Webhook signature mismatch")

        # P10-WH-2: idempotency
        if event_id and event_id in self._seen_ids:
            self._audit_event("DUPLICATE_SKIPPED", event_id)
            return WebhookProcessResult(
                accepted=True, event_id=event_id,
                event_type="duplicate", duplicate=True,
            )

        event: WebhookEvent = self._provider.parse_webhook(payload)
        if not event_id:
            event_id = event.invoice_id or f"evt_{int(time.time())}"

        if len(self._seen_ids) < NONCE_STORE_MAX:
            self._seen_ids.add(event_id)

        self._dispatch(event)

        self._audit_event(
            "PROCESSED", event_id,
            detail=f"type={event.event_type} invoice={event.invoice_id}",
        )

        return WebhookProcessResult(
            accepted=True, event_id=event_id, event_type=event.event_type.value,
        )

    def _dispatch(self, event: WebhookEvent) -> bool:
        try:
            if event.event_type == WebhookEventType.PAYMENT_SUCCEEDED:
                self._engine.confirm_from_webhook(event.invoice_id, event.raw)
            elif event.event_type == WebhookEventType.PAYMENT_FAILED:
                self._engine.confirm_from_webhook(event.invoice_id, event.raw)
            elif event.event_type == WebhookEventType.SUBSCRIPTION_CANCELLED:
                if event.user_id:
                    self._engine.cancel(event.user_id, reason="provider_cancelled")
            elif event.event_type == WebhookEventType.REFUND_ISSUED:
                self._engine.confirm_from_webhook(
                    event.invoice_id, {**event.raw, "status": "refunded"}
                )
            return True
        except KeyError:
            self._audit_event(
                "DISPATCH_KEY_ERROR", event.invoice_id, error="invoice_not_found"
            )
            return False

    def _audit_event(
        self, action: str, event_id: str,
        error: str = "", detail: str = "",
    ) -> None:
        self._audit.append({
            "action":   action,
            "event_id": event_id,
            "error":    error,
            "detail":   detail,
            "ts":       time.time(),
        })

    def audit_log(self) -> list:
        return list(self._audit)

    def seen_count(self) -> int:
        return len(self._seen_ids)
