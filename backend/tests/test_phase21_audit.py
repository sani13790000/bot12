import json

from backend.core.audit_log_v21 import (
    EVENT_META,
    REQUIRES_REASON,
    AuditEvent,
    AuditRecord,
    Severity,
)


class TestAuditEventCoverage:
    def test_T001_at_least_64_events(self):
        assert len(AuditEvent) >= 64

    def test_T002_all_events_have_meta(self):
        assert all(e in EVENT_META for e in AuditEvent)

    def test_T003_all_meta_have_severity(self):
        for e, m in EVENT_META.items():
            assert isinstance(m.severity, Severity)

    def test_T004_all_meta_have_category(self):
        for e, m in EVENT_META.items():
            assert m.category

    def test_T005_critical_events_exist(self):
        crits = [e for e, m in EVENT_META.items() if m.severity == Severity.CRITICAL]
        assert len(crits) >= 5

    def test_T006_requires_reason_subset(self):
        assert REQUIRES_REASON.issubset(set(AuditEvent))

    def test_T007_event_values_unique(self):
        vals = [e.value for e in AuditEvent]
        assert len(vals) == len(set(vals))


class TestAuditRecord:
    def test_T010_basic_create(self):
        r = AuditRecord(event=AuditEvent.USER_LOGIN, actor_id="u1", target_id="t1")
        assert r.event == AuditEvent.USER_LOGIN

    def test_T011_timestamp_utc(self):
        r = AuditRecord(event=AuditEvent.USER_LOGIN, actor_id="u1")
        assert r.timestamp.endswith("Z") or "+" in r.timestamp

    def test_T012_record_id_unique(self):
        r1 = AuditRecord(event=AuditEvent.USER_LOGIN, actor_id="u1")
        r2 = AuditRecord(event=AuditEvent.USER_LOGIN, actor_id="u1")
        assert r1.record_id != r2.record_id

    def test_T016_to_dict_keys(self):
        r = AuditRecord(event=AuditEvent.USER_LOGIN, actor_id="u1")
        d = r.to_dict()
        for key in ("record_id", "event", "actor_id", "timestamp"):
            assert key in d

    def test_T017_to_json_parseable(self):
        r = AuditRecord(event=AuditEvent.USER_LOGIN, actor_id="u1")
        parsed = json.loads(r.to_json())
        assert parsed["actor_id"] == "u1"
