"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Unit Tests: Multi-Agent Architecture
Coverage: BaseAgent, همه 7 Agent, VotingEngine, AgentService
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict
import pytest

from backend.agents.base_agent import AgentStatus, AgentVote, BaseAgent
from backend.agents.market_structure_agent import MarketStructureAgent
from backend.agents.liquidity_agent import LiquidityAgent
from backend.agents.smc_agent import SMCAgent
from backend.agents.ai_prediction_agent import AIPredictionAgent
from backend.agents.risk_agent import RiskAgent
from backend.agents.news_agent import NewsAgent
from backend.agents.execution_agent import ExecutionAgent
from backend.agents.voting_engine import TradeDecision, VotingEngine
from backend.agents.agent_service import AgentService, reset_agent_service


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def strong_buy_context() -> Dict[str, Any]:
    """Context با سیگنال قوی BUY."""
    return {
        "symbol": "XAUUSD", "direction": "BUY",
        # Market Structure
        "bos_detected": True, "bos_strength": 0.85,
        "choch_detected": True, "choch_strength": 0.70,
        "htf_alignment": True, "htf_score": 0.90,
        "structure_count": 3,
        # Liquidity
        "liquidity_sweep": True, "sweep_quality": 0.80,
        "internal_liquidity": 0.70, "external_liquidity": 0.60,
        "in_discount_zone": True, "in_premium_zone": False,
        # SMC
        "order_block_present": True, "order_block_quality": 0.85,
        "order_block_tested": True, "breaker_block": False,
        "fvg_present": True, "fvg_quality": 0.75,
        "ifvg_present": False, "in_kill_zone": True,
        "session_quality": 0.90,
        # AI
        "ai_prediction": {
            "probability": 82.0, "confidence": 88.0,
            "risk": "LOW", "model_auc": 0.72,
        },
        "decision_score": 82.0,
        # Risk — OK
        "portfolio_risk_percent": 2.0,
        "spread_ratio": 1.1,
        "atr_normalized": 1.2,
        "daily_trades_count": 2,
        "max_daily_trades": 5,
        "daily_loss_percent": 0.5,
        "max_daily_loss_percent": 3.0,
        "consecutive_losses": 0,
        # News — clear
        "news_filter_enabled": True, "upcoming_news": [],
        # Execution
        "trading_mode": "FULL_AUTO",
        "session": "LONDON",
        "expected_slippage_pips": 0.3,
        "market_depth_score": 0.85,
    }


@pytest.fixture
def blocked_risk_context(strong_buy_context) -> Dict[str, Any]:
    """Context با ریسک بلاک‌شده."""
    ctx = strong_buy_context.copy()
    ctx["portfolio_risk_percent"] = 6.0  # > MAX (5%)
    return ctx


@pytest.fixture
def no_trade_context() -> Dict[str, Any]:
    """Context با سیگنال ضعیف."""
    return {
        "symbol": "EURUSD", "direction": "BUY",
        "bos_detected": False, "choch_detected": False,
        "htf_alignment": False, "htf_score": 0.3,
        "liquidity_sweep": False, "in_discount_zone": False,
        "order_block_present": False, "fvg_present": False,
        "in_kill_zone": False, "session_quality": 0.3,
        "ai_prediction": {},
        "decision_score": 35.0,
        "portfolio_risk_percent": 1.0,
        "spread_ratio": 1.0,
        "atr_normalized": 1.0,
        "daily_trades_count": 0,
        "max_daily_trades": 5,
        "daily_loss_percent": 0.0,
        "max_daily_loss_percent": 3.0,
        "consecutive_losses": 0,
        "news_filter_enabled": False,
        "upcoming_news": [],
        "trading_mode": "FULL_AUTO",
        "session": "ASIAN",
        "expected_slippage_pips": 0.5,
        "market_depth_score": 0.5,
    }


# ── BaseAgent Tests ───────────────────────────────────────────

class ConcreteAgent(BaseAgent):
    """Agent ساده برای تست BaseAgent."""
    def __init__(self, score=70.0, confidence=80.0):
        super().__init__(name="Test", weight=1.0)
        self._score = score
        self._conf  = confidence

    async def analyze(self, context):
        return AgentVote(score=self._score, confidence=self._conf)


