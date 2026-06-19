"""Smoke tests for the voting engine."""
from __future__ import annotations

import importlib


def test_voting_engine_importable() -> None:
    """VotingEngine must be importable without side effects."""
    mod = importlib.import_module("backend.agents.voting_engine")
    assert hasattr(mod, "VotingEngine")


def test_voting_engine_has_vote_method() -> None:
    from backend.agents.voting_engine import VotingEngine

    engine = VotingEngine.__new__(VotingEngine)
    assert callable(getattr(engine, "get_consensus", None)) or callable(
        getattr(engine, "vote", None)
    ), "VotingEngine must have a vote/get_consensus method"
