"""
backend/telegram/handlers/intelligence.py
Galaxy Vast AI — Intelligence & Learning Telegram Handlers

Commands:
    /learning   -- show learning memory stats
    /weights    -- show Decision Engine weights
    /run_learning -- run learning cycle manually (ADMIN)
"""
from __future__ import annotations

import logging

from aiogram import Router, types

from ...core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = Router()

_learning_service = None


def set_learning_service(service) -> None:
    """Inject LearningService from outside."""
    global _learning_service
    _learning_service = service


@router.message(commands=["learning"])
@require_permission(Permission.USER)
async def cmd_learning_stats(message: types.Message) -> None:
    """Show learning memory stats."""
    if _learning_service is None:
        await message.answer("Learning service not active.")
        return
    try:
        stats = await _learning_service.get_stats()
    except Exception as exc:
        logger.error("Learning stats error: %s", exc)
        await message.answer("Error fetching learning stats.")
        return
    lines = [
        "Learning Memory Stats",
        f"Total trades: {stats.get('total_trades', 0)}",
        f"Wins: {stats.get('wins', 0)}",
        f"Losses: {stats.get('losses', 0)}",
        f"Win rate: {stats.get('win_rate', 0):.1%}",
        f"Avg R:R: {stats.get('avg_rr', 0):.2f}",
        f"Consecutive losses: {stats.get('consecutive_losses', 0)}",
    ]
    await message.answer("\n".join(lines))


@router.message(commands=["weights"])
@require_permission(Permission.TRADER)
async def cmd_decision_weights(message: types.Message) -> None:
    """Show Decision Engine weights."""
    if _learning_service is None:
        await message.answer("Learning service not active.")
        return
    try:
        w = await _learning_service.get_weights()
    except Exception as exc:
        logger.error("Get weights error: %s", exc)
        await message.answer("Error fetching weights.")
        return
    lines = [
        "Decision Engine Weights",
        f"SMC Engine: {w.get('smc_weight', 0):.1%}",
        f"Price Action: {w.get('price_action_weight', 0):.1%}",
        f"HTF Alignment: {w.get('htf_alignment_weight', 0):.1%}",
        f"Session Filter: {w.get('session_weight', 0):.1%}",
        f"LTF Filter: {w.get('ltf_weight', 0):.1%}",
    ]
    await message.answer("\n".join(lines))


@router.message(commands=["run_learning"])
@require_permission(Permission.ADMIN)
async def cmd_run_learning(message: types.Message) -> None:
    """Run learning cycle manually (ADMIN only)."""
    if _learning_service is None:
        await message.answer("Learning service not active.")
        return
    await message.answer("Running learning cycle...")
    try:
        result = await _learning_service.run_learning_cycle()
    except Exception as exc:
        logger.error("Learning cycle error: %s", exc)
        await message.answer(f"Error: {exc}")
        return
    lines = [
        "Learning cycle complete",
        f"Trades analysed: {getattr(result, 'trades_analyzed', 0)}",
        f"Valid losses: {getattr(result, 'valid_losses', 0)}",
        f"Rule violations: {getattr(result, 'rule_violations', 0)}",
        f"ML retrained: {getattr(result, 'ml_retrained', False)}",
    ]
    await message.answer("\n".join(lines))
