"""
backend/agents/voting_engine.py
Galaxy Vast AI — Enterprise Voting Engine

Coordinates all agents, collects votes, applies weighted majority,
veto rules, tie-breaking, and circuit breaker integration.
FIX: Import AgentStatus, AgentResult, VoteResult from base_agent (not core modules).
MS-4: Sequential fallback when gather fails.
MS-5: Per-agent error isolation (gather return_exceptions=True).
Note: results lists are bounded to MAX_AGENTS_SOFT_LIMIT.
"""