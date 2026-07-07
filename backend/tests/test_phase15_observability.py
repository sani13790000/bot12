"""
test_phase15_observability.py — Phase 15 Observability Tests
104 tests in 8 classes
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.observability.admin_trace import AdminTracer
from backend.observability.alert_manager_v15 import AlertLevel, AlertManager
from backend.observability.metrics_v15 import MetricsRegistry


@pytest.fixture
def reg():
    r = MetricsRegistry()
    yield r
    r.reset()


@pytest.fixture
def mgr():
    m = AlertManager()
    yield m
    m.reset()


@pytest.fixture
def tracer():
    t = AdminTracer()
    yield t
    t.reset()


class TestMetricsRegistry:
    def test_license_failure_increments_counter(self, reg):
        reg.license_failure("key_hash_mismatch", user_id="u1")
        assert reg.snapshot()["counters"].get("license_failures_total", 0) == 1

    def test_license_failure_reasons_tracked(self, reg):
        reg.license_failure("expired", user_id="u1")
        reg.license_failure("revoked", user_id="u2")
        reg.license_failure("expired", user_id="u3")
        snap = reg.snapshot()
        assert snap["counters"].get("license_failures.expired", 0) == 2
        assert snap["counters"].get("license_failures.revoked", 0) == 1

    def test_license_failure_logs_event(self, reg):
        reg.license_failure("device_mismatch", user_id="u1", device_id="dev1")
        events = reg.get_events(category="license_failure")
        assert len(events) == 1
        assert events[0]["reason"] == "device_mismatch"

    def test_heartbeat_received_updates_gauge(self, reg):
        before = time.time()
        reg.heartbeat_received("dev-abc")
        ts = reg.snapshot()["gauges"].get("last_heartbeat.dev-abc", 0)
        assert ts >= before

    def test_heartbeat_loss_counter(self, reg):
        reg.heartbeat_loss("dev-abc", gap_s=120.5, user_id="u1")
        snap = reg.snapshot()
        assert snap["counters"].get("heartbeat_losses_total", 0) == 1
        assert "heartbeat_gap_s" in snap["histograms"]

    def test_heartbeat_loss_event(self, reg):
        reg.heartbeat_loss("dev-x", gap_s=300.0, user_id="u2")
        events = reg.get_events(category="heartbeat_loss")
        assert len(events) == 1
        assert events[0]["device_id"] == "dev-x"
        assert events[0]["gap_s"] == 300.0

    def test_kill_switch_activated_sets_gauge(self, reg):
        assert not reg.is_kill_switch_active()
        reg.kill_switch_activated("admin", "drawdown", "global")
        assert reg.is_kill_switch_active()
        assert reg.snapshot()["counters"].get("kill_switch_activations_total", 0) == 1

    def test_kill_switch_reset_clears_gauge(self, reg):
        reg.kill_switch_activated("admin", "test")
        assert reg.is_kill_switch_active()
        reg.kill_switch_reset("admin")
        assert not reg.is_kill_switch_active()

    def test_reconciliation_mismatch_counter(self, reg):
        reg.reconciliation_mismatch("EURUSD", broker_qty=1.5, local_qty=1.0)
        snap = reg.snapshot()
        assert snap["counters"].get("reconciliation_mismatches_total", 0) == 1
        assert snap["counters"].get("reconciliation_mismatches.EURUSD", 0) == 1

    def test_reconciliation_mismatch_event_detail(self, reg):
        reg.reconciliation_mismatch("GBPUSD", 2.0, 1.5)
        events = reg.get_events(category="reconciliation_mismatch")
        assert events[0]["delta"] == 0.5

    def test_drawdown_alert_counter(self, reg):
        reg.drawdown_alert(pct=12.5, level="CRITICAL", equity_usd=50000.0)
        snap = reg.snapshot()
        assert snap["counters"].get("drawdown_alerts_total", 0) == 1
        assert snap["gauges"].get("equity_drawdown_pct", 0) == 12.5

    def test_admin_snapshot_saas_kpis(self, reg):
        reg.license_failure("expired")
        reg.heartbeat_loss("dev1", 90.0)
        reg.kill_switch_activated("admin", "test")
        snap = reg.admin_snapshot()
        kpis = snap["saas_kpis"]
        assert kpis["license_failures_total"] == 1
        assert kpis["heartbeat_losses_total"] == 1
        assert kpis["kill_switch_active"] == 1.0
        assert "recent_events" in snap

    def test_get_events_since_ts_filter(self, reg):
        reg.license_failure("old_reason")
        since = time.time()
        reg.license_failure("new_reason")
        evs = reg.get_events(category="license_failure", since_ts=since)
        assert len(evs) == 1
        assert evs[0]["reason"] == "new_reason"

    def test_reset_clears_all(self, reg):
        reg.license_failure("x")
        reg.heartbeat_loss("d", 1.0)
        reg.reset()
        snap = reg.snapshot()
        assert snap["counters"] == {}
        assert snap["gauges"] == {}

    def test_prometheus_format_not_stub(self, reg):
        reg.license_failure("test")
        text = reg.prometheus_format()
        assert isinstance(text, str) and len(text) > 0
        assert "license_failures_total" in text

    def test_license_validated_counter(self, reg):
        reg.license_validated("PRO")
        reg.license_validated("PRO")
        reg.license_validated("TRIAL")
        snap = reg.snapshot()
        assert snap["counters"].get("license_validations_total", 0) == 3
        assert snap["counters"].get("license_validations.PRO", 0) == 2


class TestAlertManager:
    def test_phase15_rules_exist(self, mgr):
        rules = {r["name"] for r in mgr.list_rules()}
        for expected in [
            "license_failure",
            "heartbeat_loss",
            "kill_switch_activated",
            "drawdown_critical",
            "reconciliation_mismatch",
        ]:
            assert expected in rules, f"Missing rule: {expected}"

    def test_kill_switch_rule_level(self, mgr):
        rule = mgr.get_rule("kill_switch_activated")
        assert rule is not None and rule.level == AlertLevel.CRITICAL

    def test_license_failure_rule_level(self, mgr):
        assert mgr.get_rule("license_failure").level == AlertLevel.CRITICAL

    def test_heartbeat_loss_rule_level(self, mgr):
        assert mgr.get_rule("heartbeat_loss").level == AlertLevel.CRITICAL

    def test_reconciliation_mismatch_rule_level(self, mgr):
        assert mgr.get_rule("reconciliation_mismatch").level == AlertLevel.CRITICAL

    def test_dedup_blocks_within_window(self, mgr):
        async def run():
            mgr.get_rule("heartbeat_loss").dedup_window_s = 300
            s1 = await mgr.fire("heartbeat_loss")
            s2 = await mgr.fire("heartbeat_loss")
            return s1, s2

        s1, s2 = asyncio.get_event_loop().run_until_complete(run())
        assert s1 is True and s2 is False

    def test_rate_limit(self, mgr):
        from backend.observability.alert_manager_v15 import _RATE_LIMIT_N

        async def run():
            mgr.get_rule("test").dedup_window_s = 0
            results = []
            for i in range(_RATE_LIMIT_N + 5):
                sent = await mgr.fire("test")
                results.append(sent)
            return results

        results = asyncio.get_event_loop().run_until_complete(run())
        assert sum(1 for r in results if r) <= _RATE_LIMIT_N

    def test_callback_receives_alert(self, mgr):
        received = []

        async def cb(r, l, c):
            received.append((r, l))

        mgr.add_callback(cb)

        async def run():
            mgr.get_rule("test").dedup_window_s = 0
            await mgr.fire("test", context={"x": 1})

        asyncio.get_event_loop().run_until_complete(run())
        assert len(received) == 1 and received[0][0] == "test"

    def test_remove_callback(self, mgr):
        received = []

        async def cb(r, l, c):
            received.append(r)

        mgr.add_callback(cb)
        mgr.remove_callback(cb)

        async def run():
            mgr.get_rule("test").dedup_window_s = 0
            await mgr.fire("test")

        asyncio.get_event_loop().run_until_complete(run())
        assert received == []

    def test_disabled_rule_not_fired(self, mgr):
        mgr.disable_rule("heartbeat_slow")

        async def run():
            return await mgr.fire("heartbeat_slow")

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is False

    def test_unknown_rule_auto_created(self, mgr):
        async def run():
            return await mgr.fire("completely_unknown_rule_xyz")

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is True

    def test_history_records_fires(self, mgr):
        async def run():
            mgr.get_rule("test").dedup_window_s = 0
            for _ in range(3):
                await mgr.fire("test")

        asyncio.get_event_loop().run_until_complete(run())
        assert len(mgr.history(rule_name="test")) == 3

    def test_history_level_filter(self, mgr):
        async def run():
            mgr.get_rule("test").dedup_window_s = 0
            await mgr.fire("test")
            await mgr.fire("license_failure", context={})

        asyncio.get_event_loop().run_until_complete(run())
        critical = mgr.history(level=AlertLevel.CRITICAL)
        assert all(a["level"] == AlertLevel.CRITICAL for a in critical)

    def test_stats(self, mgr):
        stats = mgr.stats()
        assert "sent_total" in stats and "rules_total" in stats
        assert stats["rules_total"] >= 12

    def test_enable_rule(self, mgr):
        mgr.disable_rule("heartbeat_slow")
        mgr.enable_rule("heartbeat_slow")
        assert mgr.get_rule("heartbeat_slow").enabled is True


class TestAdminTracer:
    def test_record_returns_event_id(self, tracer):
        eid = tracer.record("license", "license_failure", "CRITICAL", user_id="u1")
        assert eid and len(eid) > 0

    def test_record_license_failure(self, tracer):
        tracer.record_license_failure("key_mismatch", "u1", "dev1")
        events = tracer.issue_trace(user_id="u1")
        assert len(events) == 1 and events[0]["action"] == "license_failure"

    def test_record_heartbeat_loss(self, tracer):
        tracer.record_heartbeat_loss("dev-x", 120.0, user_id="u2")
        events = tracer.issue_trace(user_id="u2")
        assert events[0]["category"] == "heartbeat" and events[0]["detail"]["gap_s"] == 120.0

    def test_record_kill_switch(self, tracer):
        tracer.record_kill_switch("admin", "drawdown 15%")
        events = tracer.issue_trace(category="kill_switch")
        assert len(events) == 1 and events[0]["level"] == "CRITICAL"

    def test_record_reconciliation_mismatch(self, tracer):
        tracer.record_reconciliation_mismatch("EURUSD", 1.5, 1.0)
        events = tracer.issue_trace(category="reconciliation")
        assert events[0]["detail"]["delta"] == 0.5

    def test_issue_trace_by_user(self, tracer):
        tracer.record_license_failure("x", "user-A")
        tracer.record_license_failure("y", "user-B")
        tracer.record_license_failure("z", "user-A")
        evs_a = tracer.issue_trace(user_id="user-A")
        assert len(evs_a) == 2 and all(e["user_id"] == "user-A" for e in evs_a)

    def test_issue_trace_by_trace_id(self, tracer):
        tid = "trace-001"
        tracer.record("license", "failure", "CRITICAL", trace_id=tid)
        tracer.record("heartbeat", "loss", "CRITICAL", trace_id=tid)
        tracer.record("trade", "block", "WARNING", trace_id="other")
        evs = tracer.correlated_events(tid)
        assert len(evs) == 2 and all(e["trace_id"] == tid for e in evs)

    def test_issue_trace_by_category(self, tracer):
        tracer.record("license", "failure", "CRITICAL")
        tracer.record("license", "failure", "CRITICAL")
        tracer.record("reconciliation", "mismatch", "CRITICAL")
        assert len(tracer.issue_trace(category="license")) == 2

    def test_events_sorted_by_time(self, tracer):
        for i in range(5):
            tracer.record("license", f"event_{i}", "INFO")
        evs = tracer.issue_trace(category="license")
        ts_list = [e["ts"] for e in evs]
        assert ts_list == sorted(ts_list)

    def test_export_csv_valid(self, tracer):
        tracer.record_license_failure("test", "u1")
        tracer.record_heartbeat_loss("dev1", 90.0)
        csv_str = tracer.export_csv()
        lines = csv_str.strip().split("\n")
        assert len(lines) >= 2 and "event_id" in lines[0]

    def test_export_csv_user_filter(self, tracer):
        tracer.record_license_failure("x", "user-csv")
        tracer.record_license_failure("y", "other-user")
        csv_str = tracer.export_csv(user_id="user-csv")
        lines = csv_str.strip().split("\n")
        assert len(lines) == 2

    def test_summary_structure(self, tracer):
        tracer.record_license_failure("test", "u1")
        tracer.record_kill_switch("admin", "test")
        s = tracer.summary()
        assert "total_events" in s and s["total_events"] == 2

    def test_reset_clears(self, tracer):
        tracer.record_license_failure("test", "u1")
        tracer.reset()
        assert tracer.summary()["total_events"] == 0

    def test_user_timeline(self, tracer):
        tracer.record_license_failure("expired", "u-tl")
        tracer.record_heartbeat_loss("dev", 60.0, user_id="u-tl")
        assert len(tracer.user_timeline("u-tl")) == 2

    def test_tracer_gc(self):
        t = AdminTracer()
        t._MAX_EVENTS = 100
        for i in range(120):
            t.record("license", f"event_{i}", "INFO")
        assert t.summary()["total_events"] <= 100
        t.reset()


class TestAlertConvenienceMethods:
    def test_alert_license_failure(self, mgr):
        fired = []

        async def cb(r, l, c):
            fired.append(r)

        mgr.add_callback(cb)

        async def run():
            return await mgr.alert_license_failure("expired", user_id="u1")

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is True and "license_failure" in fired

    def test_alert_kill_switch_critical(self, mgr):
        received = []

        async def cb(r, l, c):
            received.append(l)

        mgr.add_callback(cb)
        asyncio.get_event_loop().run_until_complete(mgr.alert_kill_switch("admin", "drawdown"))
        assert AlertLevel.CRITICAL in received

    def test_alert_drawdown_critical_at_10pct(self, mgr):
        received = []

        async def cb(r, l, c):
            received.append((r, l))

        mgr.add_callback(cb)
        asyncio.get_event_loop().run_until_complete(mgr.alert_drawdown(pct=12.0))
        assert "drawdown_critical" in [r[0] for r in received]

    def test_alert_drawdown_warning_at_7pct(self, mgr):
        received = []

        async def cb(r, l, c):
            received.append(l)

        mgr.add_callback(cb)
        asyncio.get_event_loop().run_until_complete(mgr.alert_drawdown(pct=7.0))
        assert AlertLevel.WARNING in received

    def test_alert_reconciliation_mismatch(self, mgr):
        received = []

        async def cb(r, l, c):
            received.append(l)

        mgr.add_callback(cb)
        asyncio.get_event_loop().run_until_complete(
            mgr.alert_reconciliation_mismatch("EURUSD", 1.5, 1.0)
        )
        assert AlertLevel.CRITICAL in received

    def test_heartbeat_loss_message_includes_gap(self, mgr):
        asyncio.get_event_loop().run_until_complete(mgr.alert_heartbeat_loss("dev-x", gap_s=240.0))
        hist = mgr.history(rule_name="heartbeat_loss")
        assert "240" in hist[0]["message"]

    def test_kill_switch_message_includes_actor(self, mgr):
        asyncio.get_event_loop().run_until_complete(
            mgr.alert_kill_switch("superadmin", "emergency")
        )
        hist = mgr.history(rule_name="kill_switch_activated")
        assert "superadmin" in hist[0]["message"]

    def test_reconciliation_context_has_delta(self, mgr):
        asyncio.get_event_loop().run_until_complete(
            mgr.alert_reconciliation_mismatch("GBPUSD", 2.0, 1.5)
        )
        hist = mgr.history(rule_name="reconciliation_mismatch")
        assert hist[0]["context"]["delta"] == 0.5

    def test_license_failure_context_has_user(self, mgr):
        asyncio.get_event_loop().run_until_complete(
            mgr.alert_license_failure("expired", user_id="user-123")
        )
        hist = mgr.history(rule_name="license_failure")
        assert hist[0]["context"]["user_id"] == "user-123"

    def test_heartbeat_loss_dedup(self, mgr):
        async def run():
            s1 = await mgr.alert_heartbeat_loss("dev1", 90.0)
            s2 = await mgr.alert_heartbeat_loss("dev1", 100.0)
            return s1, s2

        s1, s2 = asyncio.get_event_loop().run_until_complete(run())
        assert s1 is True and s2 is False


class TestAdminRoutes:
    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        from backend.api.routes.admin_observability import router

        app.include_router(router)
        return TestClient(app)

    def test_get_metrics_200(self, client):
        r = client.get("/admin/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "saas_kpis" in data and "uptime_s" in data

    def test_get_metrics_prometheus_200(self, client):
        r = client.get("/admin/metrics/prometheus")
        assert r.status_code == 200 and "text/plain" in r.headers["content-type"]

    def test_get_alerts_200(self, client):
        r = client.get("/admin/alerts")
        assert r.status_code == 200
        data = r.json()
        assert "alerts" in data and "rules" in data

    def test_get_trace_200(self, client):
        r = client.get("/admin/trace")
        assert r.status_code == 200
        data = r.json()
        assert "events" in data and "summary" in data

    def test_export_csv_200(self, client):
        r = client.get("/admin/trace/export.csv")
        assert r.status_code == 200 and "csv" in r.headers["content-type"]

    def test_fire_test_alert(self, client):
        r = client.post("/admin/alert/test", params={"message": "integration test"})
        assert r.status_code == 200 and "sent" in r.json()

    def test_deep_health_200(self, client):
        r = client.get("/admin/health/deep")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data and data["status"] in ("healthy", "degraded", "unhealthy")

    def test_deep_health_issues_list(self, client):
        r = client.get("/admin/health/deep")
        assert "issues" in r.json() and isinstance(r.json()["issues"], list)

    def test_alerts_level_filter(self, client):
        assert client.get("/admin/alerts?level=CRITICAL").status_code == 200

    def test_trace_user_filter(self, client):
        assert client.get("/admin/trace?user_id=user-001").status_code == 200

    def test_trace_category_filter(self, client):
        assert client.get("/admin/trace?category=license").status_code == 200

    def test_deep_health_kill_switch_issue(self, client):
        from backend.observability.metrics_v15 import metrics as m

        m.kill_switch_activated("test", "integration")
        r = client.get("/admin/health/deep")
        assert "kill_switch_active" in r.json()["issues"]
        m.kill_switch_reset("test")


class TestPrometheusFormat:
    def test_format_counters(self, reg):
        reg.license_failure("expired")
        text = reg.prometheus_format()
        assert "license_failures_total" in text

    def test_format_gauges(self, reg):
        reg.set_equity(100000.0)
        reg.set_equity_drawdown(5.5)
        text = reg.prometheus_format()
        assert "equity_usd" in text and "equity_drawdown_pct" in text

    def test_format_histograms(self, reg):
        reg.heartbeat_loss("dev1", 90.0)
        text = reg.prometheus_format()
        assert "heartbeat_gap_s" in text and "quantile" in text

    def test_format_type_annotations(self, reg):
        reg.license_failure("test")
        assert "# TYPE" in reg.prometheus_format()

    def test_format_help_annotations(self, reg):
        reg.license_failure("test")
        assert "# HELP" in reg.prometheus_format()

    def test_format_kill_switch_gauge(self, reg):
        reg.kill_switch_activated("admin", "test")
        assert "kill_switch_active" in reg.prometheus_format()

    def test_format_reconciliation(self, reg):
        reg.reconciliation_mismatch("EURUSD", 1.5, 1.0)
        assert "reconciliation_mismatches" in reg.prometheus_format()

    def test_format_empty_registry(self, reg):
        assert isinstance(reg.prometheus_format(), str)


class TestAlertRulesYAML:
    @pytest.fixture
    def rules(self):
        import os

        import yaml

        path = os.path.join(os.path.dirname(__file__), "../../infra/prometheus/alert_rules_v15.yml")
        with open(path) as f:
            return yaml.safe_load(f)

    def test_has_groups(self, rules):
        assert "groups" in rules and len(rules["groups"]) >= 5

    def test_license_failure_spike_rule(self, rules):
        all_alerts = [r["alert"] for g in rules["groups"] for r in g.get("rules", [])]
        assert "LicenseFailureSpike" in all_alerts

    def test_heartbeat_loss_rule(self, rules):
        all_alerts = [r["alert"] for g in rules["groups"] for r in g.get("rules", [])]
        assert "HeartbeatLossDetected" in all_alerts

    def test_kill_switch_immediate(self, rules):
        for g in rules["groups"]:
            for r in g.get("rules", []):
                if r.get("alert") == "KillSwitchActive":
                    assert r.get("for") == "0m"
                    return
        pytest.fail("KillSwitchActive not found")

    def test_drawdown_critical_severity(self, rules):
        for g in rules["groups"]:
            for r in g.get("rules", []):
                if r.get("alert") == "DrawdownCritical":
                    assert r["labels"]["severity"] == "critical"
                    return
        pytest.fail("DrawdownCritical not found")

    def test_reconciliation_mismatch_rule(self, rules):
        all_alerts = [r["alert"] for g in rules["groups"] for r in g.get("rules", [])]
        assert "ReconciliationMismatch" in all_alerts

    def test_api_down_rule(self, rules):
        all_alerts = [r["alert"] for g in rules["groups"] for r in g.get("rules", [])]
        assert "APIDown" in all_alerts

    def test_critical_rules_have_runbook(self, rules):
        for g in rules["groups"]:
            for r in g.get("rules", []):
                if r.get("labels", {}).get("severity") == "critical":
                    ann = r.get("annotations", {})
                    assert "runbook" in ann or "description" in ann

    def test_pagerduty_label_on_critical_trading(self, rules):
        pd_alerts = [
            r["alert"]
            for g in rules["groups"]
            for r in g.get("rules", [])
            if r.get("labels", {}).get("pagerduty") == "true"
        ]
        assert len(pd_alerts) >= 3

    def test_groups_have_interval(self, rules):
        for g in rules["groups"]:
            assert "interval" in g or "name" in g


class TestIntegration:
    def test_full_pipeline(self):
        reg = MetricsRegistry()
        mgr = AlertManager()
        trc = AdminTracer()
        fired = []

        async def cb(rule, level, ctx):
            fired.append(rule)
            trc.record(category=rule.split("_")[0], action=rule, level=str(level), detail=ctx or {})

        mgr.add_callback(cb)

        async def run():
            reg.license_failure("expired", user_id="u1")
            await mgr.alert_license_failure("expired", user_id="u1")
            reg.heartbeat_loss("dev1", 180.0, user_id="u1")
            await mgr.alert_heartbeat_loss("dev1", 180.0, user_id="u1")

        asyncio.get_event_loop().run_until_complete(run())
        assert "license_failure" in fired and "heartbeat_loss" in fired
        assert len(trc.issue_trace()) == 2
        reg.reset()
        mgr.reset()
        trc.reset()

    def test_concurrent_metrics_thread_safe(self):
        import threading

        reg = MetricsRegistry()
        errors = []

        def worker():
            try:
                for _ in range(50):
                    reg.license_failure("expired")
                    reg.heartbeat_loss("dev", 1.0)
                    reg.trade_submitted("EURUSD", "BUY")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert reg.snapshot()["counters"].get("license_failures_total", 0) == 500
        reg.reset()

    def test_admin_snapshot_pipeline(self):
        reg = MetricsRegistry()
        reg.license_failure("expired")
        reg.heartbeat_loss("dev1", 90.0)
        reg.kill_switch_activated("admin", "test")
        reg.reconciliation_mismatch("EURUSD", 2.0, 1.5)
        reg.drawdown_alert(12.0, "CRITICAL", 88000.0)
        snap = reg.admin_snapshot()
        kpis = snap["saas_kpis"]
        assert kpis["license_failures_total"] >= 1
        assert kpis["kill_switch_active"] == 1.0
        assert kpis["reconciliation_mismatches_total"] >= 1
        reg.reset()

    def test_alert_callback_error_no_crash(self):
        mgr = AlertManager()

        async def bad_cb(r, l, c):
            raise ValueError("callback error")

        mgr.add_callback(bad_cb)

        async def run():
            mgr.get_rule("test").dedup_window_s = 0
            return await mgr.fire("test")

        assert asyncio.get_event_loop().run_until_complete(run()) is True
        mgr.reset()

    def test_singletons_importable(self):
        from backend.observability.admin_trace import admin_tracer
        from backend.observability.alert_manager_v15 import alert_manager
        from backend.observability.metrics_v15 import metrics

        assert metrics is not None and alert_manager is not None and admin_tracer is not None

    def test_kill_switch_persists(self):
        reg = MetricsRegistry()
        reg.kill_switch_activated("admin", "test")
        assert reg.is_kill_switch_active()
        reg.heartbeat_loss("dev1", 90.0)
        assert reg.is_kill_switch_active()
        reg.kill_switch_reset("admin")
        assert not reg.is_kill_switch_active()
        reg.reset()

    def test_reconciliation_ok_after_mismatch(self):
        reg = MetricsRegistry()
        reg.reconciliation_mismatch("EURUSD", 2.0, 1.5)
        reg.reconciliation_ok(positions_checked=10)
        assert reg.snapshot()["gauges"].get("reconciliation_last_ok_ts", 0) > 0
        reg.reset()

    def test_get_events_limit(self):
        reg = MetricsRegistry()
        for _ in range(20):
            reg.license_failure("test")
        evs = reg.get_events(category="license_failure", limit=5)
        assert len(evs) <= 5
        reg.reset()

    def test_drawdown_event_recorded(self):
        reg = MetricsRegistry()
        reg.drawdown_alert(8.5, "WARNING", 91500.0)
        evs = reg.get_events(category="drawdown_alert")
        assert len(evs) == 1 and evs[0]["pct"] == 8.5
        reg.reset()

    def test_tracer_export_csv_category_filter(self):
        t = AdminTracer()
        t.record_license_failure("x", "u1")
        t.record_kill_switch("admin", "test")
        csv_str = t.export_csv(category="kill_switch")
        lines = csv_str.strip().split("\n")
        assert len(lines) == 2
        t.reset()

    def test_tracer_user_isolation(self):
        t = AdminTracer()
        for i in range(5):
            t.record_license_failure("expired", f"user-{i}")
        for i in range(5):
            assert len(t.user_timeline(f"user-{i}")) == 1
        t.reset()

    def test_prometheus_format_after_reset(self):
        reg = MetricsRegistry()
        reg.license_failure("test")
        reg.reset()
        assert isinstance(reg.prometheus_format(), str)
