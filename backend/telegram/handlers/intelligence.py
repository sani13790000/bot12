"""
backend/telegram/handlers/intelligence.py
Galaxy Vast AI - Intelligence and Learning Telegram Handlers

Commands: /memory_stats /run_learning /weight_report /violation_log
"""
from __future__ import annotations

import logging

from aiogram import Dispatcher, Router, types
from aiogram.filters import Command

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("memory_stats"))
async def cmd_memory_stats(message: types.Message) -> None:
    try:
        from backend.intelligence.learning_service import LearningService
        stats = LearningService().get_memory_stats()
        lines = [
            "*Galaxy Vast - حافظه یادگیری*", "━━━━━━━━━━━━━━━━━━━━━━",
            f"کل معاملات: `{stats['total_trades']}`",
            f"برنده‌ها: `{stats['wins']}`",
            f"بازنده‌ها: `{stats['losses']}`",
            f"وین ریت: `{stats['win_rate']:.1f}%`",
            f"اندازه حافظه: `{stats['memory_size']}` ورودی",
        ]
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        logger.error("memory_stats error: %s", exc)
        await message.answer(f"خطا: {exc}")


@router.message(Command("run_learning"))
async def cmd_run_learning(message: types.Message) -> None:
    if not getattr(message.bot, "_user_data", {}).get("is_admin"):
        await message.answer("این دستور فقط برای مدیران است")
        return
    await message.answer("در حال اجرای چرخه یادگیری...")
    try:
        from backend.intelligence.learning_service import LearningService
        result = await LearningService().run_learning_cycle()
        lines = [
            "*چرخه یادگیری تکمیل شد*", "━━━━━━━━━━━━━━━━━━━━━━",
            f"معاملات پردازش‌شده: `{result.trades_processed}`",
            f"وزن‌های بروز شده: `{len(result.weight_updates)}`",
            f"زمان پردازش: `{result.duration_ms:.0f}ms`",
        ]
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        await message.answer(f"خطا: {exc}")


@router.message(Command("weight_report"))
async def cmd_weight_report(message: types.Message) -> None:
    try:
        from backend.intelligence.learning_service import LearningService
        weights = LearningService().get_factor_weights()
        lines   = ["*وزن عوامل*", "━━━━━━━━━━━━━━━━━━━━━━"]
        for factor, weight in sorted(weights.items(), key=lambda x: -x[1]):
            lines.append(f"`{factor:<20s}` {'█' * int(weight*10)} `{weight:.3f}`")
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        await message.answer(f"خطا: {exc}")


@router.message(Command("violation_log"))
async def cmd_violation_log(message: types.Message) -> None:
    try:
        from backend.intelligence.learning_service import LearningService
        violations = LearningService().get_recent_violations(limit=10)
        if not violations:
            await message.answer("هیچ نقضی در ۲۴ ساعت اخیر ثبت نشده")
            return
        lines = ["*نقض‌های اخیر*", "━━━━━━━━━━━━━━━━━━━━━━"]
        for v in violations:
            lines.append(f"- `{v['rule']}` {v['symbol']} {v['severity']}")
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        await message.answer(f"خطا: {exc}")


def register(dp: Dispatcher) -> None:
    dp.include_router(router)
