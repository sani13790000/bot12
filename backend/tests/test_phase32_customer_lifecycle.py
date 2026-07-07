"""
PHASE 32 -- Customer Lifecycle Automation
216 tests: T001-T216
"""

import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.customer_lifecycle import (
    REQUIRES_REASON,
    SELF_SERVICE_ANSWERS,
    TEMPLATES,
    CustomerRecord,
    CustomerStatus,
    CustomerStore,
    LifecycleAuditChain,
    LifecycleAuditEntry,
    LifecycleDashboard,
    LifecycleEvent,
    MissingReasonError,
    NotificationChannel,
    NotificationEngine,
    NotificationRecord,
    NotificationTemplate,
    OnboardingStep,
    ReactivationOffer,
    TicketCategory,
    build_lifecycle_system,
)


def make_customer(
    cid="cust-1",
    tid="tenant-1",
    status=CustomerStatus.ACTIVE,
    expires_in_days: float = 30,
    plan: str = "pro",
) -> CustomerRecord:
    return CustomerRecord(
        customer_id=cid,
        tenant_id=tid,
        email=f"{cid}@example.com",
        status=status,
        plan=plan,
        expires_at=time.time() + expires_in_days * 86400,
    )


def make_sys(**kw):
    return build_lifecycle_system(**kw)


class TestEnumsAndConstants:
    def test_T001_lifecycle_events_count(self):
        assert len(LifecycleEvent) >= 28

    def test_T002_customer_status_values(self):
        vals = {s.value for s in CustomerStatus}
        assert "active" in vals and "churned" in vals

    def test_T003_onboarding_steps_count(self):
        assert len(OnboardingStep) == 6

    def test_T004_notification_channels(self):
        assert len(NotificationChannel) == 4

    def test_T005_ticket_categories(self):
        assert len(TicketCategory) >= 7

    def test_T006_requires_reason_set(self):
        assert LifecycleEvent.SUBSCRIPTION_CANCELLED in REQUIRES_REASON
        assert LifecycleEvent.REACTIVATION_DECLINED in REQUIRES_REASON
        assert LifecycleEvent.SUPPORT_TICKET_CLOSED in REQUIRES_REASON

    def test_T007_templates_count(self):
        assert len(TEMPLATES) >= 17

    def test_T008_all_templates_have_subject_and_body(self):
        for k, (s, b) in TEMPLATES.items():
            assert isinstance(s, str) and len(s) > 0
            assert isinstance(b, str) and len(b) > 0

    def test_T009_self_service_answers_coverage(self):
        for cat in [
            TicketCategory.DEVICE_SETUP,
            TicketCategory.LICENSE_ISSUE,
            TicketCategory.HEARTBEAT_FAIL,
            TicketCategory.DOWNLOAD_HELP,
            TicketCategory.PAYMENT_ISSUE,
        ]:
            assert cat.value in SELF_SERVICE_ANSWERS

    def test_T010_lifecycle_event_values_are_dotted(self):
        for e in LifecycleEvent:
            assert "." in e.value

    def test_T011_customer_record_defaults(self):
        c = CustomerRecord(customer_id="x", tenant_id="t", email="x@e.com")
        assert c.status == CustomerStatus.ONBOARDING
        assert c.device_count == 0

    def test_T012_customer_record_is_expired_false(self):
        assert not make_customer(expires_in_days=10).is_expired()

    def test_T013_customer_record_is_expired_true(self):
        assert make_customer(expires_in_days=-1).is_expired()

    def test_T014_days_until_expiry(self):
        c = make_customer(expires_in_days=5)
        assert 4.9 < c.days_until_expiry() < 5.1

    def test_T015_onboarding_complete_false(self):
        assert not make_customer().is_onboarding_complete()

    def test_T016_onboarding_complete_true(self):
        c = make_customer()
        c.onboarding_steps_done = [s.value for s in OnboardingStep]
        assert c.is_onboarding_complete()


class TestLifecycleAuditChain:
    def setup_method(self):
        self.audit = LifecycleAuditChain(secret="test-secret")

    def test_T017_record_returns_entry(self):
        e = self.audit.record("account.created", "c1", "t1", "system")
        assert isinstance(e, LifecycleAuditEntry) and e.event == "account.created"

    def test_T018_chain_hash_is_64_chars(self):
        e = self.audit.record("account.created", "c1", "t1", "system")
        assert len(e.chain_hash) == 64

    def test_T019_verify_chain_empty(self):
        assert self.audit.verify_chain() is True

    def test_T020_verify_chain_single(self):
        self.audit.record("account.created", "c1", "t1", "system")
        assert self.audit.verify_chain() is True

    def test_T021_verify_chain_multiple(self):
        for i in range(10):
            self.audit.record("onboarding.started", f"c{i}", "t1", "system")
        assert self.audit.verify_chain() is True

    def test_T022_tamper_detected(self):
        e = self.audit.record("account.created", "c1", "t1", "system")
        e.event = "TAMPERED"
        assert self.audit.verify_chain() is False

    def test_T023_detect_tampered_returns_seq(self):
        self.audit.record("account.created", "c1", "t1", "system")
        e = self.audit.record("onboarding.started", "c1", "t1", "system")
        e.event = "TAMPERED"
        assert e.seq in self.audit.detect_tampered()

    def test_T024_requires_reason_enforced(self):
        with pytest.raises(MissingReasonError):
            self.audit.record(
                LifecycleEvent.SUBSCRIPTION_CANCELLED.value, "c1", "t1", "admin", reason=""
            )

    def test_T025_requires_reason_whitespace_rejected(self):
        with pytest.raises(MissingReasonError):
            self.audit.record(
                LifecycleEvent.SUBSCRIPTION_CANCELLED.value, "c1", "t1", "admin", reason="   "
            )

    def test_T026_requires_reason_satisfied(self):
        e = self.audit.record(
            LifecycleEvent.SUBSCRIPTION_CANCELLED.value, "c1", "t1", "admin", reason="user request"
        )
        assert e.reason == "user request"

    def test_T027_seq_increments(self):
        e1 = self.audit.record("account.created", "c1", "t1", "s")
        e2 = self.audit.record("account.created", "c2", "t1", "s")
        assert e2.seq == e1.seq + 1

    def test_T028_query_by_customer(self):
        self.audit.record("account.created", "c1", "t1", "s")
        self.audit.record("account.created", "c2", "t1", "s")
        assert all(e.customer_id == "c1" for e in self.audit.query(customer_id="c1"))

    def test_T029_query_by_event(self):
        self.audit.record("account.created", "c1", "t1", "s")
        self.audit.record("onboarding.started", "c1", "t1", "s")
        assert all(e.event == "account.created" for e in self.audit.query(event="account.created"))

    def test_T030_query_limit(self):
        for i in range(20):
            self.audit.record("account.created", f"c{i}", "t1", "s")
        assert len(self.audit.query(limit=5)) == 5

    def test_T031_query_most_recent_first(self):
        self.audit.record("account.created", "c1", "t1", "s")
        self.audit.record("account.created", "c2", "t1", "s")
        result = self.audit.query()
        assert result[0].seq > result[1].seq

    def test_T032_len(self):
        for _ in range(5):
            self.audit.record("account.created", "c1", "t1", "s")
        assert len(self.audit) == 5

    def test_T033_concurrent_records_unique_seqs(self):
        seqs = []

        def worker():
            seqs.append(self.audit.record("account.created", "cx", "tx", "s").seq)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(set(seqs)) == 20

    def test_T034_verify_chain_after_concurrent(self):
        def worker():
            self.audit.record("account.created", "cx", "tx", "s")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert self.audit.verify_chain() is True

    def test_T035_chain_hash_different_per_entry(self):
        e1 = self.audit.record("account.created", "c1", "t1", "s")
        e2 = self.audit.record("account.created", "c2", "t1", "s")
        assert e1.chain_hash != e2.chain_hash

    def test_T036_detail_stored_in_entry(self):
        e = self.audit.record("account.created", "c1", "t1", "s", detail={"foo": "bar"})
        assert e.detail == {"foo": "bar"}


