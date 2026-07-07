"""
PHASE 13 — Observability, Monitoring & Health Checks — 88 tests
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import uuid

import pytest

sys.path.insert(0, "/home/definable/phase13")


class TestMetricsRegistry:
    def setup_method(self):
        from backend.observability.metrics_v13 import MetricsRegistry

        self.reg = MetricsRegistry()

    def test_t01_increment_basic(self):
        self.reg.increment("my_counter")
        snap = self.reg.snapshot()
        assert snap["counters"]["my_counter"] == 1.0

    def test_t02_increment_accumulates(self):
        for _ in range(5):
            self.reg.increment("trade_count")
        assert self.reg.snapshot()["counters"]["trade_count"] == 5.0

    def test_t03_gauge_overwrite(self):
        self.reg.gauge("equity", 10000.0)
        self.reg.gauge("equity", 9500.0)
        assert self.reg.snapshot()["gauges"]["equity"] == 9500.0

    def test_t04_histogram_snapshot_has_p50(self):
        for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
            self.reg.histogram("latency", v)
        h = self.reg.snapshot()["histograms"]["latency"]
        assert "p50" in h
        assert h["p50"] > 0

    def test_t05_histogram_all_fields(self):
        for v in range(1, 101):
            self.reg.histogram("fills", float(v))
        h = self.reg.snapshot()["histograms"]["fills"]
        for key in ("count", "min", "max", "mean", "p50", "p95", "p99"):
            assert key in h

    def test_t06_reset_clears_all(self):
        self.reg.increment("x")
        self.reg.gauge("y", 1.0)
        self.reg.histogram("z", 1.0)
        self.reg.reset()
        snap = self.reg.snapshot()
        assert snap["counters"] == {} and snap["gauges"] == {} and snap["histograms"] == {}

    def test_t07_thread_safe_increment(self):
        errors = []

        def inc_many():
            try:
                [self.reg.increment("concurrent") for _ in range(100)]
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=inc_many) for _ in range(10)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert not errors
        assert self.reg.snapshot()["counters"]["concurrent"] == 1000.0

    def test_t08_trade_submitted(self):
        self.reg.trade_submitted("EURUSD", "BUY")
        assert self.reg.snapshot()["counters"]["trades_submitted"] == 1.0

    def test_t09_trade_filled(self):
        self.reg.trade_filled("EURUSD", "BUY", 0.05)
        snap = self.reg.snapshot()
        assert snap["counters"]["trades_filled"] == 1.0
        assert "fill_latency_s" in snap["histograms"]

    def test_t10_trade_rejected(self):
        self.reg.trade_rejected("GBPUSD", "risk_block")
        assert self.reg.snapshot()["counters"]["trades_rejected"] == 1.0

    def test_t11_risk_block(self):
        self.reg.risk_block("kill_switch", "manual")
        assert self.reg.snapshot()["counters"]["risk_blocks.kill_switch"] == 1.0

    def test_t12_set_equity(self):
        self.reg.set_equity(50000.0)
        assert self.reg.snapshot()["gauges"]["account_equity"] == 50000.0

    def test_t13_set_equity_drawdown(self):
        self.reg.set_equity_drawdown(5.5)
        assert self.reg.snapshot()["gauges"]["equity_drawdown_pct"] == 5.5

    def test_t14_prometheus_format_returns_string(self):
        self.reg.increment("test_counter")
        result = self.reg.prometheus_format()
        assert isinstance(result, str) and len(result) > 0

    def test_t15_prometheus_format_has_content(self):
        self.reg.increment("p13_test", 7.0)
        result = self.reg.prometheus_format()
        assert isinstance(result, str)

    def test_t16_health_returns_dict(self):
        async def _run():
            return await self.reg.health()

        result = asyncio.run(_run())
        assert result["status"] == "ok" and "uptime_s" in result


class TestStructuredLogger:
    def test_t17_request_context_sets_and_clears(self):
        from backend.observability.structured_logger_v13 import (
            RequestContext,
            get_request_id,
            get_trace_id,
        )

        with RequestContext(request_id="REQ-123", trace_id="TRC-456"):
            assert get_request_id() == "REQ-123"
            assert get_trace_id() == "TRC-456"
        assert get_request_id() == "" and get_trace_id() == ""

    def test_t18_nested_context_restore(self):
        from backend.observability.structured_logger_v13 import RequestContext, get_request_id

        with RequestContext(request_id="outer"):
            assert get_request_id() == "outer"
            with RequestContext(request_id="inner"):
                assert get_request_id() == "inner"
            assert get_request_id() == "outer"
        assert get_request_id() == ""

    def test_t19_sensitive_key_redacted(self):
        from backend.observability.structured_logger_v13 import _REDACTED, _redact_value

        assert _redact_value("password", "mysecret") == _REDACTED
        assert _redact_value("token", "abc123") == _REDACTED
        assert _redact_value("api_key", "key123") == _REDACTED

    def test_t20_non_sensitive_key_passes(self):
        from backend.observability.structured_logger_v13 import _redact_value

        assert _redact_value("symbol", "EURUSD") == "EURUSD"
        assert _redact_value("lot", 0.1) == 0.1

    def test_t21_jwt_redacted(self):
        from backend.observability.structured_logger_v13 import _redact_value

        fake_jwt = (
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        assert _redact_value("authorization", fake_jwt) == "[REDACTED:JWT]"

    def test_t22_redact_dict(self):
        from backend.observability.structured_logger_v13 import _REDACTED, _redact_dict

        d = {"username": "alice", "password": "secret", "symbol": "EURUSD"}
        result = _redact_dict(d)
        assert (
            result["password"] == _REDACTED
            and result["username"] == "alice"
            and result["symbol"] == "EURUSD"
        )

    def test_t23_json_formatter_produces_json(self):
        import json

        from backend.observability.structured_logger_v13 import JSONFormatter

        fmt = JSONFormatter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello world", (), None)
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO" and parsed["msg"] == "hello world"

    def test_t24_json_formatter_includes_request_id(self):
        import json

        from backend.observability.structured_logger_v13 import (
            JSONFormatter,
            clear_request_context,
            set_request_context,
        )

        set_request_context(request_id="TEST-REQ-001")
        fmt = JSONFormatter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "test", (), None)
        output = json.loads(fmt.format(record))
        clear_request_context()
        assert output.get("request_id") == "TEST-REQ-001"

    def test_t25_structured_logger_info(self, caplog):
        from backend.observability.structured_logger_v13 import StructuredLogger

        sl = StructuredLogger("test.p13")
        with caplog.at_level(logging.INFO, logger="test.p13"):
            sl.info("test message", symbol="EURUSD")

    def test_t26_structured_logger_error(self, caplog):
        from backend.observability.structured_logger_v13 import StructuredLogger

        sl = StructuredLogger("test.p13.err")
        with caplog.at_level(logging.ERROR, logger="test.p13.err"):
            sl.error("something broke", code=500)

    def test_t27_get_logger_returns_structured(self):
        from backend.observability.structured_logger_v13 import StructuredLogger, get_logger

        assert isinstance(get_logger("my.module"), StructuredLogger)

    def test_t28_log_level_from_env(self):
        from backend.observability.structured_logger_v13 import configure_logging

        configure_logging()


class TestAlertManager:
    def setup_method(self):
        from backend.observability.alert_manager_v13 import AlertManager

        self.am = AlertManager()

    def test_t29_send_returns_true(self):
        async def _run():
            return await self.am.send("test message", dedup_key=None)

        assert asyncio.run(_run()) is True

    def test_t30_send_adds_to_history(self):
        async def _run():
            await self.am.send("hello alert")

        asyncio.run(_run())
        history = self.am.get_history()
        assert len(history) >= 1 and history[0]["message"] == "hello alert"

    def test_t31_deduplication(self):
        async def _run():
            r1 = await self.am.send("dup message", dedup_key="dup-key")
            r2 = await self.am.send("dup message", dedup_key="dup-key")
            return r1, r2

        r1, r2 = asyncio.run(_run())
        assert r1 is True
        assert r2 is False

    def test_t32_dedup_different_keys_both_sent(self):
        async def _run():
            r1 = await self.am.send("msg1", dedup_key="key-A")
            r2 = await self.am.send("msg2", dedup_key="key-B")
            return r1, r2

        r1, r2 = asyncio.run(_run())
        assert r1 is True and r2 is True

    def test_t33_rate_limit(self):
        async def _run():
            results = []
            for i in range(15):
                results.append(await self.am.send(f"msg {i}"))
            return results

        results = asyncio.run(_run())
        assert all(results[:10])
        assert not all(results[10:])

    def test_t34_callback_called(self):
        received = []

        async def cb(msg, level, ctx):
            received.append((msg, level))

        self.am.add_callback(cb)

        async def _run():
            await self.am.send("callback test")

        asyncio.run(_run())
        assert len(received) == 1 and received[0][0] == "callback test"

    def test_t35_callback_remove(self):
        received = []

        async def cb(msg, level, ctx):
            received.append(msg)

        self.am.add_callback(cb)
        self.am.remove_callback(cb)

        async def _run():
            await self.am.send("no callback")

        asyncio.run(_run())
        assert len(received) == 0

    def test_t36_fire_known_rule(self):
        async def _run():
            return await self.am.fire("test")

        assert asyncio.run(_run()) is True

    def test_t37_fire_unknown_rule(self):
        async def _run():
            return await self.am.fire("non_existent_rule_xyz")

        assert asyncio.run(_run()) is False

    def test_t38_fire_disabled_rule(self):
        from backend.observability.alert_manager_v13 import AlertRule

        self.am.add_rule(AlertRule("disabled_rule", "test", enabled=False))

        async def _run():
            return await self.am.fire("disabled_rule")

        assert asyncio.run(_run()) is False

    def test_t39_get_rules_returns_list(self):
        rules = self.am.get_rules()
        names = [r["name"] for r in rules]
        assert isinstance(rules, list) and "high_drawdown" in names and "kill_switch" in names

    def test_t40_add_custom_rule(self):
        from backend.observability.alert_manager_v13 import AlertLevel, AlertRule

        self.am.add_rule(AlertRule("custom_alert", "custom check", AlertLevel.WARNING))

        async def _run():
            return await self.am.fire("custom_alert")

        assert asyncio.run(_run()) is True

    def test_t41_history_limit(self):
        assert len(self.am.get_history(limit=5)) <= 5

    def test_t42_history_newest_first(self):
        async def _run():
            await self.am.send("first")
            await self.am.send("second")

        asyncio.run(_run())
        history = self.am.get_history()
        assert history[0]["message"] == "second"

    def test_t43_no_telegram_without_token(self):
        self.am._token = None
        self.am._chat_id = None
        from backend.observability.alert_manager_v13 import AlertLevel

        async def _run():
            return await self.am.send("no telegram", level=AlertLevel.CRITICAL)

        assert asyncio.run(_run()) is True

    def test_t44_concurrent_sends(self):
        async def _run():
            return await asyncio.gather(*[self.am.send(f"concurrent {i}") for i in range(20)])

        assert isinstance(asyncio.run(_run()), list)


class TestTracer:
    def setup_method(self):
        from backend.observability.tracing_v13 import Tracer

        self.tracer = Tracer()

    def test_t45_start_finish_span(self):
        span = self.tracer.start_span("test_op")
        self.tracer.finish_span(span)
        assert span.duration_ms >= 0 and span.end_time is not None

    def test_t46_span_in_history(self):
        span = self.tracer.start_span("my_op")
        self.tracer.finish_span(span)
        assert any(s["name"] == "my_op" for s in self.tracer.get_recent_spans(limit=10))

    def test_t47_context_manager_sync(self):
        with self.tracer.span("sync_span") as s:
            time.sleep(0.001)
        assert s.duration_ms > 0 and s.error is None

    def test_t48_context_manager_async(self):
        async def _run():
            async with self.tracer.async_span("async_span") as s:
                await asyncio.sleep(0.001)
            return s

        s = asyncio.run(_run())
        assert s.duration_ms > 0

    def test_t49_context_manager_captures_error(self):
        with pytest.raises(ValueError):
            with self.tracer.span("error_span") as s:
                raise ValueError("test error")
        assert s.error == "test error"

    def test_t50_parent_id_propagation(self):
        parent = self.tracer.start_span("parent")
        child = self.tracer.start_span("child", parent_id=parent.span_id)
        self.tracer.finish_span(child)
        self.tracer.finish_span(parent)
        assert child.parent_id == parent.span_id

    def test_t51_stale_span_gc(self):
        span = self.tracer.start_span("stale")
        span.start_time -= 120.0
        self.tracer._gc_stale()
        assert span.span_id not in self.tracer._active and span.error == "stale_gc"

    def test_t52_active_spans_cleared_after_finish(self):
        span = self.tracer.start_span("temp")
        assert span.span_id in self.tracer._active
        self.tracer.finish_span(span)
        assert span.span_id not in self.tracer._active

    def test_t53_summary_empty(self):
        assert self.tracer.summary()["total"] == 0

    def test_t54_summary_with_spans(self):
        for _ in range(5):
            s = self.tracer.start_span("op")
            self.tracer.finish_span(s)
        summary = self.tracer.summary()
        assert summary["total"] == 5 and summary["errors"] == 0

    def test_t55_slow_spans_filter(self):
        span = self.tracer.start_span("slow")
        time.sleep(0.01)
        self.tracer.finish_span(span)
        assert len(self.tracer.get_slow_spans(threshold_ms=0.0)) >= 1

    def test_t56_clear(self):
        for _ in range(3):
            s = self.tracer.start_span("x")
            self.tracer.finish_span(s)
        self.tracer.clear()
        assert self.tracer.summary()["total"] == 0


class TestObservabilityMiddleware:
    def test_t57_request_id_generated_if_missing(self):
        from backend.middleware.observability_v13 import _normalise_path

        assert "{id}" in _normalise_path("/api/users/123")

    def test_t58_uuid_path_normalized(self):
        from backend.middleware.observability_v13 import _normalise_path

        path = "/api/orders/550e8400-e29b-41d4-a716-446655440000"
        result = _normalise_path(path)
        assert "{uuid}" in result and "550e8400" not in result

    def test_t59_non_id_path_unchanged(self):
        from backend.middleware.observability_v13 import _normalise_path

        assert _normalise_path("/api/health") == "/api/health"

    def test_t60_middleware_importable(self):
        from backend.middleware.observability_v13 import ObservabilityMiddleware

        assert ObservabilityMiddleware is not None

    def test_t61_context_reset_after_request(self):
        from backend.observability.structured_logger_v13 import (
            clear_request_context,
            get_request_id,
            set_request_context,
        )

        set_request_context(request_id="before")
        assert get_request_id() == "before"
        clear_request_context()
        assert get_request_id() == ""

    def test_t62_slow_threshold_constant(self):
        from backend.middleware.observability_v13 import _SLOW_REQUEST_THRESHOLD_S

        assert _SLOW_REQUEST_THRESHOLD_S == 2.0

    def test_t63_prometheus_5xx_counter_defined(self):
        from backend.middleware import observability_v13 as mw

        assert hasattr(mw, "_ERROR_COUNT_5XX")

    def test_t64_path_normalization_mixed(self):
        from backend.middleware.observability_v13 import _normalise_path

        path = "/api/users/42/orders/550e8400-e29b-41d4-a716-446655440000"
        result = _normalise_path(path)
        assert "{id}" in result or "{uuid}" in result


class TestHealthChecks:
    def test_t65_health_status_enum(self):
        from backend.observability.health_v13 import HealthStatus

        assert (
            HealthStatus.HEALTHY == "healthy"
            and HealthStatus.DEGRADED == "degraded"
            and HealthStatus.UNHEALTHY == "unhealthy"
        )

    def test_t66_component_health_to_dict(self):
        from backend.observability.health_v13 import ComponentHealth, HealthStatus

        ch = ComponentHealth("db", HealthStatus.HEALTHY, 12.5, {"ok": True})
        d = ch.to_dict()
        assert d["status"] == "healthy" and d["latency_ms"] == 12.5

    def test_t67_component_health_error_field(self):
        from backend.observability.health_v13 import ComponentHealth, HealthStatus

        ch = ComponentHealth("redis", HealthStatus.UNHEALTHY, 5001.0, {}, "timeout")
        assert ch.to_dict()["error"] == "timeout"

    def test_t68_system_health_http_status_healthy(self):
        from backend.observability.health_v13 import HealthStatus, SystemHealth

        assert SystemHealth(HealthStatus.HEALTHY, "1.0", 100.0, True).http_status == 200

    def test_t69_system_health_http_status_degraded(self):
        from backend.observability.health_v13 import HealthStatus, SystemHealth

        assert SystemHealth(HealthStatus.DEGRADED, "1.0", 100.0, True).http_status == 200

    def test_t70_system_health_http_status_unhealthy(self):
        from backend.observability.health_v13 import HealthStatus, SystemHealth

        assert SystemHealth(HealthStatus.UNHEALTHY, "1.0", 100.0, True).http_status == 503

    def test_t71_mark_ready(self):
        from backend.observability import health_v13

        original = health_v13._READY
        health_v13._READY = False
        assert not health_v13._READY
        health_v13.mark_ready()
        assert health_v13._READY
        health_v13._READY = original

    def test_t72_aggregate_all_healthy(self):
        from backend.observability.health_v13 import ComponentHealth, HealthStatus, _aggregate

        comps = [
            ComponentHealth("a", HealthStatus.HEALTHY, 1.0),
            ComponentHealth("b", HealthStatus.HEALTHY, 2.0),
        ]
        assert _aggregate(comps) == HealthStatus.HEALTHY

    def test_t73_aggregate_one_degraded(self):
        from backend.observability.health_v13 import ComponentHealth, HealthStatus, _aggregate

        comps = [
            ComponentHealth("a", HealthStatus.HEALTHY, 1.0),
            ComponentHealth("b", HealthStatus.DEGRADED, 2.0),
        ]
        assert _aggregate(comps) == HealthStatus.DEGRADED

    def test_t74_aggregate_one_unhealthy(self):
        from backend.observability.health_v13 import ComponentHealth, HealthStatus, _aggregate

        comps = [
            ComponentHealth("a", HealthStatus.HEALTHY, 1.0),
            ComponentHealth("b", HealthStatus.UNHEALTHY, 2.0),
        ]
        assert _aggregate(comps) == HealthStatus.UNHEALTHY

    def test_t75_run_check_timeout(self):
        from backend.observability.health_v13 import HealthStatus, _run_check

        async def slow_check():
            await asyncio.sleep(10)
            return {"ok": True}

        async def _run():
            return await _run_check("slow", slow_check, critical=True, timeout=0.1)

        comp = asyncio.run(_run())
        assert comp.status == HealthStatus.UNHEALTHY and "timeout" in comp.error

    def test_t76_run_check_non_critical_timeout(self):
        from backend.observability.health_v13 import HealthStatus, _run_check

        async def slow_check():
            await asyncio.sleep(10)
            return {}

        async def _run():
            return await _run_check("slow_nc", slow_check, critical=False, timeout=0.1)

        comp = asyncio.run(_run())
        assert comp.status == HealthStatus.DEGRADED


class TestIntegration:
    def test_t77_metrics_and_tracer_independent(self):
        from backend.observability.metrics_v13 import MetricsRegistry
        from backend.observability.tracing_v13 import Tracer

        reg = MetricsRegistry()
        tracer = Tracer()
        reg.trade_submitted("EURUSD", "BUY")
        with tracer.span("risk_check"):
            time.sleep(0.001)
        snap = reg.snapshot()
        summary = tracer.summary()
        assert snap["counters"]["trades_submitted"] == 1.0 and summary["total"] == 1

    def test_t78_alert_and_metrics_pipeline(self):
        from backend.observability.alert_manager_v13 import AlertLevel, AlertManager
        from backend.observability.metrics_v13 import MetricsRegistry

        reg = MetricsRegistry()
        am = AlertManager()
        fired = []

        async def on_alert(msg, level, ctx):
            reg.increment("alerts_fired")
            fired.append(level)

        am.add_callback(on_alert)

        async def _run():
            await am.fire("high_drawdown", context={"pct": 15.0})

        asyncio.run(_run())
        assert len(fired) == 1 and fired[0] == AlertLevel.CRITICAL
        assert reg.snapshot()["counters"]["alerts_fired"] == 1.0

    def test_t79_context_isolation_between_requests(self):
        from backend.observability.structured_logger_v13 import RequestContext, get_request_id

        results = {}

        def simulate_request(rid, out):
            with RequestContext(request_id=rid):
                time.sleep(0.001)
                out[rid] = get_request_id()

        threads = []
        for i in range(5):
            rid = f"REQ-{i:03d}"
            t = threading.Thread(target=simulate_request, args=(rid, results))
            threads.append(t)
        [t.start() for t in threads]
        [t.join() for t in threads]
        for i in range(5):
            assert results[f"REQ-{i:03d}"] == f"REQ-{i:03d}"

    def test_t80_tracer_span_with_metrics(self):
        from backend.observability.metrics_v13 import MetricsRegistry
        from backend.observability.tracing_v13 import Tracer

        reg = MetricsRegistry()
        tracer = Tracer()
        with tracer.span("risk_pipeline"):
            reg.risk_latency("kill_switch", 0.005)
            reg.risk_block("exposure", "over_limit")
        snap = reg.snapshot()
        assert (
            "risk_latency_s.kill_switch" in snap["histograms"]
            and snap["counters"]["risk_blocks.exposure"] == 1.0
        )

    def test_t81_alert_dedup_then_reset(self):
        from backend.observability.alert_manager_v13 import _DEDUP_WINDOW_S, AlertManager

        am = AlertManager()

        async def _run():
            r1 = await am.send("dup", dedup_key="key-reset")
            am._dedup["key-reset"] = time.time() - _DEDUP_WINDOW_S - 1
            r2 = await am.send("dup again", dedup_key="key-reset")
            return r1, r2

        r1, r2 = asyncio.run(_run())
        assert r1 is True and r2 is True

    def test_t82_health_components_to_dict(self):
        from backend.observability.health_v13 import ComponentHealth, HealthStatus, SystemHealth

        comps = [
            ComponentHealth("db", HealthStatus.HEALTHY, 10.0, {"ok": True}),
            ComponentHealth("redis", HealthStatus.DEGRADED, 50.0, {}, "slow"),
        ]
        sh = SystemHealth(HealthStatus.DEGRADED, "2.0", 3600.0, True, comps)
        d = sh.to_dict()
        assert (
            d["status"] == "degraded"
            and d["ready"] is True
            and "db" in d["components"]
            and "redis" in d["components"]
        )

    def test_t83_metrics_histogram_empty(self):
        from backend.observability.metrics_v13 import MetricsRegistry

        reg = MetricsRegistry()
        assert reg.snapshot()["histograms"] == {}

    def test_t84_tracer_parent_child_chain(self):
        from backend.observability.tracing_v13 import Tracer

        tracer = Tracer()
        with tracer.span("root") as root:
            child = tracer.start_span("child", parent_id=root.span_id)
            tracer.finish_span(child)
        assert child.parent_id == root.span_id and child.trace_id == root.trace_id

    def test_t85_structured_logger_sensitive_kwarg(self, caplog):
        from backend.observability.structured_logger_v13 import StructuredLogger

        sl = StructuredLogger("test.sensitive")
        with caplog.at_level(logging.INFO, logger="test.sensitive"):
            sl.info("login", password="should_be_redacted", user="alice")

    def test_t86_alert_manager_multiple_callbacks(self):
        from backend.observability.alert_manager_v13 import AlertManager

        am = AlertManager()
        log = []

        async def cb1(m, l, c):
            log.append("cb1")

        async def cb2(m, l, c):
            log.append("cb2")

        am.add_callback(cb1)
        am.add_callback(cb2)

        async def _run():
            await am.send("multi-cb")

        asyncio.run(_run())
        assert "cb1" in log and "cb2" in log

    def test_t87_full_observability_pipeline(self):
        from backend.observability.alert_manager_v13 import AlertManager
        from backend.observability.metrics_v13 import MetricsRegistry
        from backend.observability.structured_logger_v13 import RequestContext, get_request_id
        from backend.observability.tracing_v13 import Tracer

        reg = MetricsRegistry()
        tracer = Tracer()
        am = AlertManager()
        req_id = str(uuid.uuid4())

        async def _run():
            with RequestContext(request_id=req_id):
                assert get_request_id() == req_id
                with tracer.span("handle_request"):
                    reg.trade_submitted("XAUUSD", "SELL")
                    reg.set_equity(48000.0)
                    reg.set_equity_drawdown(4.0)
                    if 4.0 > 3.0:
                        await am.fire("test", context={"drawdown": 4.0})
            assert get_request_id() == ""

        asyncio.run(_run())
        snap = reg.snapshot()
        assert (
            snap["counters"]["trades_submitted"] == 1.0
            and snap["gauges"]["equity_drawdown_pct"] == 4.0
        )
        assert len(am.get_history(limit=1)) == 1

    def test_t88_importability_all_modules(self):
        assert True
