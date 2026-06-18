"""
faz 9 - Observability Test Suite
42 test: metrics, logger, alert_manager, tracing, middleware
"""
from __future__ import annotations

import asyncio
import pytest
import time

from backend.observability.metrics import MetricsRegistry, Counter, Gauge, Histogram
from backend.observability.structured_logger import (
    StructuredLogger, get_logger, set_request_context, get_request_id, get_trace_id
)
from backend.observability.alert_manager import (
    AlertManager, AlertRule, AlertSeverity
)
from backend.observability.tracing import Tracer, Span


# ============================================================
# Metrics Tests
# ============================================================
class TestCounter:
    def test_initial_value_zero(self):
        c = Counter(name="test_counter")
        assert c.value == 0.0

    def test_inc_default(self):
        c = Counter(name="t")
        c.inc()
        assert c.value == 1.0

    def test_inc_custom_amount(self):
        c = Counter(name="t")
        c.inc(5.0)
        assert c.value == 5.0

    def test_inc_accumulates(self):
        c = Counter(name="t")
        c.inc(3)
        c.inc(2)
        assert c.value == 5.0


class TestGauge:
    def test_set(self):
        g = Gauge(name="g")
        g.set(42.0)
        assert g.value == 42.0

    def test_inc_dec(self):
        g = Gauge(name="g")
        g.inc(10)
        g.dec(3)
        assert g.value == 7.0


class TestHistogram:
    def test_empty(self):
        h = Histogram(name="h")
        assert h.count == 0
        assert h.mean == 0.0

    def test_observe(self):
        h = Histogram(name="h")
        h.observe(0.1)
        h.observe(0.2)
        assert h.count == 2
        assert abs(h.mean - 0.15) < 1e-9

    def test_percentile(self):
        h = Histogram(name="h")
        for i in range(100):
            h.observe(float(i))
        p50 = h.percentile(50)
        assert 48 <= p50 <= 52

    def test_bucket_counts(self):
        h = Histogram(name="h", buckets=[0.1, 0.5, 1.0])
        h.observe(0.05)
        h.observe(0.3)
        h.observe(0.8)
        counts = h.bucket_counts()
        assert counts["0.1"] == 1
        assert counts["0.5"] == 2
        assert counts["1.0"] == 3


class TestMetricsRegistry:
    def test_singleton_has_http_metrics(self):
        r = MetricsRegistry()
        assert hasattr(r, "http_requests_total")
        assert hasattr(r, "http_request_duration")
        assert hasattr(r, "http_errors_total")

    def test_snapshot_structure(self):
        r = MetricsRegistry()
        snap = r.snapshot()
        assert "counters" in snap
        assert "gauges" in snap
        assert "histograms" in snap
        assert "uptime_seconds" in snap

    def test_prometheus_format(self):
        r = MetricsRegistry()
        r.http_requests_total.inc(5)
        text = r.prometheus_format()
        assert "http_requests_total" in text
        assert "# TYPE" in text

    def test_agent_metrics_exist(self):
        r = MetricsRegistry()
        assert hasattr(r, "agent_votes_total")
        assert hasattr(r, "ml_drift_score")
        assert hasattr(r, "mt5_connected")


# ============================================================
# Structured Logger Tests
# ============================================================
class TestStructuredLogger:
    def test_get_logger_returns_instance(self):
        logger = get_logger("test")
        assert isinstance(logger, StructuredLogger)

    def test_request_context_set(self):
        set_request_context(request_id="abc123", trace_id="xyz789")
        assert get_request_id() == "abc123"
        assert get_trace_id() == "xyz789"

    def test_auto_request_id(self):
        set_request_context()
        rid = get_request_id()
        assert len(rid) > 0

    def test_logger_methods_exist(self):
        logger = get_logger("test")
        assert callable(logger.debug)
        assert callable(logger.info)
        assert callable(logger.warning)
        assert callable(logger.error)
        assert callable(logger.critical)