class TestCustomerStore:
    def setup_method(self):
        self.store = CustomerStore()

    def test_T037_upsert_and_get(self):
        c = make_customer("c1")
        self.store.upsert(c)
        assert self.store.get("c1") is c

    def test_T038_get_missing_returns_none(self):
        assert self.store.get("missing") is None

    def test_T039_len(self):
        self.store.upsert(make_customer("c1"))
        self.store.upsert(make_customer("c2"))
        assert len(self.store) == 2

    def test_T040_list_by_status(self):
        self.store.upsert(make_customer("c1", status=CustomerStatus.ACTIVE))
        self.store.upsert(make_customer("c2", status=CustomerStatus.EXPIRED))
        active = self.store.list_by_status(CustomerStatus.ACTIVE)
        assert len(active) == 1 and active[0].customer_id == "c1"

    def test_T041_list_by_status_tenant_filter(self):
        self.store.upsert(make_customer("c1", tid="T1", status=CustomerStatus.ACTIVE))
        self.store.upsert(make_customer("c2", tid="T2", status=CustomerStatus.ACTIVE))
        assert all(
            c.tenant_id == "T1"
            for c in self.store.list_by_status(CustomerStatus.ACTIVE, tenant_id="T1")
        )

    def test_T042_list_expiring(self):
        c = make_customer("c1", expires_in_days=3)
        self.store.upsert(c)
        assert c in self.store.list_expiring(within_days=7)
        assert c not in self.store.list_expiring(within_days=2)

    def test_T043_list_heartbeat_overdue(self):
        c = make_customer("c1")
        c.last_heartbeat = time.time() - 400
        self.store.upsert(c)
        assert c in self.store.list_heartbeat_overdue(threshold_s=300)

    def test_T044_list_heartbeat_not_overdue(self):
        c = make_customer("c1")
        c.last_heartbeat = time.time() - 100
        self.store.upsert(c)
        assert c not in self.store.list_heartbeat_overdue(threshold_s=300)

    def test_T045_count_by_status(self):
        self.store.upsert(make_customer("c1", status=CustomerStatus.ACTIVE))
        self.store.upsert(make_customer("c2", status=CustomerStatus.ACTIVE))
        self.store.upsert(make_customer("c3", status=CustomerStatus.EXPIRED))
        counts = self.store.count_by_status()
        assert counts["active"] == 2 and counts["expired"] == 1

    def test_T046_upsert_updates_record(self):
        c = make_customer("c1")
        self.store.upsert(c)
        c.plan = "enterprise"
        self.store.upsert(c)
        assert self.store.get("c1").plan == "enterprise"

    def test_T047_thread_safe_upsert(self):
        results = []

        def worker(i):
            self.store.upsert(make_customer(f"c{i}"))
            results.append(i)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(self.store) == 20

    def test_T048_list_expiring_excludes_expired(self):
        c = make_customer("c1", expires_in_days=-1)
        self.store.upsert(c)
        assert c not in self.store.list_expiring(within_days=7)

    def test_T049_heartbeat_overdue_no_last_heartbeat(self):
        c = make_customer("c1")
        c.last_heartbeat = None
        self.store.upsert(c)
        assert c not in self.store.list_heartbeat_overdue()

    def test_T050_multiple_tenant_isolation(self):
        for i in range(5):
            self.store.upsert(make_customer(f"c{i}", tid=f"T{i % 2}", status=CustomerStatus.ACTIVE))
        assert all(
            c.tenant_id == "T0"
            for c in self.store.list_by_status(CustomerStatus.ACTIVE, tenant_id="T0")
        )

    def test_T051_updated_at_changes(self):
        c = make_customer("c1")
        old = c.updated_at
        time.sleep(0.01)
        self.store.upsert(c)
        assert c.updated_at >= old

    def test_T052_count_by_status_empty(self):
        assert self.store.count_by_status() == {}