class ErrorAgent(BaseAgent):
    """Agent که همیشه خطا می‌دهد."""
    async def analyze(self, context):
        raise RuntimeError("Test error")


def test_agent_vote_clamp():
    """مقادیر خارج از [0,100] باید clamp شوند."""
    vote = AgentVote(score=150.0, confidence=-10.0)
    assert vote.score == 100.0
    assert vote.confidence == 0.0


def test_base_agent_disabled():
    """Agent غیرفعال باید SKIP برگرداند."""
    agent = ConcreteAgent()
    agent.enabled = False
    result = asyncio.get_event_loop().run_until_complete(agent.run({}))
    assert result.vote.status == AgentStatus.SKIP
    assert result.vote.score == 50.0


def test_base_agent_error_handling():
    """خطای داخلی Agent باید ERROR برگرداند نه crash."""
    agent = ErrorAgent(name="Error", weight=1.0)
    result = asyncio.get_event_loop().run_until_complete(agent.run({}))
    assert result.vote.status == AgentStatus.ERROR
    assert result.error is not None


# ── Individual Agent Tests ────────────────────────────────────

def test_market_structure_agent_strong_signal(strong_buy_context):
    agent = MarketStructureAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze(strong_buy_context)
    )
    assert vote.score >= 60.0
    assert vote.confidence >= 60.0
    assert vote.direction == "BUY"


def test_market_structure_agent_no_signal():
    agent = MarketStructureAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze({"bos_detected": False, "choch_detected": False})
    )
    assert vote.score <= 30.0


def test_liquidity_agent_sweep(strong_buy_context):
    agent = LiquidityAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze(strong_buy_context)
    )
    assert vote.score >= 50.0
    assert vote.confidence >= 60.0


def test_liquidity_agent_no_sweep():
    agent = LiquidityAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze({"liquidity_sweep": False, "direction": "BUY"})
    )
    assert vote.score <= 50.0


def test_smc_agent_full_confluence(strong_buy_context):
    agent = SMCAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze(strong_buy_context)
    )
    assert vote.score >= 65.0
    assert vote.metadata.get("confluence", 0) >= 2


def test_ai_prediction_agent_with_model(strong_buy_context):
    agent = AIPredictionAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze(strong_buy_context)
    )
    assert vote.score >= 70.0
    assert vote.metadata["model_available"] is True


def test_ai_prediction_agent_no_model():
    agent = AIPredictionAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze({"ai_prediction": {}, "decision_score": 60.0, "direction": "BUY"})
    )
    assert vote.status == AgentStatus.WARNING
    assert vote.metadata["model_available"] is False


def test_risk_agent_ok(strong_buy_context):
    agent = RiskAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze(strong_buy_context)
    )
    assert vote.score > 0.0
    assert vote.status == AgentStatus.OK
    assert vote.metadata["blocked"] is False


def test_risk_agent_blocked_portfolio(blocked_risk_context):
    agent = RiskAgent(max_portfolio_risk=5.0)
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze(blocked_risk_context)
    )
    assert vote.score == 0.0
    assert vote.status == AgentStatus.ERROR
    assert vote.metadata["blocked"] is True


def test_risk_agent_blocked_daily_limit():
    agent = RiskAgent()
    ctx = {
        "portfolio_risk_percent": 1.0,
        "spread_ratio": 1.0, "atr_normalized": 1.0,
        "daily_trades_count": 5, "max_daily_trades": 5,
        "daily_loss_percent": 0.0, "max_daily_loss_percent": 3.0,
        "consecutive_losses": 0,
    }
    vote = asyncio.get_event_loop().run_until_complete(agent.analyze(ctx))
    assert vote.score == 0.0
    assert vote.metadata["blocked"] is True


def test_news_agent_clear():
    agent = NewsAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze({"news_filter_enabled": True, "upcoming_news": [], "direction": "BUY"})
    )
    assert vote.score >= 80.0
    assert vote.metadata["blocked"] is False


def test_news_agent_high_impact_block():
    agent = NewsAgent(block_on_high_impact=True, minutes_before=30)
    ctx = {
        "news_filter_enabled": True,
        "direction": "BUY",
        "upcoming_news": [
            {"name": "NFP", "impact": "HIGH", "minutes_to_event": 10, "minutes_since_event": 999}
        ],
    }
    vote = asyncio.get_event_loop().run_until_complete(agent.analyze(ctx))
    assert vote.metadata["blocked"] is True
    assert vote.score == 0.0