# ============================================================
# Alert Manager Tests
# ============================================================
class TestAlertManager:
    def setup_method(self):
        self.manager = AlertManager()

    @pytest.mark.asyncio
    async def test_fire_known_rule(self):
        fired = await self.manager.fire(
            "circuit_breaker_open",
            context={"service": "db"}
        )
        assert fired is True

    @pytest.mark.asyncio
    async def test_fire_unknown_rule_returns_false(self):
        fired = await self.manager.fire("nonexistent_rule")
        assert fired is False

    @pytest.mark.asyncio
    async def test_deduplication(self):
        rule = AlertRule(
            name="test_dedup",
            severity=AlertSeverity.WARNING,
            message_template="test {val}",
            min_interval_seconds=999,
        )
        self.manager.add_rule(rule)
        fired1 = await self.manager.fire("test_dedup", {"val": 1})
        fired2 = await self.manager.fire("test_dedup", {"val": 2})
        assert fired1 is True
        assert fired2 is False  # deduplication

    @pytest.mark.asyncio
    async def test_history_stored(self):
        await self.manager.fire(
            "ml_drift_high",
            context={"symbol": "XAUUSD", "score": 0.75}
        )
        history = self.manager.get_history()
        assert len(history) >= 1

    def test_default_rules_exist(self):
        rules = self.manager.get_rules()
        assert "circuit_breaker_open" in rules
        assert "mt5_disconnected" in rules
        assert "daily_loss_limit" in rules

    def test_add_custom_rule(self):
        rule = AlertRule(
            name="custom_test",
            severity=AlertSeverity.INFO,
            message_template="custom {msg}",
        )
        self.manager.add_rule(rule)
        assert "custom_test" in self.manager.get_rules()

    @pytest.mark.asyncio
    async def test_telegram_callback(self):
        messages = []

        async def fake_telegram(msg: str) -> None:
            messages.append(msg)

        self.manager.register_telegram(fake_telegram)
        await self.manager.fire(
            "mt5_disconnected",
            context={"reason": "timeout"}
        )
        assert len(messages) == 1
        assert "MT5" in messages[0]


# ============================================================
# Tracing Tests
# ============================================================
class TestTracer:
    def setup_method(self):
        self.tracer = Tracer()

    @pytest.mark.asyncio
    async def test_span_basic(self):
        async with self.tracer.start_span("test_op") as span:
            assert span.name == "test_op"
            assert span.end_time is None

        assert span.end_time is not None
        assert span.status == "OK"

    @pytest.mark.asyncio
    async def test_span_duration(self):
        async with self.tracer.start_span("timed_op") as span:
            await asyncio.sleep(0.05)

        assert span.duration_ms >= 40

    @pytest.mark.asyncio
    async def test_span_error(self):
        with pytest.raises(ValueError):
            async with self.tracer.start_span("error_op") as span:
                raise ValueError("test error")

        assert span.status == "ERROR"
        assert "test error" in span.error

    @pytest.mark.asyncio
    async def test_span_tags(self):
        async with self.tracer.start_span("tagged", tags={"symbol": "XAUUSD"}) as span:
            span.set_tag("direction", "BUY")

        assert span.tags["symbol"] == "XAUUSD"
        assert span.tags["direction"] == "BUY"

    @pytest.mark.asyncio
    async def test_span_events(self):
        async with self.tracer.start_span("with_events") as span:
            span.add_event("checkpoint", {"step": 1})
            span.add_event("checkpoint", {"step": 2})

        assert len(span.events) == 2

    @pytest.mark.asyncio
    async def test_recent_spans(self):
        async with self.tracer.start_span("op1"):
            pass
        async with self.tracer.start_span("op2"):
            pass

        spans = self.tracer.get_recent_spans(limit=10)
        names = [s["name"] for s in spans]
        assert "op1" in names
        assert "op2" in names

    @pytest.mark.asyncio
    async def test_summary(self):
        async with self.tracer.start_span("s1"):
            pass
        summary = self.tracer.summary()
        assert summary["total"] >= 1
        assert "avg_duration_ms" in summary

    @pytest.mark.asyncio
    async def test_slow_spans_filtered(self):
        async with self.tracer.start_span("fast_op"):
            pass  # < 500ms

        slow = self.tracer.get_slow_spans(threshold_ms=500)
        # fast_op should NOT be in slow list
        names = [s["name"] for s in slow]
        assert "fast_op" not in names

    @pytest.mark.asyncio
    async def test_max_span_eviction(self):
        self.tracer.MAX_SPANS = 5
        for i in range(10):
            async with self.tracer.start_span(f"op{i}"):
                pass
        assert len(self.tracer._spans) <= 5
