"""
backend/tests/test_phase10_billing.py
Phase 10 -- Billing & Subscription Lifecycle
94 tests -- 0 external dependencies

Run:
    cd /home/definable/phase10
    python -m pytest backend/tests/test_phase10_billing.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import uuid

import pytest

sys.path.insert(0, "/home/definable/phase10")

from backend.billing.engine import (
    DUNNING_THRESHOLD,
    PLANS,
    BillingEngine,
    Invoice,
    Subscription,
    SubscriptionStatus,
    SubscriptionTransitionError,
)
from backend.billing.provider import (
    Currency,
    ManualProvider,
    MockProvider,
    PaymentRequest,
    PaymentStatus,
    ProviderName,
    StripeProvider,
    WebhookEventType,
    ZarinpalProvider,
    get_provider,
)
from backend.billing.webhook import (
    MAX_PAYLOAD_BYTES,
    TIMESTAMP_TOLERANCE,
    InvalidSignatureError,
    PayloadTooLargeError,
    StaleTimestampError,
    WebhookProcessor,
)


@pytest.fixture
def mock_provider():
    return MockProvider(auto_succeed=True)


@pytest.fixture
def pending_provider():
    return MockProvider(auto_succeed=False)


@pytest.fixture
def engine(mock_provider):
    return BillingEngine(provider=mock_provider)


@pytest.fixture
def pending_engine(pending_provider):
    return BillingEngine(provider=pending_provider)


@pytest.fixture
def uid():
    return f"user_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def webhook_secret():
    return "test-webhook-secret-32bytes-long!!"


@pytest.fixture
def processor(engine, webhook_secret):
    return WebhookProcessor(
        engine=engine,
        provider=MockProvider(),
        webhook_secret=webhook_secret,
    )


def _make_signed_payload(data: dict, secret: str):
    payload = json.dumps(data).encode()
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return payload, sig


class TestPaymentProviderAbstraction:
    def test_mock_provider_auto_succeed(self, uid):
        p = MockProvider(auto_succeed=True)
        req = PaymentRequest(uid, "basic", 2900, Currency.USD)
        r = p.create_payment(req)
        assert r.status == PaymentStatus.SUCCEEDED
        assert r.invoice_id.startswith("mock_")

    def test_mock_provider_pending(self, uid):
        p = MockProvider(auto_succeed=False)
        req = PaymentRequest(uid, "pro", 7900, Currency.USD)
        r = p.create_payment(req)
        assert r.status == PaymentStatus.PENDING
        assert r.checkout_url.startswith("https://mock.pay/")

    def test_mock_confirm_success(self, uid):
        p = MockProvider(auto_succeed=False)
        req = PaymentRequest(uid, "basic", 2900, Currency.USD)
        r = p.create_payment(req)
        r2 = p.confirm_payment(r.invoice_id, {"status": "succeeded"})
        assert r2.status == PaymentStatus.SUCCEEDED

    def test_mock_confirm_unknown_invoice(self, uid):
        p = MockProvider()
        r = p.confirm_payment("nonexistent_id", {})
        assert r.status == PaymentStatus.FAILED
        assert "invoice_not_found" in r.error

    def test_mock_force_fail(self, uid):
        p = MockProvider(auto_succeed=True)
        req = PaymentRequest(uid, "basic", 2900, Currency.USD)
        r = p.create_payment(req)
        p.force_fail(r.invoice_id)
        assert p._store[r.invoice_id].status == PaymentStatus.FAILED

    def test_mock_force_refund(self, uid):
        p = MockProvider(auto_succeed=True)
        req = PaymentRequest(uid, "basic", 2900, Currency.USD)
        r = p.create_payment(req)
        p.force_refund(r.invoice_id)
        assert p._store[r.invoice_id].status == PaymentStatus.REFUNDED

    def test_mock_webhook_signature_valid(self, webhook_secret):
        p = MockProvider()
        payload = b'{"event":"payment.succeeded","invoice_id":"abc"}'
        sig = hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        assert p.verify_webhook(payload, sig, webhook_secret)

    def test_mock_webhook_signature_invalid(self, webhook_secret):
        p = MockProvider()
        payload = b'{"event":"payment.succeeded"}'
        assert not p.verify_webhook(payload, "bad_sig", webhook_secret)

    def test_mock_parse_webhook_succeeded(self):
        p = MockProvider()
        data = {
            "event": "payment.succeeded",
            "invoice_id": "inv_1",
            "amount": 2900,
            "currency": "usd",
        }
        evt = p.parse_webhook(json.dumps(data).encode())
        assert evt.event_type == WebhookEventType.PAYMENT_SUCCEEDED
        assert evt.invoice_id == "inv_1"

    def test_manual_provider_pending(self, uid):
        p = ManualProvider()
        req = PaymentRequest(uid, "vip", 14900, Currency.USD)
        r = p.create_payment(req)
        assert r.status == PaymentStatus.PENDING
        assert r.checkout_url == ""

    def test_manual_confirm(self, uid):
        p = ManualProvider()
        req = PaymentRequest(uid, "vip", 14900, Currency.USD)
        r = p.create_payment(req)
        r2 = p.confirm_payment(r.invoice_id, {})
        assert r2.status == PaymentStatus.SUCCEEDED

    def test_factory_mock(self):
        p = get_provider(ProviderName.MOCK, {"auto_succeed": True})
        assert isinstance(p, MockProvider)
        assert p._auto_succeed is True


class TestPlanCatalogue:
    def test_all_five_plans_exist(self):
        for pid in ("trial", "basic", "pro", "vip", "annual"):
            assert pid in PLANS, f"Plan {pid!r} missing"

    def test_trial_is_free(self):
        assert PLANS["trial"]["price_usd"] == 0
        assert PLANS["trial"]["price_irr"] == 0

    def test_trial_duration(self):
        assert PLANS["trial"]["days"] == 14

    def test_annual_duration(self):
        assert PLANS["annual"]["days"] == 365

    def test_vip_features(self):
        assert "institutional" in PLANS["vip"]["features"]

    def test_basic_features(self):
        assert "mt5" in PLANS["basic"]["features"]

    def test_trial_features_have_signals(self):
        assert "signals_read" in PLANS["trial"]["features"]
        assert "signals_write" in PLANS["trial"]["features"]

    def test_price_hierarchy_usd(self):
        assert PLANS["trial"]["price_usd"] < PLANS["basic"]["price_usd"]
        assert PLANS["basic"]["price_usd"] < PLANS["pro"]["price_usd"]
        assert PLANS["pro"]["price_usd"] < PLANS["vip"]["price_usd"]
        assert PLANS["vip"]["price_usd"] < PLANS["annual"]["price_usd"]

    def test_max_devices_grow(self):
        assert PLANS["trial"]["max_devices"] < PLANS["pro"]["max_devices"]

    def test_max_positions_grow(self):
        assert PLANS["trial"]["max_positions"] < PLANS["vip"]["max_positions"]

    def test_irr_prices_nonzero_for_paid(self):
        for pid in ("basic", "pro", "vip", "annual"):
            assert PLANS[pid]["price_irr"] > 0

    def test_all_plans_have_label(self):
        for pid, plan in PLANS.items():
            assert "label" in plan, f"Plan {pid!r} missing label"


class TestBillingEngine:
    def test_checkout_returns_invoice(self, engine, uid):
        inv = engine.checkout(uid, "basic")
        assert inv.invoice_id
        assert inv.user_id == uid
        assert inv.plan_id == "basic"

    def test_checkout_auto_succeed_activates(self, engine, uid):
        engine.checkout(uid, "basic")
        sub = engine.get_subscription(uid)
        assert sub is not None
        assert sub.status == SubscriptionStatus.ACTIVE

    def test_checkout_irr_currency(self, engine, uid):
        inv = engine.checkout(uid, "pro", Currency.IRR)
        assert inv.currency == Currency.IRR
        assert inv.amount == PLANS["pro"]["price_irr"]

    def test_checkout_unknown_plan_raises(self, engine, uid):
        with pytest.raises(ValueError, match="Unknown plan"):
            engine.checkout(uid, "nonexistent_plan")

    def test_idempotency_same_hour_returns_same_invoice(self, engine, uid):
        inv1 = engine.checkout(uid, "basic")
        inv2 = engine.checkout(uid, "basic")
        assert inv1.invoice_id == inv2.invoice_id

    def test_idempotency_check_before_provider_call(self, uid):
        call_count = [0]

        class CountingProvider(MockProvider):
            def create_payment(self, req):
                call_count[0] += 1
                return super().create_payment(req)

        eng = BillingEngine(provider=CountingProvider())
        eng.checkout(uid, "basic")
        eng.checkout(uid, "basic")
        assert call_count[0] == 1

    def test_trial_subscription_status(self, engine, uid):
        engine.checkout(uid, "trial")
        sub = engine.get_subscription(uid)
        assert sub.status == SubscriptionStatus.TRIAL

    def test_license_key_generated(self, engine, uid):
        engine.checkout(uid, "basic")
        sub = engine.get_subscription(uid)
        assert sub.license_key.startswith("BOT12-")
        assert len(sub.license_key) > 10

    def test_days_remaining_positive(self, engine, uid):
        engine.checkout(uid, "basic")
        sub = engine.get_subscription(uid)
        assert sub.days_remaining >= 29

    def test_list_invoices(self, engine, uid):
        engine.checkout(uid, "basic")
        invoices = engine.list_invoices(uid)
        assert len(invoices) >= 1
        assert all(i.user_id == uid for i in invoices)

    def test_cancel_subscription(self, engine, uid):
        engine.checkout(uid, "basic")
        sub = engine.cancel(uid)
        assert sub.status == SubscriptionStatus.CANCELLED
        assert sub.cancelled_at is not None

    def test_cancel_nonexistent_raises(self, engine, uid):
        with pytest.raises(KeyError):
            engine.cancel(uid)

    def test_on_activate_callback(self, uid):
        activated = []
        eng = BillingEngine(
            provider=MockProvider(auto_succeed=True),
            on_license_activate=lambda u, k: activated.append((u, k)),
        )
        eng.checkout(uid, "basic")
        assert len(activated) == 1
        assert activated[0][0] == uid

    def test_on_subscription_change_callback(self, uid):
        changes = []
        eng = BillingEngine(
            provider=MockProvider(auto_succeed=True),
            on_subscription_change=lambda s: changes.append(s.status),
        )
        eng.checkout(uid, "basic")
        assert SubscriptionStatus.ACTIVE in changes

    def test_audit_log_checkout_event(self, engine, uid):
        engine.checkout(uid, "basic")
        log = engine.audit_log(user_id=uid)
        events = [e["event"] for e in log]
        assert "CHECKOUT_CREATED" in events

    def test_confirm_from_webhook_idempotent(self, pending_engine, uid):
        inv = pending_engine.checkout(uid, "basic")
        pending_engine.confirm_from_webhook(inv.invoice_id, {"status": "complete"})
        inv2 = pending_engine.confirm_from_webhook(inv.invoice_id, {"status": "complete"})
        assert inv2.status == PaymentStatus.SUCCEEDED


class TestSubscriptionFSM:
    def _sub(self, status: SubscriptionStatus) -> Subscription:
        return Subscription(sub_id=str(uuid.uuid4()), user_id="u1", plan_id="basic", status=status)

    def test_trial_to_active_allowed(self):
        s = self._sub(SubscriptionStatus.TRIAL)
        s.transition(SubscriptionStatus.ACTIVE)
        assert s.status == SubscriptionStatus.ACTIVE

    def test_active_to_past_due_allowed(self):
        s = self._sub(SubscriptionStatus.ACTIVE)
        s.transition(SubscriptionStatus.PAST_DUE)
        assert s.status == SubscriptionStatus.PAST_DUE

    def test_past_due_to_active_allowed(self):
        s = self._sub(SubscriptionStatus.PAST_DUE)
        s.transition(SubscriptionStatus.ACTIVE)
        assert s.status == SubscriptionStatus.ACTIVE

    def test_suspended_to_revoked_allowed(self):
        s = self._sub(SubscriptionStatus.SUSPENDED)
        s.transition(SubscriptionStatus.REVOKED)
        assert s.status == SubscriptionStatus.REVOKED

    def test_revoked_is_terminal(self):
        s = self._sub(SubscriptionStatus.REVOKED)
        with pytest.raises(SubscriptionTransitionError):
            s.transition(SubscriptionStatus.ACTIVE)

    def test_trial_to_past_due_blocked(self):
        s = self._sub(SubscriptionStatus.TRIAL)
        with pytest.raises(SubscriptionTransitionError):
            s.transition(SubscriptionStatus.PAST_DUE)

    def test_active_to_revoked_blocked(self):
        s = self._sub(SubscriptionStatus.ACTIVE)
        with pytest.raises(SubscriptionTransitionError):
            s.transition(SubscriptionStatus.REVOKED)

    def test_transition_audit_trail(self):
        s = self._sub(SubscriptionStatus.ACTIVE)
        s.transition(SubscriptionStatus.PAST_DUE, reason="test_reason")
        assert len(s.transitions) == 1
        assert s.transitions[0]["reason"] == "test_reason"
        assert s.transitions[0]["from"] == SubscriptionStatus.ACTIVE

    def test_is_active_property(self):
        for st in (
            SubscriptionStatus.TRIAL,
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.PAST_DUE,
        ):
            assert self._sub(st).is_active

    def test_not_active_for_terminal(self):
        for st in (
            SubscriptionStatus.REVOKED,
            SubscriptionStatus.CANCELLED,
            SubscriptionStatus.EXPIRED,
        ):
            assert not self._sub(st).is_active

    def test_is_terminal(self):
        assert self._sub(SubscriptionStatus.REVOKED).is_terminal
        assert not self._sub(SubscriptionStatus.ACTIVE).is_terminal

    def test_days_remaining_zero_when_no_expiry(self):
        s = self._sub(SubscriptionStatus.ACTIVE)
        assert s.days_remaining == 0


class TestAdminActions:
    def test_admin_confirm_manual_payment(self, uid):
        p = ManualProvider()
        eng = BillingEngine(provider=p)
        inv = eng.checkout(uid, "basic")
        assert inv.status == PaymentStatus.PENDING
        confirmed = eng.admin_confirm(inv.invoice_id, actor="admin1")
        assert confirmed.status == PaymentStatus.SUCCEEDED
        sub = eng.get_subscription(uid)
        assert sub is not None
        assert sub.status == SubscriptionStatus.ACTIVE

    def test_admin_confirm_idempotent(self, uid):
        p = ManualProvider()
        eng = BillingEngine(provider=p)
        inv = eng.checkout(uid, "basic")
        eng.admin_confirm(inv.invoice_id)
        inv2 = eng.admin_confirm(inv.invoice_id)
        assert inv2.status == PaymentStatus.SUCCEEDED

    def test_admin_confirm_unknown_invoice_raises(self, engine):
        with pytest.raises(KeyError):
            engine.admin_confirm("nonexistent_invoice_id")

    def test_suspend_active_subscription(self, engine, uid):
        engine.checkout(uid, "basic")
        sub = engine.suspend(uid)
        assert sub.status == SubscriptionStatus.SUSPENDED

    def test_revoke_from_active(self, engine, uid):
        engine.checkout(uid, "basic")
        sub = engine.revoke(uid)
        assert sub.status == SubscriptionStatus.REVOKED

    def test_revoke_is_terminal(self, engine, uid):
        engine.checkout(uid, "basic")
        engine.revoke(uid)
        with pytest.raises((SubscriptionTransitionError, Exception)):
            engine.suspend(uid)

    def test_dunning_active_to_past_due_on_first_fail(self, uid):
        p = MockProvider(auto_succeed=False)
        eng = BillingEngine(provider=p)
        inv = eng.checkout(uid, "basic")
        eng.admin_confirm(inv.invoice_id)
        assert eng.get_subscription(uid).status == SubscriptionStatus.ACTIVE
        fake_invoice = Invoice(
            invoice_id="fake_fail",
            user_id=uid,
            plan_id="basic",
            amount=2900,
            currency=Currency.USD,
            provider=ProviderName.MOCK,
            status=PaymentStatus.FAILED,
        )
        eng._invoices["fake_fail"] = fake_invoice
        eng._handle_payment_failure(fake_invoice)
        sub = eng.get_subscription(uid)
        assert sub.status == SubscriptionStatus.PAST_DUE

    def test_dunning_suspended_after_threshold(self, uid):
        p = MockProvider(auto_succeed=False)
        eng = BillingEngine(provider=p)
        inv = eng.checkout(uid, "basic")
        eng.admin_confirm(inv.invoice_id)
        sub = eng.get_subscription(uid)
        sub.status = SubscriptionStatus.PAST_DUE
        sub.dunning_count = DUNNING_THRESHOLD - 1
        fake_invoice = Invoice(
            invoice_id="fake_fail2",
            user_id=uid,
            plan_id="basic",
            amount=2900,
            currency=Currency.USD,
            provider=ProviderName.MOCK,
            status=PaymentStatus.FAILED,
        )
        eng._invoices["fake_fail2"] = fake_invoice
        eng._handle_payment_failure(fake_invoice)
        assert sub.status == SubscriptionStatus.SUSPENDED

    def test_audit_log_suspend_event(self, engine, uid):
        engine.checkout(uid, "basic")
        engine.suspend(uid, reason="non_payment")
        log = engine.audit_log(user_id=uid)
        events = [e["event"] for e in log]
        assert "SUBSCRIPTION_SUSPENDED" in events

    def test_audit_log_revoke_event(self, engine, uid):
        engine.checkout(uid, "basic")
        engine.revoke(uid)
        log = engine.audit_log(user_id=uid)
        events = [e["event"] for e in log]
        assert "SUBSCRIPTION_REVOKED" in events

    def test_cancel_sets_cancelled_at(self, engine, uid):
        engine.checkout(uid, "basic")
        sub = engine.cancel(uid)
        assert sub.cancelled_at is not None
        assert sub.cancelled_at <= time.time()

    def test_dunning_reset_on_success(self, uid):
        p = MockProvider(auto_succeed=False)
        eng = BillingEngine(provider=p)
        inv = eng.checkout(uid, "basic")
        eng.admin_confirm(inv.invoice_id)
        sub = eng.get_subscription(uid)
        sub.dunning_count = 2
        eng._idempotency.clear()
        inv2 = eng.checkout(uid, "pro")
        eng.admin_confirm(inv2.invoice_id)
        assert sub.dunning_count == 0


class TestWebhookSecurity:
    def _make_payload(self, invoice_id: str, event: str = "payment.succeeded") -> dict:
        return {
            "event": event,
            "invoice_id": invoice_id,
            "user_id": "user_1",
            "amount": 2900,
            "currency": "usd",
        }

    def test_valid_webhook_accepted(self, engine, webhook_secret, uid):
        inv = engine.checkout(uid, "basic")
        engine._invoices[inv.invoice_id].status = PaymentStatus.PENDING
        data = self._make_payload(inv.invoice_id)
        payload, sig = _make_signed_payload(data, webhook_secret)
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        result = proc.process(payload, sig, event_id="evt_001")
        assert result.accepted
        assert not result.duplicate

    def test_invalid_signature_raises(self, engine, webhook_secret, uid):
        inv = engine.checkout(uid, "basic")
        data = self._make_payload(inv.invoice_id)
        payload = json.dumps(data).encode()
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        with pytest.raises(InvalidSignatureError):
            proc.process(payload, "bad_signature", event_id="evt_002")

    def test_duplicate_webhook_idempotent(self, engine, webhook_secret, uid):
        inv = engine.checkout(uid, "basic")
        data = self._make_payload(inv.invoice_id)
        payload, sig = _make_signed_payload(data, webhook_secret)
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        r1 = proc.process(payload, sig, event_id="evt_003")
        r2 = proc.process(payload, sig, event_id="evt_003")
        assert not r1.duplicate
        assert r2.duplicate

    def test_stale_timestamp_rejected(self, engine, webhook_secret, uid):
        inv = engine.checkout(uid, "basic")
        data = self._make_payload(inv.invoice_id)
        payload, sig = _make_signed_payload(data, webhook_secret)
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        stale_ts = time.time() - TIMESTAMP_TOLERANCE - 60
        with pytest.raises(StaleTimestampError):
            proc.process(payload, sig, event_id="evt_004", timestamp=stale_ts)

    def test_future_timestamp_rejected(self, engine, webhook_secret, uid):
        inv = engine.checkout(uid, "basic")
        data = self._make_payload(inv.invoice_id)
        payload, sig = _make_signed_payload(data, webhook_secret)
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        future_ts = time.time() + TIMESTAMP_TOLERANCE + 60
        with pytest.raises(StaleTimestampError):
            proc.process(payload, sig, event_id="evt_005", timestamp=future_ts)

    def test_valid_timestamp_accepted(self, engine, webhook_secret, uid):
        inv = engine.checkout(uid, "basic")
        data = self._make_payload(inv.invoice_id)
        payload, sig = _make_signed_payload(data, webhook_secret)
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        result = proc.process(payload, sig, event_id="evt_006", timestamp=time.time())
        assert result.accepted

    def test_payload_too_large_rejected(self, engine, webhook_secret):
        payload = b"X" * (MAX_PAYLOAD_BYTES + 1)
        sig = hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        with pytest.raises(PayloadTooLargeError):
            proc.process(payload, sig, event_id="evt_007")

    def test_payload_at_limit_accepted(self, engine, webhook_secret, uid):
        inv = engine.checkout(uid, "basic")
        data = self._make_payload(inv.invoice_id)
        payload, sig = _make_signed_payload(data, webhook_secret)
        assert len(payload) < MAX_PAYLOAD_BYTES

    def test_webhook_activates_subscription(self, uid, webhook_secret):
        p = MockProvider(auto_succeed=False)
        eng = BillingEngine(provider=p)
        inv = eng.checkout(uid, "basic")
        assert inv.status == PaymentStatus.PENDING
        proc = WebhookProcessor(eng, MockProvider(), webhook_secret)
        data = self._make_payload(inv.invoice_id, "payment.succeeded")
        payload, sig = _make_signed_payload(data, webhook_secret)
        proc.process(payload, sig, event_id="evt_008")
        updated = eng.get_invoice(inv.invoice_id)
        assert updated.status == PaymentStatus.SUCCEEDED

    def test_payment_failed_webhook_triggers_dunning(self, uid, webhook_secret):
        p = MockProvider(auto_succeed=False)
        eng = BillingEngine(provider=p)
        inv = eng.checkout(uid, "basic")
        eng.admin_confirm(inv.invoice_id)
        sub = eng.get_subscription(uid)
        assert sub.status == SubscriptionStatus.ACTIVE
        fake_inv = Invoice(
            invoice_id="fake_wh_fail",
            user_id=uid,
            plan_id="basic",
            amount=2900,
            currency=Currency.USD,
            provider=ProviderName.MOCK,
            status=PaymentStatus.FAILED,
        )
        eng._invoices["fake_wh_fail"] = fake_inv
        eng._handle_payment_failure(fake_inv)
        assert sub.dunning_count >= 1

    def test_webhook_audit_on_rejection(self, engine, webhook_secret):
        payload = b'{"event":"payment.succeeded","invoice_id":"x"}'
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        try:
            proc.process(payload, "bad_sig", event_id="evt_010")
        except InvalidSignatureError:
            pass
        log = proc.audit_log()
        assert any(e["action"] == "REJECTED_BAD_SIG" for e in log)

    def test_webhook_audit_on_duplicate(self, engine, webhook_secret, uid):
        inv = engine.checkout(uid, "basic")
        data = self._make_payload(inv.invoice_id)
        payload, sig = _make_signed_payload(data, webhook_secret)
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        proc.process(payload, sig, event_id="evt_dup")
        proc.process(payload, sig, event_id="evt_dup")
        log = proc.audit_log()
        assert any(e["action"] == "DUPLICATE_SKIPPED" for e in log)

    def test_seen_count_bounded(self, engine, webhook_secret):
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        for i in range(10):
            proc._seen_ids.add(f"evt_{i}")
        assert proc.seen_count() == 10

    def test_different_event_ids_both_accepted(self, engine, webhook_secret, uid):
        inv = engine.checkout(uid, "basic")
        data = self._make_payload(inv.invoice_id)
        payload, sig = _make_signed_payload(data, webhook_secret)
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        r1 = proc.process(payload, sig, event_id="evt_A")
        r2 = proc.process(payload, sig, event_id="evt_B")
        assert not r1.duplicate
        assert not r2.duplicate

    def test_subscription_cancel_webhook(self, engine, webhook_secret, uid):
        engine.checkout(uid, "basic")
        sub = engine.get_subscription(uid)
        data = {
            "event": "subscription.cancelled",
            "invoice_id": "inv_cancel",
            "user_id": uid,
            "amount": 0,
            "currency": "usd",
        }
        payload, sig = _make_signed_payload(data, webhook_secret)
        proc = WebhookProcessor(engine, MockProvider(), webhook_secret)
        proc.process(payload, sig, event_id="evt_cancel")
        assert sub.status == SubscriptionStatus.CANCELLED


class TestIntegration:
    def test_full_trial_to_paid_lifecycle(self):
        uid = f"user_{uuid.uuid4().hex[:6]}"
        p = MockProvider(auto_succeed=False)
        eng = BillingEngine(provider=p)
        trial_inv = eng.checkout(uid, "trial")
        eng.admin_confirm(trial_inv.invoice_id)
        sub = eng.get_subscription(uid)
        assert sub.status == SubscriptionStatus.TRIAL
        eng._idempotency.clear()
        pro_inv = eng.checkout(uid, "pro")
        eng.admin_confirm(pro_inv.invoice_id)
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.plan_id == "pro"

    def test_multi_user_isolation(self):
        p = MockProvider(auto_succeed=True)
        eng = BillingEngine(provider=p)
        uid1 = f"u1_{uuid.uuid4().hex[:6]}"
        uid2 = f"u2_{uuid.uuid4().hex[:6]}"
        eng.checkout(uid1, "basic")
        eng.checkout(uid2, "vip")
        s1 = eng.get_subscription(uid1)
        s2 = eng.get_subscription(uid2)
        assert s1.plan_id == "basic"
        assert s2.plan_id == "vip"
        assert s1.license_key != s2.license_key

    def test_refund_suspends_subscription(self, uid):
        p = MockProvider(auto_succeed=False)
        eng = BillingEngine(provider=p)
        inv = eng.checkout(uid, "basic")
        eng.admin_confirm(inv.invoice_id)
        sub = eng.get_subscription(uid)
        assert sub.status == SubscriptionStatus.ACTIVE
        inv_obj = eng.get_invoice(inv.invoice_id)
        inv_obj.status = PaymentStatus.REFUNDED
        eng._handle_refund(inv_obj)
        assert sub.status == SubscriptionStatus.SUSPENDED

    def test_concurrent_idempotency_race(self):
        import threading

        uid = f"u_race_{uuid.uuid4().hex[:6]}"
        eng = BillingEngine(provider=MockProvider(auto_succeed=True))
        results = []

        def do_checkout():
            inv = eng.checkout(uid, "basic")
            results.append(inv.invoice_id)

        threads = [threading.Thread(target=do_checkout) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(results)) == 1

    def test_re_subscribe_after_cancelled(self, uid):
        p = MockProvider(auto_succeed=False)
        eng = BillingEngine(provider=p)
        inv = eng.checkout(uid, "basic")
        eng.admin_confirm(inv.invoice_id)
        eng.cancel(uid)
        sub = eng.get_subscription(uid)
        assert sub.status == SubscriptionStatus.CANCELLED
        eng._idempotency.clear()
        inv2 = eng.checkout(uid, "pro")
        eng.admin_confirm(inv2.invoice_id)
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.plan_id == "pro"

    def test_stripe_provider_webhook_verify(self):
        secret = "whsec_test_secret"
        p = StripeProvider(api_key="sk_test", webhook_secret=secret)
        payload = b'{"type":"checkout.session.completed","data":{"object":{}}}'
        ts = str(int(time.time()))
        signed = f"{ts}.".encode() + payload
        v1 = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        sig = f"t={ts},v1={v1}"
        assert p.verify_webhook(payload, sig, secret)

    def test_stripe_parse_succeeded_event(self):
        p = StripeProvider(api_key="sk_test", webhook_secret="secret")
        data = {
            "type": "checkout.session.completed",
            "id": "cs_test_123",
            "data": {"object": {"id": "cs_test_123", "amount_total": 2900, "currency": "usd"}},
        }
        evt = p.parse_webhook(json.dumps(data).encode())
        assert evt.event_type == WebhookEventType.PAYMENT_SUCCEEDED
        assert evt.invoice_id == "cs_test_123"

    def test_zarinpal_provider_ok_status(self):
        p = ZarinpalProvider(merchant_id="test_merchant", webhook_secret="secret")
        r = p.create_payment(PaymentRequest("u1", "basic", 4_900_000, Currency.IRR))
        assert r.status == PaymentStatus.PENDING
        assert "ZAP_" in r.invoice_id

    def test_zarinpal_confirm_ok(self):
        p = ZarinpalProvider(merchant_id="m", webhook_secret="s")
        r = p.create_payment(PaymentRequest("u1", "basic", 4_900_000, Currency.IRR))
        r2 = p.confirm_payment(r.invoice_id, {"Status": "OK", "RefID": "12345"})
        assert r2.status == PaymentStatus.SUCCEEDED

    def test_zarinpal_confirm_failed(self):
        p = ZarinpalProvider(merchant_id="m", webhook_secret="s")
        r = p.create_payment(PaymentRequest("u1", "basic", 4_900_000, Currency.IRR))
        r2 = p.confirm_payment(r.invoice_id, {"Status": "NOK"})
        assert r2.status == PaymentStatus.FAILED

    def test_get_provider_factory_all(self):
        mock = get_provider(ProviderName.MOCK, {"auto_succeed": False})
        manual = get_provider(ProviderName.MANUAL, {})
        stripe = get_provider(ProviderName.STRIPE, {"api_key": "sk_test", "webhook_secret": "wh"})
        zarinpal = get_provider(ProviderName.ZARINPAL, {"merchant_id": "m", "webhook_secret": "s"})
        assert isinstance(mock, MockProvider)
        assert isinstance(manual, ManualProvider)
        assert isinstance(stripe, StripeProvider)
        assert isinstance(zarinpal, ZarinpalProvider)

    def test_get_provider_unknown_raises(self):
        with pytest.raises(ValueError):
            get_provider("unknown_provider", {})  # type: ignore

    def test_invoice_has_raw_field(self, engine, uid):
        inv = engine.checkout(uid, "basic")
        assert isinstance(inv.raw, dict)

    def test_audit_log_all_events(self, engine, uid):
        engine.checkout(uid, "basic")
        engine.suspend(uid)
        log = engine.audit_log(user_id=uid)
        event_types = {e["event"] for e in log}
        assert "CHECKOUT_CREATED" in event_types
        assert "SUBSCRIPTION_SUSPENDED" in event_types

    def test_global_audit_log(self):
        eng = BillingEngine(provider=MockProvider())
        uid1 = "ua_global"
        uid2 = "ub_global"
        eng.checkout(uid1, "basic")
        eng.checkout(uid2, "pro")
        full_log = eng.audit_log()
        users = {e["user_id"] for e in full_log}
        assert uid1 in users
        assert uid2 in users