class TestNotificationEngine:
    def setup_method(self):
        self.audit = LifecycleAuditChain()
        self.notif = NotificationEngine(audit=self.audit)
        self.customer = make_customer()

    def test_T053_send_returns_record(self):
        r = self.notif.send(self.customer, NotificationTemplate.WELCOME)
        assert isinstance(r, NotificationRecord)

    def test_T054_notification_has_subject_and_body(self):
        r = self.notif.send(self.customer, NotificationTemplate.WELCOME)
        assert len(r.subject) > 0 and len(r.body) > 0

    def test_T055_count_sent(self):
        self.notif.send(self.customer, NotificationTemplate.WELCOME)
        self.notif.send(self.customer, NotificationTemplate.DOWNLOAD_GUIDE)
        assert self.notif.count_sent() == 2

    def test_T056_list_sent_by_customer(self):
        c2 = make_customer("c2")
        self.notif.send(self.customer, NotificationTemplate.WELCOME)
        self.notif.send(c2, NotificationTemplate.WELCOME)
        assert all(n.customer_id == "cust-1" for n in self.notif.list_sent(customer_id="cust-1"))

    def test_T057_list_sent_by_template(self):
        self.notif.send(self.customer, NotificationTemplate.WELCOME)
        self.notif.send(self.customer, NotificationTemplate.DOWNLOAD_GUIDE)
        assert all(
            n.event == NotificationTemplate.WELCOME.value
            for n in self.notif.list_sent(template=NotificationTemplate.WELCOME.value)
        )

    def test_T058_audit_record_created(self):
        self.notif.send(self.customer, NotificationTemplate.WELCOME)
        assert len(self.audit) > 0

    def test_T059_hook_called(self):
        called = []
        self.notif.add_hook(lambda r: called.append(r))
        self.notif.send(self.customer, NotificationTemplate.WELCOME)
        assert len(called) == 1

    def test_T060_hook_exception_does_not_raise(self):
        self.notif.add_hook(lambda r: 1 / 0)
        self.notif.send(self.customer, NotificationTemplate.WELCOME)

    def test_T061_params_injected(self):
        r = self.notif.send(
            self.customer,
            NotificationTemplate.DEVICE_REGISTERED,
            params={"device_id": "DEV-1", "count": 1, "max": 3},
        )
        assert "DEV-1" in r.body

    def test_T062_channel_stored(self):
        r = self.notif.send(
            self.customer, NotificationTemplate.WELCOME, channel=NotificationChannel.TELEGRAM
        )
        assert r.channel == NotificationChannel.TELEGRAM.value

    def test_T063_concurrent_send_safe(self):
        results = []

        def worker():
            results.append(self.notif.send(self.customer, NotificationTemplate.WELCOME))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(results) == 10

    def test_T064_no_audit_still_works(self):
        notif = NotificationEngine(audit=None)
        assert notif.send(self.customer, NotificationTemplate.WELCOME) is not None

    def test_T065_download_guide_contains_url(self):
        r = self.notif.send(self.customer, NotificationTemplate.DOWNLOAD_GUIDE)
        assert "docs.bot12.io" in r.body

    def test_T066_heartbeat_fail_contains_minutes(self):
        r = self.notif.send(
            self.customer,
            NotificationTemplate.HEARTBEAT_FAIL,
            params={"device_id": "D1", "minutes": 5},
        )
        assert "5" in r.body

    def test_T067_notification_id_unique(self):
        r1 = self.notif.send(self.customer, NotificationTemplate.WELCOME)
        r2 = self.notif.send(self.customer, NotificationTemplate.WELCOME)
        assert r1.notification_id != r2.notification_id

    def test_T068_sent_at_populated(self):
        assert self.notif.send(self.customer, NotificationTemplate.WELCOME).sent_at > 0

    def test_T069_customer_id_in_record(self):
        assert (
            self.notif.send(self.customer, NotificationTemplate.WELCOME).customer_id
            == self.customer.customer_id
        )

    def test_T070_tenant_id_in_record(self):
        assert (
            self.notif.send(self.customer, NotificationTemplate.WELCOME).tenant_id
            == self.customer.tenant_id
        )

    def test_T071_reactivation_offer_template(self):
        r = self.notif.send(
            self.customer,
            NotificationTemplate.REACTIVATION_OFFER,
            params={"discount": 20, "valid_until": "2027-01-01"},
        )
        assert "20%" in r.body

    def test_T072_cancellation_confirm_template(self):
        r = self.notif.send(
            self.customer,
            NotificationTemplate.CANCELLATION_CONFIRM,
            params={"plan": "pro", "date": "2027-01-01"},
        )
        assert "pro" in r.body


class TestOnboardingEngine:
    def setup_method(self):
        sys_ = make_sys()
        self.audit = sys_["audit"]
        self.store = sys_["store"]
        self.notif = sys_["notif"]
        self.onboard = sys_["onboard"]
        self.customer = make_customer(status=CustomerStatus.ONBOARDING)

    def test_T073_start_sets_onboarding_status(self):
        self.store.upsert(self.customer)
        self.onboard.start(self.customer)
        assert self.customer.status == CustomerStatus.ONBOARDING

    def test_T074_start_sends_welcome(self):
        self.store.upsert(self.customer)
        self.onboard.start(self.customer)
        assert len(self.notif.list_sent(template=NotificationTemplate.WELCOME.value)) >= 1

    def test_T075_start_sends_download_guide(self):
        self.store.upsert(self.customer)
        self.onboard.start(self.customer)
        assert len(self.notif.list_sent(template=NotificationTemplate.DOWNLOAD_GUIDE.value)) >= 1

    def test_T076_start_records_audit(self):
        self.store.upsert(self.customer)
        self.onboard.start(self.customer)
        assert len(self.audit.query(event=LifecycleEvent.ONBOARDING_STARTED.value)) >= 1

    def test_T077_complete_step_records(self):
        self.store.upsert(self.customer)
        self.onboard.complete_step(self.customer, OnboardingStep.ACCOUNT_VERIFIED)
        assert OnboardingStep.ACCOUNT_VERIFIED.value in self.customer.onboarding_steps_done

    def test_T078_complete_step_idempotent(self):
        self.store.upsert(self.customer)
        self.onboard.complete_step(self.customer, OnboardingStep.ACCOUNT_VERIFIED)
        self.onboard.complete_step(self.customer, OnboardingStep.ACCOUNT_VERIFIED)
        assert self.customer.onboarding_steps_done.count(OnboardingStep.ACCOUNT_VERIFIED.value) == 1

    def test_T079_all_steps_triggers_complete(self):
        self.store.upsert(self.customer)
        for step in OnboardingStep:
            self.onboard.complete_step(self.customer, step)
        assert self.customer.status == CustomerStatus.TRIAL

    def test_T080_complete_status_notification_sent(self):
        self.store.upsert(self.customer)
        for step in OnboardingStep:
            self.onboard.complete_step(self.customer, step)
        assert (
            len(self.notif.list_sent(template=NotificationTemplate.ONBOARDING_COMPLETE.value)) >= 1
        )

    def test_T081_stall_nudge_sends_notification(self):
        self.store.upsert(self.customer)
        self.onboard.send_stall_nudge(self.customer)
        assert len(self.notif.list_sent(template=NotificationTemplate.ONBOARDING_STEP.value)) >= 1

    def test_T082_audit_chain_valid_after_onboarding(self):
        self.store.upsert(self.customer)
        self.onboard.start(self.customer)
        for step in OnboardingStep:
            self.onboard.complete_step(self.customer, step)
        assert self.audit.verify_chain() is True

    def test_T083_step_audit_recorded(self):
        self.store.upsert(self.customer)
        self.onboard.complete_step(self.customer, OnboardingStep.EA_DOWNLOADED)
        trail = self.audit.query(event=LifecycleEvent.ONBOARDING_STEP_DONE.value)
        assert len(trail) >= 1 and trail[0].detail["step"] == OnboardingStep.EA_DOWNLOADED.value

    def test_T084_concurrent_step_completion_safe(self):
        self.store.upsert(self.customer)
        threads = [
            threading.Thread(target=self.onboard.complete_step, args=(self.customer, s))
            for s in OnboardingStep
        ]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert self.customer.is_onboarding_complete()

    def test_T085_start_audit_event(self):
        self.store.upsert(self.customer)
        self.onboard.start(self.customer)
        assert len(self.audit.query(event=LifecycleEvent.ONBOARDING_STARTED.value)) >= 1

    def test_T086_partial_steps_not_complete(self):
        self.store.upsert(self.customer)
        self.onboard.complete_step(self.customer, OnboardingStep.ACCOUNT_VERIFIED)
        assert not self.customer.is_onboarding_complete()