def test_news_agent_filter_disabled():
    agent = NewsAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze({"news_filter_enabled": False})
    )
    assert vote.score == 80.0
    assert vote.metadata["filter_active"] is False


def test_execution_agent_signal_only():
    agent = ExecutionAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze({"trading_mode": "SIGNAL_ONLY", "direction": "BUY"})
    )
    assert vote.score == 75.0
    assert "signal-only" in vote.reason.lower()


def test_execution_agent_london_session(strong_buy_context):
    agent = ExecutionAgent()
    vote = asyncio.get_event_loop().run_until_complete(
        agent.analyze(strong_buy_context)
    )
    assert vote.score >= 60.0


# ── VotingEngine Tests ────────────────────────────────────────

def make_engine(threshold=65.0):
    agents = [
        MarketStructureAgent(weight=0.20),
        LiquidityAgent(weight=0.15),
        SMCAgent(weight=0.20),
        AIPredictionAgent(weight=0.20),
        RiskAgent(weight=0.15),
        NewsAgent(weight=0.10),
        ExecutionAgent(weight=0.10),
    ]
    return VotingEngine(agents=agents, min_score_threshold=threshold)


def test_voting_engine_buy_decision(strong_buy_context):
    engine = make_engine()
    result = asyncio.get_event_loop().run_until_complete(
        engine.vote(strong_buy_context)
    )
    assert result.decision in (TradeDecision.BUY, TradeDecision.NO_TRADE)
    assert result.final_score >= 0.0
    assert len(result.agent_results) == 7
    assert len(result.votes_summary) == 7


def test_voting_engine_blocked(blocked_risk_context):
    engine = make_engine()
    result = asyncio.get_event_loop().run_until_complete(
        engine.vote(blocked_risk_context)
    )
    assert result.decision == TradeDecision.BLOCKED
    assert "Risk" in result.blocking_agents


def test_voting_engine_no_trade(no_trade_context):
    engine = make_engine(threshold=65.0)
    result = asyncio.get_event_loop().run_until_complete(
        engine.vote(no_trade_context)
    )
    assert result.decision == TradeDecision.NO_TRADE


def test_voting_engine_weight_update(strong_buy_context):
    engine = make_engine()
    engine.update_weights({"Market Structure": 0.30, "SMC": 0.25})
    weights = engine.get_weights()
    assert weights["Market Structure"] == 0.30
    assert weights["SMC"] == 0.25


def test_voting_engine_disable_agent(strong_buy_context):
    engine = make_engine()
    engine.disable_agent("News")
    result = asyncio.get_event_loop().run_until_complete(
        engine.vote(strong_buy_context)
    )
    # News Agent باید SKIP باشد
    news_result = next(r for r in result.agent_results if r.agent_name == "News")
    assert news_result.vote.status == AgentStatus.SKIP


def test_vote_result_to_dict(strong_buy_context):
    engine = make_engine()
    result = asyncio.get_event_loop().run_until_complete(
        engine.vote(strong_buy_context)
    )
    d = result.to_dict()
    assert "decision" in d
    assert "final_score" in d
    assert "votes" in d
    assert len(d["votes"]) == 7


# ── AgentService Tests ────────────────────────────────────────

def test_agent_service_evaluate(strong_buy_context):
    reset_agent_service()
    service = AgentService()
    result = asyncio.get_event_loop().run_until_complete(
        service.evaluate(strong_buy_context)
    )
    assert result.decision in TradeDecision.__members__.values()
    assert 0.0 <= result.final_score <= 100.0


def test_agent_service_get_weights():
    service = AgentService()
    weights = service.get_agent_weights()
    assert len(weights) == 7
    assert "Market Structure" in weights
    assert "Risk" in weights


def test_agent_service_update_threshold():
    service = AgentService(min_score_threshold=70.0)
    service.set_threshold(80.0)
    assert service.voting_engine.min_score_threshold == 80.0


def test_agent_service_agent_names():
    service = AgentService()
    names = service.get_agent_names()
    expected = ["Market Structure", "Liquidity", "SMC",
                "AI Prediction", "Risk", "News", "Execution"]
    assert names == expected
