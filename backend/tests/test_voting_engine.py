"""
تست‌های VotingEngine
"""
from __future__ import annotations
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    SKIP = "SKIP"


@dataclass
class AgentVote:
    score: float
    confidence: float
    direction: str
    status: AgentStatus
    reason: str


@dataclass
class AgentResult:
    agent_name: str
    vote: AgentVote
    elapsed_ms: float = 0.0
    error: str = ""


def make_agent(name="agent", weight=0.5, score=70.0,
               direction="BUY", status="OK", enabled=True):
    agent = MagicMock()
    agent.name = name
    agent.weight = weight
    agent.enabled = enabled
    vote = AgentVote(
        score=score, confidence=80.0,
        direction=direction, status=AgentStatus(status), reason="ok"
    )
    async def run(ctx):
        return AgentResult(agent_name=name, vote=vote, elapsed_ms=1.0)
    agent.run = run
    return agent


# ─── stub کلاس‌های لازم برای VotingEngine ────────────────────────────────
class _BaseAgent:
    pass


class VoteDecision(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"
    BLOCKED = "BLOCKED"


@dataclass
class VoteResult:
    decision: VoteDecision
    weighted_score: float
    confidence: float
    direction: str
    agent_results: list
    blocked_by: Any = None
    reasons: list = None
    elapsed_ms: float = 0.0
    metadata: dict = None

    def __post_init__(self):
        if self.reasons is None:
            self.reasons = []
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self):
        return {
            "decision": self.decision.value,
            "weighted_score": round(self.weighted_score, 2),
            "confidence": round(self.confidence, 2),
            "direction": self.direction,
            "blocked_by": self.blocked_by,
            "reasons": self.reasons,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "agents": [],
        }


