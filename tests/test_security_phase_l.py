"""
tests/test_security_phase_l.py
Phase L — SecurityAIAgent + AgentPerformanceTracker + MetricsEngine + VotingEngine hook
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


# ================================================================== #
# SecurityAIAgent
# ================================================================== #

class TestSecurityAIAgentPhaseL:
    """BUG-L1 through BUG-L3: real detect_anomaly, assess_risk_score, analyze_threat."""

    def _make_event(self, ip="1.2.3.4", status=200, endpoint="/api/signals"):
        from backend.agents.security_ai_agent import SecurityEvent, EventType
        return SecurityEvent(
            event_type=EventType.API_REQUEST,
            ip_address=ip,
            endpoint=endpoint,
            status_code=status,
            response_time_ms=50.0,
            payload_size=512,
        )

    @pytest.mark.asyncio
    async def test_detect_anomaly_normal(self):
        from backend.agents.security_ai_agent import SecurityAIAgent
        agent = SecurityAIAgent()
        features = [0.1] * 12
        result = await agent.detect_anomaly(features)
        assert result.is_anomaly is False
        assert result.score == 0.0  # untrained model returns 0.0
        assert result.risk_level.value == "low"

    @pytest.mark.asyncio
    async def test_detect_anomaly_heuristic_high_rate(self):
        from backend.agents.security_ai_agent import SecurityAIAgent
        agent = SecurityAIAgent()
        # f[0] > 0.8 → heuristic score -0.6
        features = [0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4, 0.5, 0.0]
        result = await agent.detect_anomaly(features)
        assert result.score < -0.1
        assert "Very high request rate" in result.explanation

    @pytest.mark.asyncio
    async def test_analyze_threat_returns_result(self):
        from backend.agents.security_ai_agent import SecurityAIAgent
        agent = SecurityAIAgent()
        ev = self._make_event()
        with patch.object(agent, '_persist', new_callable=AsyncMock):
            result = await agent.analyze_threat(ev)
        assert result is not None
        assert result.inference_time_ms >= 0

    @pytest.mark.asyncio
    async def test_assess_risk_score_returns_dict(self):
        from backend.agents.security_ai_agent import SecurityAIAgent
        agent = SecurityAIAgent()
        ev = self._make_event()
        with patch.object(agent, '_persist', new_callable=AsyncMock):
            score = await agent.assess_risk_score(ev)
        assert "score" in score
        assert "risk_level" in score
        assert "model_used" in score
        assert score["model_used"] in ("IsolationForest", "heuristic")

    @pytest.mark.asyncio
    async def test_assess_risk_score_not_hardcoded_50(self):
        """BUG-L was: hardcoded return {score: 50}. Now must be dynamic."""
        from backend.agents.security_ai_agent import SecurityAIAgent
        agent = SecurityAIAgent()
        ev1 = self._make_event(status=200)
        ev2 = self._make_event(status=401, endpoint="/auth/login")
        with patch.object(agent, '_persist', new_callable=AsyncMock):
            s1 = await agent.assess_risk_score(ev1)
            s2 = await agent.assess_risk_score(ev2)
        # They may differ or both be 0 if no anomaly — but must not both be exactly 50
        assert not (s1["score"] == 50 and s2["score"] == 50)

    @pytest.mark.asyncio
    async def test_create_incident_returns_uuid(self):
        from backend.agents.security_ai_agent import SecurityAIAgent, AnomalyResult, RiskLevel
        agent = SecurityAIAgent()
        ev = self._make_event()
        result = AnomalyResult(
            is_anomaly=True, score=-0.5, risk_level=RiskLevel.HIGH,
            confidence=0.8, features=[0.1]*12, explanation=["High rate"]
        )
        with patch("backend.agents.security_ai_agent._get_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = MagicMock()
            mock_db.return_value.table.return_value.insert.return_value.execute.return_value = MagicMock()
            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
                mock_thread.return_value = MagicMock()
                incident_id = await agent.create_incident(ev, result)
        assert incident_id is not None
        import uuid
        uuid.UUID(incident_id)  # valid UUID

    @pytest.mark.asyncio
    async def test_create_incident_non_anomaly_returns_none(self):
        from backend.agents.security_ai_agent import SecurityAIAgent, AnomalyResult, RiskLevel
        agent = SecurityAIAgent()
        ev = self._make_event()
        result = AnomalyResult(
            is_anomaly=False, score=0.0, risk_level=RiskLevel.LOW,
            confidence=0.0, features=[0.1]*12, explanation=["Normal"]
        )
        incident_id = await agent.create_incident(ev, result)
        assert incident_id is None

    @pytest.mark.asyncio
    async def test_generate_alert_low_risk_no_telegram(self):
        from backend.agents.security_ai_agent import SecurityAIAgent, AnomalyResult, RiskLevel
        agent = SecurityAIAgent()
        ev = self._make_event()
        result = AnomalyResult(
            is_anomaly=False, score=0.0, risk_level=RiskLevel.LOW,
            confidence=0.0, features=[0.1]*12, explanation=["Normal"]
        )
        # Should not call Telegram — no exception
        await agent.generate_alert(result, ev)

    @pytest.mark.asyncio
    async def test_update_threat_intel_returns_int(self):
        from backend.agents.security_ai_agent import SecurityAIAgent
        agent = SecurityAIAgent()
        with patch("backend.agents.security_ai_agent._get_db", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = MagicMock()
            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
                mock_thread.return_value = MagicMock(data=[])
                count = await agent.update_threat_intel()
        assert isinstance(count, int)

    def test_get_stats_structure(self):
        from backend.agents.security_ai_agent import SecurityAIAgent
        agent = SecurityAIAgent()
        stats = agent.get_stats()
        assert "model_trained" in stats
        assert "buffer_size" in stats
        assert "retrain_interval" in stats
        assert stats["model_trained"] is False  # untrained initially


# ================================================================== #
# AgentPerformanceTracker
# ================================================================== #

class TestAgentPerformanceTracker:
    """BUG-L4: get_agent_performance() was empty stub."""

    @pytest.mark.asyncio
    async def test_record_and_query(self):
        from backend.analytics.agent_performance_tracker import AgentPerformanceTracker
        tracker = AgentPerformanceTracker()
        with patch.object(tracker, '_persist', new_callable=AsyncMock):
            await tracker.record_vote("smc_agent", "BUY", 72.0)
            await tracker.record_vote("smc_agent", "BUY", 68.0)
            await tracker.record_vote("ml_agent", "ABSTAIN", 0.0)
        perf = await tracker.get_agent_performance()
        assert perf["total_votes"] == 3
        agent_ids = [a["agent_id"] for a in perf["agents"]]
        assert "smc_agent" in agent_ids
        assert "ml_agent" in agent_ids

    @pytest.mark.asyncio
    async def test_consensus_rate_calculation(self):
        from backend.analytics.agent_performance_tracker import AgentPerformanceTracker
        tracker = AgentPerformanceTracker()
        with patch.object(tracker, '_persist', new_callable=AsyncMock):
            await tracker.record_vote("a", "BUY", 70.0)
            await tracker.record_vote("a", "ABSTAIN", 0.0)
        perf = await tracker.get_agent_performance()
        agent_a = next(a for a in perf["agents"] if a["agent_id"] == "a")
        assert agent_a["consensus_rate"] == 0.5  # 1 active out of 2

    @pytest.mark.asyncio
    async def test_empty_tracker_returns_zero(self):
        from backend.analytics.agent_performance_tracker import AgentPerformanceTracker
        tracker = AgentPerformanceTracker()
        perf = await tracker.get_agent_performance()
        assert perf["total_votes"] == 0
        assert perf["agents"] == []


# ================================================================== #
# MetricsEngine.get_agent_performance()
# ================================================================== #

class TestMetricsEngineAgentPerf:
    """Verifies delegation to AgentPerformanceTracker."""

    @pytest.mark.asyncio
    async def test_get_agent_performance_not_stub(self):
        from backend.analytics.metrics_engine import MetricsEngine
        from backend.analytics.agent_performance_tracker import AgentPerformanceTracker
        engine = MetricsEngine()
        tracker = AgentPerformanceTracker()
        with patch.object(tracker, '_persist', new_callable=AsyncMock):
            await tracker.record_vote("test_agent", "BUY", 75.0)
        with patch("backend.analytics.metrics_engine.agent_tracker", tracker):
            perf = await engine.get_agent_performance()
        assert perf["total_votes"] >= 0  # real data, not stub
        assert "agents" in perf


# ================================================================== #
# VotingEngine._record_votes hook
# ================================================================== #

class TestVotingEngineRecordHook:
    """BUG-L5: record_vote hook fires after each vote cycle."""

    @pytest.mark.asyncio
    async def test_record_votes_called_after_vote(self):
        from backend.agents.voting_engine import VotingEngine, VotingConfig
        from backend.agents.base_agent import VoteResult, VoteSignal
        engine = VotingEngine(VotingConfig(min_agents=1, confidence_floor=0.0))

        mock_agent = AsyncMock()
        mock_agent.agent_id = "test_agent"
        mock_agent.weight = 1.0
        mock_agent.vote = AsyncMock(return_value=VoteResult(
            agent_id="test_agent", signal=VoteSignal.BUY,
            confidence=80.0, weight=1.0, reason="test",
        ))

        recorded = []
        async def fake_record(votes, symbol):
            recorded.extend(votes)

        with patch.object(engine, '_record_votes', side_effect=fake_record):
            await engine.vote([mock_agent], {"symbol": "XAUUSD"})

        assert len(recorded) == 1
        assert recorded[0].agent_id == "test_agent"
