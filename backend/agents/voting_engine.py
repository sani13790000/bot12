"""Voting Engine - Consensus Decision Making"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum

from .base_agent import AgentVote, AgentResult, AgentStatus

log = logging.getLogger(__name__)


class VotingStrategy(str, Enum):
    """Voting strategies for consensus"""
    WEIGHTED_AVERAGE = "weighted_average"
    MAJORITY = "majority"
    UNANIMOUS = "unanimous"
    WEIGHTED_VETO = "weighted_veto"


@dataclass
class VotingResult:
    """Result of voting process"""
    final_signal: str  # "BUY", "SELL", "HOLD"
    confidence: float
    weighted_score: float
    agent_votes: List[AgentVote] = field(default_factory=list)
    agent_results: List[AgentResult] = field(default_factory=list)
    reasoning: str = ""
    timestamp: float = 0.0


class VotingEngine:
    """
    Consensus voting engine that combines multiple agent signals
    into a single trading decision.
    """
    
    def __init__(self, strategy: VotingStrategy = VotingStrategy.WEIGHTED_AVERAGE):
        self.strategy = strategy
        self.weights: Dict[str, float] = {}
    
    def set_agent_weight(self, agent_id: str, weight: float) -> None:
        """Set weight for an agent"""
        self.weights[agent_id] = max(0, min(1.0, weight))
        log.info(f"Set weight for {agent_id}: {weight}")
    
    async def vote(self, agent_results: List[AgentResult]) -> VotingResult:
        """
        Aggregate agent votes into final decision.
        
        Args:
            agent_results: List of agent analysis results
        
        Returns:
            VotingResult with final decision
        """
        try:
            if not agent_results:
                return VotingResult(
                    final_signal="HOLD",
                    confidence=0.0,
                    weighted_score=0.0,
                    reasoning="No agent results to vote on"
                )
            
            votes = [r.vote for r in agent_results]
            
            # Apply voting strategy
            if self.strategy == VotingStrategy.WEIGHTED_AVERAGE:
                return self._vote_weighted_average(votes, agent_results)
            elif self.strategy == VotingStrategy.MAJORITY:
                return self._vote_majority(votes, agent_results)
            elif self.strategy == VotingStrategy.WEIGHTED_VETO:
                return self._vote_weighted_veto(votes, agent_results)
            else:
                return self._vote_weighted_average(votes, agent_results)
        
        except Exception as e:
            log.error(f"Voting error: {e}")
            return VotingResult(
                final_signal="HOLD",
                confidence=0.0,
                weighted_score=0.0,
                reasoning=f"Voting engine error: {e}"
            )
    
    def _vote_weighted_average(self, votes: List[AgentVote], 
                               results: List[AgentResult]) -> VotingResult:
        """Weighted average voting"""
        
        buy_score = 0.0
        sell_score = 0.0
        hold_score = 0.0
        total_weight = 0.0
        
        # Calculate weighted scores
        for vote, result in zip(votes, results):
            weight = vote.weight
            confidence = vote.confidence
            
            if vote.direction == "BUY":
                buy_score += confidence * weight
            elif vote.direction == "SELL":
                sell_score += confidence * weight
            else:
                hold_score += confidence * weight
            
            total_weight += weight
        
        # Normalize scores
        if total_weight > 0:
            buy_score /= total_weight
            sell_score /= total_weight
            hold_score /= total_weight
        
        # Determine final signal
        max_score = max(buy_score, sell_score, hold_score)
        
        if max_score < 0.5:
            final_signal = "HOLD"
        elif buy_score > sell_score:
            final_signal = "BUY"
        else:
            final_signal = "SELL"
        
        # Build reasoning
        reasoning = self._build_reasoning(votes, final_signal, 
                                         buy_score, sell_score, hold_score)
        
        return VotingResult(
            final_signal=final_signal,
            confidence=max_score,
            weighted_score=max_score,
            agent_votes=votes,
            agent_results=results,
            reasoning=reasoning
        )
    
    def _vote_majority(self, votes: List[AgentVote], 
                       results: List[AgentResult]) -> VotingResult:
        """Simple majority voting"""
        
        buy_count = sum(1 for v in votes if v.direction == "BUY")
        sell_count = sum(1 for v in votes if v.direction == "SELL")
        total = len(votes)
        
        confidence = max(buy_count, sell_count) / total if total > 0 else 0
        
        if buy_count > sell_count:
            final_signal = "BUY"
        elif sell_count > buy_count:
            final_signal = "SELL"
        else:
            final_signal = "HOLD"
        
        reasoning = f"Majority vote: {buy_count} BUY, {sell_count} SELL out of {total} agents"
        
        return VotingResult(
            final_signal=final_signal,
            confidence=confidence,
            weighted_score=confidence,
            agent_votes=votes,
            agent_results=results,
            reasoning=reasoning
        )
    
    def _vote_weighted_veto(self, votes: List[AgentVote], 
                            results: List[AgentResult]) -> VotingResult:
        """Weighted voting with veto power"""
        
        # Check for veto
        for vote in votes:
            if vote.status == AgentStatus.VETO:
                return VotingResult(
                    final_signal="HOLD",
                    confidence=0.9,
                    weighted_score=0.9,
                    agent_votes=votes,
                    agent_results=results,
                    reasoning=f"Agent {vote.agent_id} issued VETO"
                )
        
        # Otherwise use weighted average
        return self._vote_weighted_average(votes, results)
    
    def _build_reasoning(self, votes: List[AgentVote], signal: str,
                        buy_score: float, sell_score: float, 
                        hold_score: float) -> str:
        """Build detailed reasoning for decision"""
        
        agent_reasons = [v.reason for v in votes if v.reason]
        
        reasoning = f"Signal: {signal} | "
        reasoning += f"Scores - BUY: {buy_score:.2f}, SELL: {sell_score:.2f}, HOLD: {hold_score:.2f} | "
        reasoning += f"Agents: {', '.join(agent_reasons[:3])}"
        
        return reasoning
    
    def get_status(self) -> Dict[str, Any]:
        """Get voting engine status"""
        return {
            "strategy": self.strategy.value,
            "agent_weights": self.weights,
            "status": "operational"
        }