class TestDeviceHeartbeatManager:
    def setup_method(self):
        sys_ = make_sys(heartbeat_timeout_s=10.0)
        self.audit = sys_["audit"]
        self.store = sys_["store"]
        self.notif = sys_["notif"]
        self.heartbeat = sys_["heartbeat"]
        self.customer = make_customer()
        self.store.upsert(self.customer)

    def test_T087_register_device_success(self):
        assert self.heartbeat.register_device(self.customer, "D1") is True
        assert self.customer.device_count == 1

    def test_T088_register_device_notification(self):
        self.heartbeat.register_device(self.customer, "D1")
        assert len(self.notif.list_sent(template=NotificationTemplate.DEVICE_REGISTERED.value)) >= 1

    def test_T089_register_device_limit_reached(self):
        self.customer.device_count = self.customer.max_devices
        assert self.heartbeat.register_device(self.customer, "EXTRA") is False

    def test_T090_device_limit_notification_sent(self):
        self.customer.device_count = self.customer.max_devices
        self.heartbeat.register_device(self.customer, "EXTRA")
        assert len(self.notif.list_sent(template=NotificationTemplate.DEVICE_LIMIT.value)) >= 1

    def test_T091_send_download_guide(self):
        self.heartbeat.send_download_guide(self.customer)
        assert len(self.notif.list_sent(template=NotificationTemplate.DOWNLOAD_GUIDE.value)) >= 1

    def test_T092_flag_heartbeat_fail_increments(self):
        self.heartbeat.flag_heartbeat_fail(self.customer, "D1")
        assert self.customer.heartbeat_fail_count == 1

    def test_T093_heartbeat_fail_notification(self):
        self.heartbeat.flag_heartbeat_fail(self.customer, "D1")
        assert len(self.notif.list_sent(template=NotificationTemplate.HEARTBEAT_FAIL.value)) >= 1

    def test_T094_record_heartbeat_clears_fail(self):
        self.customer.heartbeat_fail_count = 3
        self.customer.last_heartbeat = time.time() - 400
        self.heartbeat.record_heartbeat(self.customer)
        assert self.customer.heartbeat_fail_count == 0

    def test_T095_heartbeat_recovered_notification(self):
        self.customer.heartbeat_fail_count = 2
        self.customer.last_heartbeat = time.time() - 400
        self.heartbeat.record_heartbeat(self.customer)
        assert (
            len(self.notif.list_sent(template=NotificationTemplate.HEARTBEAT_RECOVERED.value)) >= 1
        )

    def test_T096_device_audit_recorded(self):
        self.heartbeat.register_device(self.customer, "D1")
        assert len(self.audit.query(event=LifecycleEvent.DEVICE_REGISTERED.value)) >= 1

    def test_T097_heartbeat_fail_audit(self):
        self.heartbeat.flag_heartbeat_fail(self.customer, "D1")
        trail = self.audit.query(event=LifecycleEvent.HEARTBEAT_FAIL.value)
        assert len(trail) >= 1 and trail[0].detail["device_id"] == "D1"

    def test_T098_multiple_fail_increments(self):
        self.heartbeat.flag_heartbeat_fail(self.customer, "D1")
        self.heartbeat.flag_heartbeat_fail(self.customer, "D1")
        assert self.customer.heartbeat_fail_count == 2

    def test_T099_audit_chain_valid(self):
        self.heartbeat.register_device(self.customer, "D1")
        self.heartbeat.flag_heartbeat_fail(self.customer, "D1")
        self.heartbeat.record_heartbeat(self.customer)
        assert self.audit.verify_chain() is True

    def test_T100_download_guide_audit(self):
        self.heartbeat.send_download_guide(self.customer)
        assert len(self.audit.query(event=LifecycleEvent.DOWNLOAD_GUIDE_SENT.value)) >= 1


class TestSubscriptionLifecycle:
    def setup_method(self):
        sys_ = make_sys()
        self.audit = sys_["audit"]
        self.store = sys_["store"]
        self.notif = sys_["notif"]
        self.sub = sys_["sub"]
        self.customer = make_customer(expires_in_days=5)
        self.store.upsert(self.customer)

    def test_T101_send_renewal_reminder(self):
        self.sub.send_renewal_reminder(self.customer)
        assert len(self.notif.list_sent(template=NotificationTemplate.RENEWAL_REMINDER.value)) >= 1

    def test_T102_send_expiry_warning_sets_status(self):
        self.sub.send_expiry_warning(self.customer)
        assert self.customer.status == CustomerStatus.EXPIRING

    def test_T103_expiry_warning_notification_sent(self):
        self.sub.send_expiry_warning(self.customer)
        assert len(self.notif.list_sent(template=NotificationTemplate.EXPIRY_WARNING.value)) >= 1

    def test_T104_trial_warning_uses_trial_template(self):
        self.customer.plan = "trial"
        self.sub.send_expiry_warning(self.customer)
        assert len(self.notif.list_sent(template=NotificationTemplate.TRIAL_WARNING.value)) >= 1

    def test_T105_expire_subscription_sets_status(self):
        self.sub.expire_subscription(self.customer)
        assert self.customer.status == CustomerStatus.EXPIRED

    def test_T106_expire_sends_notification(self):
        self.sub.expire_subscription(self.customer)
        assert (
            len(self.notif.list_sent(template=NotificationTemplate.SUBSCRIPTION_EXPIRED.value)) >= 1
        )

    def test_T107_renew_sets_active(self):
        self.customer.status = CustomerStatus.EXPIRED
        new_exp = time.time() + 30 * 86400
        self.sub.renew_subscription(self.customer, new_exp)
        assert self.customer.status == CustomerStatus.ACTIVE
        assert self.customer.expires_at == new_exp

    def test_T108_cancel_requires_reason(self):
        with pytest.raises(MissingReasonError):
            self.sub.cancel_subscription(self.customer, reason="")

    def test_T109_cancel_sets_cancelled(self):
        self.sub.cancel_subscription(self.customer, reason="too expensive")
        assert self.customer.status == CustomerStatus.CANCELLED

    def test_T110_cancel_notification_sent(self):
        self.sub.cancel_subscription(self.customer, reason="moving to competitor")
        assert (
            len(self.notif.list_sent(template=NotificationTemplate.CANCELLATION_CONFIRM.value)) >= 1
        )

    def test_T111_cancel_audit_recorded(self):
        self.sub.cancel_subscription(self.customer, reason="user request")
        trail = self.audit.query(event=LifecycleEvent.SUBSCRIPTION_CANCELLED.value)
        assert len(trail) >= 1 and trail[0].reason == "user request"

    def test_T112_renewal_audit_recorded(self):
        self.sub.renew_subscription(self.customer, time.time() + 86400)
        assert len(self.audit.query(event=LifecycleEvent.SUBSCRIPTION_RENEWED.value)) >= 1

    def test_T113_expiry_audit_recorded(self):
        self.sub.expire_subscription(self.customer)
        assert len(self.audit.query(event=LifecycleEvent.SUBSCRIPTION_EXPIRED.value)) >= 1

    def test_T114_audit_chain_valid_after_full_cycle(self):
        self.sub.send_renewal_reminder(self.customer)
        self.sub.send_expiry_warning(self.customer)
        self.sub.expire_subscription(self.customer)
        self.sub.renew_subscription(self.customer, time.time() + 30 * 86400)
        assert self.audit.verify_chain() is True

    def test_T115_cancel_whitespace_reason_rejected(self):
        with pytest.raises(MissingReasonError):
            self.sub.cancel_subscription(self.customer, reason="   ")