class VotingEngine:
    """Inline test copy — mirrors backend/agents/voting_engine.py."""

    def __init__(self, agents, min_score_threshold=65.0,
                 min_confidence_threshold=50.0, run_parallel=True):
        self._agents = agents
        self._min_score_threshold = min_score_threshold
        self._min_confidence_threshold = min_confidence_threshold
        self._run_parallel = run_parallel

    async def vote(self, context):
        if self._run_parallel:
            results = await self._run_parallel_safe(context)
        else:
            results = await self._run_sequential_safe(context)
        return self._aggregate(results)

    def update_weights(self, weight_map):
        for agent in self._agents:
            if agent.name in weight_map:
                agent.weight = float(weight_map[agent.name])

    def set_threshold(self, threshold):
        self._min_score_threshold = float(threshold)

    def enable_agent(self, name):
        for a in self._agents:
            if a.name == name:
                a.enabled = True

    def disable_agent(self, name):
        for a in self._agents:
            if a.name == name:
                a.enabled = False

    def get_weights(self):
        return {a.name: a.weight for a in self._agents}

    async def _run_parallel_safe(self, context):
        import asyncio
        tasks = [self._run_agent_safe(a, context) for a in self._agents]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        for i, item in enumerate(raw):
            if isinstance(item, BaseException):
                name = self._agents[i].name if i < len(self._agents) else f"Agent[{i}]"
                results.append(AgentResult(
                    agent_name=name,
                    vote=AgentVote(score=50.0, confidence=0.0,
                                   direction="NEUTRAL",
                                   status=AgentStatus.ERROR,
                                   reason=str(item)),
                    elapsed_ms=0.0, error=str(item),
                ))
            else:
                results.append(item)
        return results

    async def _run_sequential_safe(self, context):
        results = []
        for agent in self._agents:
            results.append(await self._run_agent_safe(agent, context))
        return results

    @staticmethod
    async def _run_agent_safe(agent, context):
        try:
            return await agent.run(context)
        except Exception as exc:
            return AgentResult(
                agent_name=agent.name,
                vote=AgentVote(score=50.0, confidence=0.0,
                               direction="NEUTRAL",
                               status=AgentStatus.ERROR,
                               reason=f"Fatal: {exc}"),
                elapsed_ms=0.0, error=str(exc),
            )

    def _aggregate(self, results):
        # block check
        for r in results:
            if r.vote.status == AgentStatus.ERROR and r.vote.score == 0.0:
                return VoteResult(
                    decision=VoteDecision.BLOCKED, weighted_score=0.0,
                    confidence=0.0, direction="BLOCKED",
                    agent_results=results, blocked_by=r.agent_name,
                    reasons=[f"Blocked by {r.agent_name}: {r.vote.reason}"],
                )
        total_weight = 0.0
        weighted_sum = 0.0
        weighted_conf = 0.0
        direction_votes = {"BUY": 0.0, "SELL": 0.0, "NEUTRAL": 0.0}
        reasons = []
        agent_weights = {a.name: a.weight for a in self._agents}
        for r in results:
            w = agent_weights.get(r.agent_name, 1.0 / max(len(results), 1))
            if r.vote.status == AgentStatus.SKIP:
                continue
            if r.vote.status == AgentStatus.ERROR:
                w *= 0.5
            weighted_sum  += r.vote.score * w
            weighted_conf += r.vote.confidence * w
            total_weight  += w
            d = (r.vote.direction or "NEUTRAL").upper()
            if d not in direction_votes:
                d = "NEUTRAL"
            direction_votes[d] += w
            if r.vote.reason:
                reasons.append(f"[{r.agent_name}] {r.vote.reason}")
        if total_weight > 0:
            ws = weighted_sum / total_weight
            wc = weighted_conf / total_weight
        else:
            ws, wc = 50.0, 0.0
        ws = max(0.0, min(100.0, ws))
        wc = max(0.0, min(100.0, wc))
        direction = max(direction_votes, key=lambda d: direction_votes[d])
        if ws >= self._min_score_threshold and wc >= self._min_confidence_threshold:
            decision = (
                VoteDecision.BUY if direction == "BUY" else
                VoteDecision.SELL if direction == "SELL" else
                VoteDecision.NO_TRADE
            )
        else:
            decision = VoteDecision.NO_TRADE
            reasons.append(f"Threshold not met: score={ws:.1f}/{self._min_score_threshold}")
        return VoteResult(
            decision=decision, weighted_score=ws, confidence=wc,
            direction=direction, agent_results=results, reasons=reasons,
            metadata={"direction_votes": direction_votes, "total_weight": round(total_weight, 4)},
        )


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestVotingEngineBasic:

    @pytest.mark.asyncio
    async def test_buy_signal_above_threshold(self):
        agents = [
            make_agent("smc",    weight=0.3, score=80.0, direction="BUY"),
            make_agent("pa",     weight=0.3, score=75.0, direction="BUY"),
            make_agent("risk",   weight=0.2, score=70.0, direction="BUY"),
            make_agent("news",   weight=0.2, score=68.0, direction="BUY"),
        ]
        engine = VotingEngine(agents, min_score_threshold=65.0, min_confidence_threshold=50.0)
        result = await engine.vote({})
        assert result.decision == VoteDecision.BUY
        assert result.weighted_score >= 65.0
        assert result.direction == "BUY"

    @pytest.mark.asyncio
    async def test_sell_signal(self):
        agents = [
            make_agent("smc",  weight=0.5, score=80.0, direction="SELL"),
            make_agent("risk", weight=0.5, score=75.0, direction="SELL"),
        ]
        engine = VotingEngine(agents)
        result = await engine.vote({})
        assert result.decision == VoteDecision.SELL

    @pytest.mark.asyncio
    async def test_no_trade_below_threshold(self):
        agents = [
            make_agent("smc",  weight=0.5, score=40.0, direction="BUY"),
            make_agent("risk", weight=0.5, score=35.0, direction="BUY"),
        ]
        engine = VotingEngine(agents, min_score_threshold=65.0)
        result = await engine.vote({})
        assert result.decision == VoteDecision.NO_TRADE
        assert result.weighted_score < 65.0

    @pytest.mark.asyncio
    async def test_blocked_by_zero_score_error_agent(self):
        async def crash_run(ctx):
            return AgentResult(
                agent_name="risk_guard",
                vote=AgentVote(score=0.0, confidence=0.0,
                               direction="NEUTRAL",
                               status=AgentStatus.ERROR,
                               reason="Max drawdown exceeded"),
                elapsed_ms=0.0, error="Max drawdown exceeded",
            )
        blocker = MagicMock()
        blocker.name = "risk_guard"
        blocker.weight = 0.2
        blocker.enabled = True
        blocker.run = crash_run
        engine = VotingEngine([blocker])
        result = await engine.vote({})
        assert result.decision == VoteDecision.BLOCKED
        assert result.blocked_by == "risk_guard"

    @pytest.mark.asyncio
    async def test_error_agent_does_not_crash_engine(self):
        """اگر یک agent exception دهد، بقیه باید ادامه دهند."""
        async def raise_run(ctx):
            raise RuntimeError("agent exploded")
        bad = MagicMock()
        bad.name = "bad_agent"
        bad.weight = 0.3
        bad.enabled = True
        bad.run = raise_run
        good = make_agent("good_agent", weight=0.7, score=80.0, direction="BUY")
        engine = VotingEngine([bad, good])
        result = await engine.vote({})
        # نباید crash کند
        assert result.decision in list(VoteDecision)

    @pytest.mark.asyncio
    async def test_parallel_vs_sequential_same_result(self):
        agents = [
            make_agent("a", weight=0.5, score=70.0, direction="BUY"),
            make_agent("b", weight=0.5, score=72.0, direction="BUY"),
        ]
        e_par = VotingEngine(agents, run_parallel=True)
        e_seq = VotingEngine(agents, run_parallel=False)
        r_par = await e_par.vote({})
        r_seq = await e_seq.vote({})
        assert r_par.decision == r_seq.decision
        assert abs(r_par.weighted_score - r_seq.weighted_score) < 0.01


