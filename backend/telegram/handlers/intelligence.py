"""
backend/telegram/handlers/intelligence.py
Galaxy Vast AI — Intelligence Handlers
"""
from __future__ import annotations
import logging
from typing import Any, Dict
logger = logging.getLogger(__name__)
async def cmd_learning_report(message,ml_state):
    cycles=ml_state.get("cycles_completed",0)
    acc=ml_state.get("last_accuracy",0.0)
    drift=ml_state.get("drift_score",0.0)
    text=("\U0001f9e0 *Learning Report*\n\n"
          f"Cycles: {cycles}\nAccuracy: {acc:.1%}\nDrift: {drift:.3f}")
    try: await message.answer(text,parse_mode="Markdown")
    except Exception as e: logger.error("learning_report: %s",e)
async def cmd_weights(message,weights):
    lines=["\U0001f9e0 *Weights*\n"]+[f"`{k}`: {v:.3f}" for k,v in weights.items()]
    try: await message.answer("\n".join(lines),parse_mode="Markdown")
    except Exception as e: logger.error("weights: %s",e)