class TestReactivationEngine:
    def setup_method(self):
        sys_ = make_sys()
        self.audit = sys_["audit"]
        self.store = sys_["store"]
        self.notif = sys_["notif"]
        self.reactivate = sys_["reactivate"]
        self.customer = make_customer(status=CustomerStatus.EXPIRED)
        self.store.upsert(self.customer)

    def test_T116_create_offer_returns_offer(self):
        assert isinstance(self.reactivate.create_offer(self.customer), ReactivationOffer)

    def test_T117_offer_discount(self):
        assert self.reactivate.create_offer(self.customer, discount_pct=30).discount_pct == 30

    def test_T118_offer_notification_sent(self):
        self.reactivate.create_offer(self.customer)
        assert (
            len(self.notif.list_sent(template=NotificationTemplate.REACTIVATION_OFFER.value)) >= 1
        )

    def test_T119_accept_offer_reactivates(self):
        offer = self.reactivate.create_offer(self.customer)
        result = self.reactivate.accept_offer(offer.offer_id, time.time() + 30 * 86400)
        assert result is not None and result.accepted is True
        assert self.customer.status == CustomerStatus.ACTIVE

    def test_T120_accept_expired_offer_returns_none(self):
        offer = self.reactivate.create_offer(self.customer, valid_days=-1)
        assert self.reactivate.accept_offer(offer.offer_id, time.time() + 86400) is None

    def test_T121_decline_requires_reason(self):
        offer = self.reactivate.create_offer(self.customer)
        with pytest.raises(MissingReasonError):
            self.reactivate.decline_offer(offer.offer_id, reason="")

    def test_T122_decline_sets_churned(self):
        offer = self.reactivate.create_offer(self.customer)
        self.reactivate.decline_offer(offer.offer_id, reason="found alternative")
        assert self.customer.status == CustomerStatus.CHURNED

    def test_T123_decline_audit_recorded(self):
        offer = self.reactivate.create_offer(self.customer)
        self.reactivate.decline_offer(offer.offer_id, reason="too expensive")
        assert len(self.audit.query(event=LifecycleEvent.REACTIVATION_DECLINED.value)) >= 1

    def test_T124_accept_audit_recorded(self):
        offer = self.reactivate.create_offer(self.customer)
        self.reactivate.accept_offer(offer.offer_id, time.time() + 86400)
        assert len(self.audit.query(event=LifecycleEvent.REACTIVATION_ACCEPTED.value)) >= 1

    def test_T125_list_offers_by_customer(self):
        c2 = make_customer("c2", status=CustomerStatus.EXPIRED)
        self.store.upsert(c2)
        self.reactivate.create_offer(self.customer)
        self.reactivate.create_offer(c2)
        result = self.reactivate.list_offers(customer_id=self.customer.customer_id)
        assert all(o.customer_id == self.customer.customer_id for o in result)

    def test_T126_accept_missing_offer_returns_none(self):
        assert self.reactivate.accept_offer("nonexistent", time.time() + 86400) is None

    def test_T127_offer_audit_created(self):
        self.reactivate.create_offer(self.customer)
        assert len(self.audit.query(event=LifecycleEvent.REACTIVATION_OFFERED.value)) >= 1

    def test_T128_audit_chain_valid(self):
        offer = self.reactivate.create_offer(self.customer)
        self.reactivate.accept_offer(offer.offer_id, time.time() + 86400)
        assert self.audit.verify_chain() is True


class TestDunningManager:
    def setup_method(self):
        sys_ = make_sys()
        self.audit = sys_["audit"]
        self.store = sys_["store"]
        self.notif = sys_["notif"]
        self.dunning = sys_["dunning"]
        self.customer = make_customer()
        self.store.upsert(self.customer)

    def test_T129_payment_failed_sets_dunning(self):
        self.dunning.payment_failed(self.customer)
        assert self.customer.status == CustomerStatus.DUNNING

    def test_T130_payment_failed_notification(self):
        self.dunning.payment_failed(self.customer)
        assert len(self.notif.list_sent(template=NotificationTemplate.PAYMENT_FAILED.value)) >= 1

    def test_T131_payment_recovered_sets_active(self):
        self.dunning.payment_failed(self.customer)
        self.dunning.payment_recovered(self.customer)
        assert self.customer.status == CustomerStatus.ACTIVE

    def test_T132_payment_recovered_notification(self):
        self.dunning.payment_recovered(self.customer)
        assert len(self.notif.list_sent(template=NotificationTemplate.PAYMENT_RECOVERED.value)) >= 1

    def test_T133_start_dunning_notification(self):
        self.dunning.start_dunning(self.customer, days_remaining=5)
        assert len(self.notif.list_sent(template=NotificationTemplate.DUNNING_STARTED.value)) >= 1

    def test_T134_payment_fail_audit(self):
        self.dunning.payment_failed(self.customer)
        assert len(self.audit.query(event=LifecycleEvent.PAYMENT_FAILED.value)) >= 1

    def test_T135_payment_recovered_audit(self):
        self.dunning.payment_recovered(self.customer)
        assert len(self.audit.query(event=LifecycleEvent.PAYMENT_RECOVERED.value)) >= 1

    def test_T136_dunning_started_audit(self):
        self.dunning.start_dunning(self.customer, days_remaining=7)
        trail = self.audit.query(event=LifecycleEvent.DUNNING_STARTED.value)
        assert len(trail) >= 1 and trail[0].detail["days_remaining"] == 7

    def test_T137_audit_chain_valid(self):
        self.dunning.payment_failed(self.customer)
        self.dunning.payment_recovered(self.customer)
        assert self.audit.verify_chain() is True