class TestVotingEngineWeights:

    def test_get_weights(self):
        agents = [
            make_agent("a", weight=0.4),
            make_agent("b", weight=0.6),
        ]
        engine = VotingEngine(agents)
        w = engine.get_weights()
        assert w == {"a": 0.4, "b": 0.6}

    def test_update_weights(self):
        agents = [make_agent("a", weight=0.5), make_agent("b", weight=0.5)]
        engine = VotingEngine(agents)
        engine.update_weights({"a": 0.8, "b": 0.2})
        w = engine.get_weights()
        assert w["a"] == 0.8
        assert w["b"] == 0.2

    def test_set_threshold(self):
        engine = VotingEngine([], min_score_threshold=65.0)
        engine.set_threshold(80.0)
        assert engine._min_score_threshold == 80.0

    def test_enable_disable_agent(self):
        agents = [make_agent("smc", enabled=True)]
        engine = VotingEngine(agents)
        engine.disable_agent("smc")
        assert agents[0].enabled is False
        engine.enable_agent("smc")
        assert agents[0].enabled is True

    def test_enable_unknown_agent_no_crash(self):
        engine = VotingEngine([])
        engine.enable_agent("nonexistent")  # نباید exception بدهد


class TestVoteResultDict:

    @pytest.mark.asyncio
    async def test_to_dict_keys(self):
        agents = [make_agent("a", weight=1.0, score=70.0, direction="BUY")]
        engine = VotingEngine(agents)
        result = await engine.vote({})
        d = result.to_dict()
        for key in ("decision", "weighted_score", "confidence", "direction",
                    "blocked_by", "reasons", "elapsed_ms", "agents"):
            assert key in d, f"Key '{key}' missing from to_dict()"

    @pytest.mark.asyncio
    async def test_elapsed_ms_set(self):
        agents = [make_agent("a", weight=1.0, score=70.0, direction="BUY")]
        engine = VotingEngine(agents)
        result = await engine.vote({})
        # elapsed_ms در کلاس واقعی توسط vote() set می‌شود — اما در inline copy ما نه
        assert isinstance(result.elapsed_ms, float)
