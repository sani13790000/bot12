"""
tests/test_institutional_grade.py
Institutional-grade pipeline integration tests.

BUG-Q4 FIX: added @pytest.mark.integration markers.
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
class TestInstitutionalGradePipeline:
    """Full pipeline smoke tests at institutional grade."""

    def test_smc_engine_importable(self):
        from backend.analysis.smc_engine import SMCEngine
        assert SMCEngine is not None

    def test_decision_engine_importable(self):
        from backend.analysis.decision_engine import DecisionEngine
        assert DecisionEngine is not None

    def test_voting_engine_importable(self):
        from backend.agents.voting_engine import VotingEngine
        assert VotingEngine is not None

    def test_ml_agent_importable(self):
        from backend.agents.ml_agent import MLAgent
        assert MLAgent is not None

    def test_risk_orchestrator_importable(self):
        from backend.risk.risk_orchestrator import RiskOrchestrator
        assert RiskOrchestrator is not None

    def test_kill_switch_importable(self):
        from backend.risk.kill_switch import KillSwitch
        assert KillSwitch is not None

    def test_metrics_engine_importable(self):
        from backend.analytics.metrics_engine import MetricsEngine
        assert MetricsEngine is not None

    def test_analytics_service_importable(self):
        from backend.analytics.analytics_service import AnalyticsService
        assert AnalyticsService is not None

    def test_analytics_service_has_summary(self):
        from backend.analytics.analytics_service import AnalyticsService
        svc = AnalyticsService()
        assert hasattr(svc, "get_analytics_summary")

    def test_agent_tracker_lazy_lock(self):
        """BUG-Q3: lock must not be created at import time."""
        from backend.analytics.agent_performance_tracker import AgentPerformanceTracker
        tracker = AgentPerformanceTracker()
        # At construction, lock should NOT exist yet
        assert tracker._lock_obj is None
        # Accessing the property creates it lazily
        lock = tracker._lock
        assert lock is not None
        assert tracker._lock_obj is not None

    def test_analytics_summary_has_data_source_key(self):
        """BUG-Q2: summary must include data_source field."""
        import asyncio
        from backend.analytics.analytics_service import AnalyticsService
        svc = AnalyticsService()
        result = asyncio.get_event_loop().run_until_complete(svc.get_analytics_summary())
        assert "data_source" in result
        assert result["data_source"] in ("live_db", "fallback_db_error")