class TestSupportTicketDeflector:
    def setup_method(self):
        sys_ = make_sys()
        self.audit = sys_["audit"]
        self.deflector = sys_["deflector"]
        self.customer = make_customer()

    def test_T138_auto_deflect_known_category(self):
        t = self.deflector.auto_deflect(self.customer, TicketCategory.DEVICE_SETUP, "S", "B")
        assert t.self_served is True and t.status == "self_served"

    def test_T139_auto_deflect_has_resolution(self):
        t = self.deflector.auto_deflect(self.customer, TicketCategory.HEARTBEAT_FAIL, "S", "B")
        assert len(t.resolution) > 0

    def test_T140_auto_deflect_unknown_opens_ticket(self):
        t = self.deflector.auto_deflect(self.customer, TicketCategory.OTHER, "S", "B")
        assert t.status == "open" and t.self_served is False

    def test_T141_close_ticket_requires_reason(self):
        t = self.deflector.auto_deflect(self.customer, TicketCategory.OTHER, "S", "B")
        with pytest.raises(MissingReasonError):
            self.deflector.close_ticket(t.ticket_id, "fixed", reason="")

    def test_T142_close_ticket_sets_closed(self):
        t = self.deflector.auto_deflect(self.customer, TicketCategory.OTHER, "S", "B")
        result = self.deflector.close_ticket(t.ticket_id, "fixed", reason="resolved")
        assert result.status == "closed"

    def test_T143_deflection_rate_all_self_served(self):
        for cat in [
            TicketCategory.DEVICE_SETUP,
            TicketCategory.HEARTBEAT_FAIL,
            TicketCategory.LICENSE_ISSUE,
        ]:
            self.deflector.auto_deflect(self.customer, cat, "S", "B")
        assert self.deflector.deflection_rate() == 1.0

    def test_T144_deflection_rate_mixed(self):
        self.deflector.auto_deflect(self.customer, TicketCategory.DEVICE_SETUP, "S", "B")
        self.deflector.auto_deflect(self.customer, TicketCategory.OTHER, "S", "B")
        assert 0 < self.deflector.deflection_rate() < 1

    def test_T145_deflection_rate_empty(self):
        assert self.deflector.deflection_rate() == 0.0

    def test_T146_list_tickets_by_status(self):
        self.deflector.auto_deflect(self.customer, TicketCategory.OTHER, "S", "B")
        assert len(self.deflector.list_tickets(status="open")) >= 1

    def test_T147_self_served_audit(self):
        self.deflector.auto_deflect(self.customer, TicketCategory.DEVICE_SETUP, "S", "B")
        assert len(self.audit.query(event=LifecycleEvent.SELF_SERVICE_RESOLVED.value)) >= 1

    def test_T148_close_audit_recorded(self):
        t = self.deflector.auto_deflect(self.customer, TicketCategory.OTHER, "S", "B")
        self.deflector.close_ticket(t.ticket_id, "resolved", reason="agent resolved")
        assert len(self.audit.query(event=LifecycleEvent.SUPPORT_TICKET_CLOSED.value)) >= 1

    def test_T149_close_missing_ticket_returns_none(self):
        assert self.deflector.close_ticket("nonexistent", "res", reason="r") is None

    def test_T150_resolution_contains_doc_url(self):
        t = self.deflector.auto_deflect(self.customer, TicketCategory.DOWNLOAD_HELP, "S", "B")
        assert "docs.bot12.io" in t.resolution

    def test_T151_concurrent_deflect_safe(self):
        results = []

        def worker():
            results.append(
                self.deflector.auto_deflect(self.customer, TicketCategory.DEVICE_SETUP, "S", "B")
            )

        threads = [threading.Thread(target=worker) for _ in range(10)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(results) == 10

    def test_T152_audit_chain_valid_after_deflect(self):
        self.deflector.auto_deflect(self.customer, TicketCategory.DEVICE_SETUP, "S", "B")
        assert self.audit.verify_chain() is True


class TestLifecycleScheduler:
    def setup_method(self):
        self.sys_ = make_sys(renewal_remind_days=14.0, expiry_warn_days=3.0)
        self.scheduler = self.sys_["scheduler"]
        self.store = self.sys_["store"]
        self.audit = self.sys_["audit"]

    def test_T153_renewal_reminder_sent(self):
        self.store.upsert(make_customer("c1", status=CustomerStatus.ACTIVE, expires_in_days=7))
        assert self.scheduler.run_daily().get("renewal_reminders", 0) >= 1

    def test_T154_expiry_warning_sent(self):
        self.store.upsert(make_customer("c1", status=CustomerStatus.ACTIVE, expires_in_days=2))
        assert self.scheduler.run_daily().get("expiry_warnings", 0) >= 1

    def test_T155_expired_subscription_processed(self):
        c = make_customer("c1", status=CustomerStatus.ACTIVE, expires_in_days=-1)
        self.store.upsert(c)
        assert self.scheduler.run_daily().get("expired", 0) >= 1
        assert c.status == CustomerStatus.EXPIRED

    def test_T156_heartbeat_fail_detected(self):
        sys2 = make_sys(heartbeat_timeout_s=300.0)
        c2 = make_customer("c2")
        c2.last_heartbeat = time.time() - 400
        sys2["store"].upsert(c2)
        assert sys2["scheduler"].run_daily().get("heartbeat_fails", 0) >= 1

    def test_T157_reactivation_offer_for_expired(self):
        self.store.upsert(make_customer("c1", status=CustomerStatus.EXPIRED, expires_in_days=-5))
        assert self.scheduler.run_daily().get("reactivation_offers", 0) >= 1

    def test_T158_no_duplicate_reactivation_offer(self):
        self.store.upsert(make_customer("c1", status=CustomerStatus.EXPIRED, expires_in_days=-5))
        self.scheduler.run_daily()
        assert self.scheduler.run_daily().get("reactivation_offers", 0) == 0

    def test_T159_no_renewal_reminder_for_expired(self):
        self.store.upsert(make_customer("c1", status=CustomerStatus.ACTIVE, expires_in_days=-1))
        assert self.scheduler.run_daily().get("renewal_reminders", 0) == 0

    def test_T160_audit_chain_valid_after_scheduler(self):
        self.store.upsert(make_customer("c1", status=CustomerStatus.ACTIVE, expires_in_days=7))
        self.store.upsert(make_customer("c2", status=CustomerStatus.EXPIRED, expires_in_days=-1))
        self.scheduler.run_daily()
        assert self.audit.verify_chain() is True


class TestLifecycleAdmin:
    def setup_method(self):
        self.sys_ = make_sys()
        self.admin = self.sys_["admin"]
        self.store = self.sys_["store"]
        self.audit = self.sys_["audit"]
        self.deflector = self.sys_["deflector"]

    def _populate(self, n_active=3, n_expired=2):
        for i in range(n_active):
            c = make_customer(f"a{i}", status=CustomerStatus.ACTIVE)
            c.onboarding_steps_done = [s.value for s in OnboardingStep]
            self.store.upsert(c)
        for i in range(n_expired):
            self.store.upsert(make_customer(f"e{i}", status=CustomerStatus.EXPIRED))

    def test_T161_dashboard_returns_object(self):
        self._populate()
        assert isinstance(self.admin.dashboard(), LifecycleDashboard)

    def test_T162_total_customers_correct(self):
        self._populate(n_active=3, n_expired=2)
        assert self.admin.dashboard().total_customers == 5

    def test_T163_status_breakdown_correct(self):
        self._populate(n_active=3, n_expired=2)
        d = self.admin.dashboard()
        assert d.status_breakdown.get("active", 0) == 3
        assert d.status_breakdown.get("expired", 0) == 2

    def test_T164_onboarding_complete_count(self):
        self._populate(n_active=3, n_expired=0)
        assert self.admin.dashboard().onboarding_complete == 3

    def test_T165_expiring_7d_count(self):
        self.store.upsert(make_customer("exp1", status=CustomerStatus.ACTIVE, expires_in_days=3))
        assert self.admin.dashboard().expiring_7d >= 1

    def test_T166_open_tickets_count(self):
        self.deflector.auto_deflect(make_customer("c1"), TicketCategory.OTHER, "S", "B")
        assert self.admin.dashboard().open_tickets >= 1

    def test_T167_audit_chain_ok_true(self):
        self._populate()
        assert self.admin.dashboard().audit_chain_ok is True

    def test_T168_notification_count(self):
        self.sys_["notif"].send(make_customer("c1"), NotificationTemplate.WELCOME)
        assert self.admin.dashboard().notification_count >= 1

    def test_T169_to_dict_serializable(self):
        import json

        self._populate()
        assert len(json.dumps(self.admin.dashboard().to_dict())) > 0

    def test_T170_dashboard_has_generated_at(self):
        assert self.admin.dashboard().generated_at > 0

    def test_T171_heartbeat_overdue_count(self):
        c = make_customer("c1")
        c.last_heartbeat = time.time() - 400
        self.store.upsert(c)
        assert self.admin.dashboard().heartbeat_overdue >= 1

    def test_T172_self_service_rate_high(self):
        c = make_customer("c1")
        for cat in [
            TicketCategory.DEVICE_SETUP,
            TicketCategory.HEARTBEAT_FAIL,
            TicketCategory.LICENSE_ISSUE,
        ]:
            self.deflector.auto_deflect(c, cat, "S", "B")
        assert self.admin.dashboard().self_service_rate >= 0.8


class TestSQLMigration:
    def setup_method(self):
        import pathlib

        p = pathlib.Path(__file__).parents[2] / "supabase" / "migrations"
        sql_files = sorted(p.glob("*phase32*")) if p.exists() else []
        if not sql_files:
            pytest.skip("SQL migration file not found")
        self.sql = sql_files[-1].read_text()

    def test_T173_create_customer_lifecycle_table(self):
        assert "customer_lifecycle_events" in self.sql

    def test_T174_create_notification_log_table(self):
        assert "notification_log" in self.sql

    def test_T175_create_support_tickets_table(self):
        assert "support_tickets" in self.sql

    def test_T176_create_reactivation_offers_table(self):
        assert "reactivation_offers" in self.sql

    def test_T177_create_dunning_log_table(self):
        assert "dunning_log" in self.sql

    def test_T178_create_lifecycle_audit_log_table(self):
        assert "lifecycle_audit_log" in self.sql

    def test_T179_rls_enabled(self):
        assert "ROW LEVEL SECURITY" in self.sql or "ENABLE ROW LEVEL SECURITY" in self.sql

    def test_T180_tenant_id_column(self):
        assert "tenant_id" in self.sql

    def test_T181_chain_hash_column(self):
        assert "chain_hash" in self.sql

    def test_T182_immutable_trigger(self):
        assert "BEFORE UPDATE OR DELETE" in self.sql or "RAISE EXCEPTION" in self.sql

    def test_T183_indexes_defined(self):
        assert "CREATE INDEX" in self.sql

    def test_T184_cleanup_function(self):
        assert "cleanup" in self.sql.lower() or "DELETE FROM" in self.sql

    def test_T185_views_defined(self):
        assert "CREATE OR REPLACE VIEW" in self.sql or "CREATE VIEW" in self.sql

    def test_T186_begin_commit(self):
        assert "BEGIN" in self.sql and "COMMIT" in self.sql


class TestIntegrationFlows:
    def setup_method(self):
        self.sys_ = make_sys()

    def test_T187_full_onboarding_flow(self):
        sys_ = self.sys_
        c = make_customer(status=CustomerStatus.ONBOARDING)
        sys_["store"].upsert(c)
        sys_["onboard"].start(c)
        for step in OnboardingStep:
            sys_["onboard"].complete_step(c, step)
        assert c.status == CustomerStatus.TRIAL
        assert c.is_onboarding_complete()
        assert sys_["audit"].verify_chain()

    def test_T188_full_subscription_lifecycle(self):
        sys_ = self.sys_
        c = make_customer(status=CustomerStatus.ACTIVE, expires_in_days=10)
        sys_["store"].upsert(c)
        sys_["sub"].send_renewal_reminder(c)
        sys_["sub"].send_expiry_warning(c)
        sys_["sub"].expire_subscription(c)
        assert c.status == CustomerStatus.EXPIRED
        sys_["sub"].renew_subscription(c, time.time() + 30 * 86400)
        assert c.status == CustomerStatus.ACTIVE

    def test_T189_heartbeat_fail_and_recovery_flow(self):
        sys_ = self.sys_
        c = make_customer()
        sys_["store"].upsert(c)
        sys_["heartbeat"].register_device(c, "D1")
        sys_["heartbeat"].flag_heartbeat_fail(c, "D1")
        sys_["heartbeat"].flag_heartbeat_fail(c, "D1")
        sys_["heartbeat"].record_heartbeat(c)
        assert c.heartbeat_fail_count == 0
        assert sys_["audit"].verify_chain()

    def test_T190_reactivation_full_flow(self):
        sys_ = self.sys_
        c = make_customer(status=CustomerStatus.EXPIRED)
        sys_["store"].upsert(c)
        offer = sys_["reactivate"].create_offer(c, discount_pct=25)
        result = sys_["reactivate"].accept_offer(offer.offer_id, time.time() + 30 * 86400)
        assert result.accepted is True and c.status == CustomerStatus.ACTIVE

    def test_T191_churn_flow(self):
        sys_ = self.sys_
        c = make_customer(status=CustomerStatus.EXPIRED)
        sys_["store"].upsert(c)
        offer = sys_["reactivate"].create_offer(c)
        sys_["reactivate"].decline_offer(offer.offer_id, reason="no longer needed")
        assert c.status == CustomerStatus.CHURNED

    def test_T192_dunning_recovery_flow(self):
        sys_ = self.sys_
        c = make_customer()
        sys_["store"].upsert(c)
        sys_["dunning"].payment_failed(c)
        assert c.status == CustomerStatus.DUNNING
        sys_["dunning"].payment_recovered(c)
        assert c.status == CustomerStatus.ACTIVE

    def test_T193_cancellation_then_reactivation(self):
        sys_ = self.sys_
        c = make_customer(status=CustomerStatus.ACTIVE, expires_in_days=10)
        sys_["store"].upsert(c)
        sys_["sub"].cancel_subscription(c, reason="switching product")
        assert c.status == CustomerStatus.CANCELLED
        sys_["sub"].renew_subscription(c, time.time() + 30 * 86400)
        assert c.status == CustomerStatus.ACTIVE

    def test_T194_support_deflection_flow(self):
        sys_ = self.sys_
        c = make_customer()
        t = sys_["deflector"].auto_deflect(c, TicketCategory.DEVICE_SETUP, "S", "B")
        assert t.self_served and sys_["deflector"].deflection_rate() == 1.0

    def test_T195_scheduler_full_run(self):
        sys_ = self.sys_
        c1 = make_customer("c1", status=CustomerStatus.ACTIVE, expires_in_days=7)
        c2 = make_customer("c2", status=CustomerStatus.ACTIVE, expires_in_days=-1)
        c3 = make_customer("c3", status=CustomerStatus.EXPIRED, expires_in_days=-5)
        c4 = make_customer("c4")
        c4.last_heartbeat = time.time() - 400
        for c in [c1, c2, c3, c4]:
            sys_["store"].upsert(c)
        counts = sys_["scheduler"].run_daily()
        assert counts.get("expired", 0) >= 1 and counts.get("reactivation_offers", 0) >= 1
        assert sys_["audit"].verify_chain()

    def test_T196_200_event_audit_chain(self):
        sys_ = self.sys_
        for i in range(200):
            sys_["audit"].record(LifecycleEvent.ACCOUNT_CREATED.value, f"c{i}", "t1", "system")
        assert sys_["audit"].verify_chain()
        assert len(sys_["audit"].detect_tampered()) == 0

    def test_T197_concurrent_full_lifecycle(self):
        sys_ = self.sys_
        errors = []

        def worker(i):
            try:
                c = make_customer(f"cc{i}")
                sys_["store"].upsert(c)
                sys_["onboard"].start(c)
                sys_["heartbeat"].register_device(c, f"D{i}")
                sys_["sub"].send_renewal_reminder(c)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(errors) == 0 and sys_["audit"].verify_chain()


class TestEdgeCasesAndAcceptance:
    def setup_method(self):
        self.sys_ = make_sys()

    def test_T198_days_until_expiry_none_if_no_expiry(self):
        c = CustomerRecord(customer_id="x", tenant_id="t", email="x@e.com")
        assert c.days_until_expiry() is None

    def test_T199_is_expired_false_if_no_expiry(self):
        assert not CustomerRecord(customer_id="x", tenant_id="t", email="x@e.com").is_expired()

    def test_T200_lifecycle_event_str_values(self):
        for e in LifecycleEvent:
            assert isinstance(e.value, str)

    def test_T201_customer_status_str_values(self):
        for s in CustomerStatus:
            assert isinstance(s.value, str)

    def test_T202_notification_template_has_17_values(self):
        assert len(NotificationTemplate) >= 17

    def test_T203_download_guide_contains_platform_info(self):
        assert (
            "MT4" in TEMPLATES[NotificationTemplate.DOWNLOAD_GUIDE][1]
            or "MT5" in TEMPLATES[NotificationTemplate.DOWNLOAD_GUIDE][1]
        )

    def test_T204_welcome_template_has_support_email(self):
        assert "support@bot12.io" in TEMPLATES[NotificationTemplate.WELCOME][1]

    def test_T205_heartbeat_fail_template_has_url(self):
        assert "docs.bot12.io" in TEMPLATES[NotificationTemplate.HEARTBEAT_FAIL][1]

    def test_T206_all_self_service_answers_nonempty(self):
        for k, v in SELF_SERVICE_ANSWERS.items():
            assert len(v) > 50

    def test_T207_reactivation_offer_valid_until_future(self):
        sys_ = self.sys_
        c = make_customer(status=CustomerStatus.EXPIRED)
        sys_["store"].upsert(c)
        assert sys_["reactivate"].create_offer(c, valid_days=7).valid_until > time.time()

    def test_T208_build_system_returns_all_keys(self):
        keys = {
            "audit",
            "store",
            "notif",
            "onboard",
            "sub",
            "heartbeat",
            "reactivate",
            "dunning",
            "deflector",
            "scheduler",
            "admin",
        }
        assert keys.issubset(set(self.sys_.keys()))

    def test_T209_audit_chain_genesis_correct(self):
        import hmac as hm

        secret = "lifecycle-audit-secret-v32".encode()
        genesis = hm.new(secret, LifecycleAuditChain.GENESIS_MSG.encode(), "sha256").hexdigest()
        assert len(genesis) == 64

    def test_T210_customer_status_onboarding_default(self):
        assert (
            CustomerRecord(customer_id="x", tenant_id="t", email="x@e.com").status
            == CustomerStatus.ONBOARDING
        )

    def test_T211_notification_record_has_id(self):
        sys_ = self.sys_
        r = sys_["notif"].send(make_customer(), NotificationTemplate.WELCOME)
        assert len(r.notification_id) == 36

    def test_T212_reactivation_offer_has_uuid(self):
        sys_ = self.sys_
        c = make_customer(status=CustomerStatus.EXPIRED)
        sys_["store"].upsert(c)
        assert len(sys_["reactivate"].create_offer(c).offer_id) == 36

    def test_T213_support_ticket_has_uuid(self):
        sys_ = self.sys_
        t = sys_["deflector"].auto_deflect(make_customer(), TicketCategory.OTHER, "S", "B")
        assert len(t.ticket_id) == 36

    def test_T214_cancellation_whitespace_reason_fails(self):
        sys_ = self.sys_
        c = make_customer()
        sys_["store"].upsert(c)
        with pytest.raises(MissingReasonError):
            sys_["sub"].cancel_subscription(c, reason="   ")

    def test_T215_decline_reactivation_whitespace_fails(self):
        sys_ = self.sys_
        c = make_customer(status=CustomerStatus.EXPIRED)
        sys_["store"].upsert(c)
        offer = sys_["reactivate"].create_offer(c)
        with pytest.raises(MissingReasonError):
            sys_["reactivate"].decline_offer(offer.offer_id, reason="  ")

    def test_T216_acceptance_customer_journey_smooth(self):
        """T216 -- Acceptance: customer journey is smooth end-to-end."""
        sys_ = build_lifecycle_system()
        audit = sys_["audit"]
        store = sys_["store"]
        onboard = sys_["onboard"]
        sub = sys_["sub"]
        hb = sys_["heartbeat"]
        react = sys_["reactivate"]
        deflector = sys_["deflector"]
        admin = sys_["admin"]
        c = make_customer("journey-1", status=CustomerStatus.ONBOARDING)
        store.upsert(c)
        onboard.start(c)
        for step in OnboardingStep:
            onboard.complete_step(c, step)
        assert c.status == CustomerStatus.TRIAL and c.is_onboarding_complete()
        assert hb.register_device(c, "MT5-PC1") is True
        hb.flag_heartbeat_fail(c, "MT5-PC1")
        assert c.heartbeat_fail_count == 1
        hb.record_heartbeat(c)
        assert c.heartbeat_fail_count == 0
        t = deflector.auto_deflect(c, TicketCategory.HEARTBEAT_FAIL, "EA offline", "Not sending")
        assert t.self_served is True
        c.status = CustomerStatus.ACTIVE
        c.expires_at = time.time() + 2 * 86400
        store.upsert(c)
        sub.send_expiry_warning(c)
        assert c.status == CustomerStatus.EXPIRING
        sub.renew_subscription(c, time.time() + 30 * 86400)
        assert c.status == CustomerStatus.ACTIVE
        sub.cancel_subscription(c, reason="switching to manual trading")
        assert c.status == CustomerStatus.CANCELLED
        c.status = CustomerStatus.EXPIRED
        c.expires_at = time.time() - 1
        store.upsert(c)
        offer = react.create_offer(c, discount_pct=20)
        result = react.accept_offer(offer.offer_id, time.time() + 30 * 86400)
        assert result.accepted is True and c.status == CustomerStatus.ACTIVE
        d = admin.dashboard()
        assert d.total_customers >= 1 and d.self_service_rate == 1.0
        assert d.audit_chain_ok is True and d.notification_count >= 5
        assert audit.verify_chain() is True and len(audit.detect_tampered()) == 0
        assert len(audit) >= 10
