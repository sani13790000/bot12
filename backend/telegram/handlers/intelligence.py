"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Intelligence Telegram Handler

دستورات:
  /learning_report ← گزارش چرخه یادگیری
  /weights         ← وزن‌های فعلی Decision Engine
  /memory_stats    ← آمار حافظه معاملاتی
  /run_learning    ← اجرای چرخه یادگیری (ADMIN+)
"""

from aiogram import Dispatcher, types
from aiogram.filters import Command

from ..rbac import require_permission, Permission
from ..auth import get_user_id
from ...intelligence.learning_service import LearningService
from ...core.logger import get_logger

logger = get_logger("telegram.handlers.intelligence")

# ─── Dependency ─────────────────────────────────────────────────
_learning_service: LearningService | None = None


def set_learning_service(service: LearningService) -> None:
    """تنظیم LearningService از خارج"""
    global _learning_service
    _learning_service = service


def _get_service() -> LearningService:
    global _learning_service
    if _learning_service is None:
        _learning_service = LearningService(model_dir="models")
    return _learning_service


# ─── Handlers ───────────────────────────────────────────────────

@require_permission(Permission.VIEW_REPORTS)
async def cmd_memory_stats(message: types.Message) -> None:
    """
    نمایش آمار حافظه معاملاتی.
    """
    service = _get_service()
    stats = service.get_memory_stats()

    text = (
        "🧠 *Galaxy Vast — حافظه یادگیری*
"
        "━━━━━━━━━━━━━━━━━━━━━━

"
        f"📊 *کل معاملات:* `{stats['total_trades']}`
"
        f"✅ *برنده‌ها:* `{stats['wins']}`
"
        f"❌ *بازنده‌ها:* `{stats['losses']}`
"
        f"🎯 *نرخ برنده:* `{stats['win_rate']:.1%}`
"
        f"📈 *میانگین R:R:* `{stats['avg_rr']:.2f}`
"
        f"🔴 *زیان‌های متوالی:* `{stats['consecutive_losses']}`
"
        f"💾 *حافظه:* `{stats['memory_usage']}`

"
        "━━━━━━━━━━━━━━━━━━━━━━
"
        "_Galaxy Vast AI Engine_"
    )
    await message.answer(text, parse_mode="Markdown")


@require_permission(Permission.VIEW_REPORTS)
async def cmd_weights(message: types.Message) -> None:
    """
    نمایش وزن‌های فعلی Decision Engine.
    """
    service = _get_service()
    weights = service.get_current_weights()
    w = weights.to_dict()

    text = (
        "⚖️ *Galaxy Vast — وزن‌های Decision Engine*
"
        "━━━━━━━━━━━━━━━━━━━━━━

"
        "*وزن‌های اصلی:*
"
        f"  🔵 SMC Engine: `{w['smc_weight']:.1%}`
"
        f"  🟢 Price Action: `{w['price_action_weight']:.1%}`
"
        f"  🟡 HTF Alignment: `{w['htf_alignment_weight']:.1%}`
"
        f"  🟠 Session Filter: `{w['session_weight']:.1%}`
"
        f"  🔴 LTF Filter: `{w['ltf_weight']:.1%}`

"
        "*وزن‌های SMC:*
"
        f"  • BOS: `{w['bos_weight']:.1%}`
"
        f"  • Order Block: `{w['order_block_weight']:.1%}`
"
        f"  • FVG: `{w['fvg_weight']:.1%}`
"
        f"  • Liquidity: `{w['liquidity_weight']:.1%}`
"
        f"  • Structure: `{w['structure_weight']:.1%}`

"
        "━━━━━━━━━━━━━━━━━━━━━━
"
        "_وزن‌ها به صورت خودکار بر اساس عملکرد تنظیم می‌شوند_
"
        "_Galaxy Vast AI Engine_"
    )
    await message.answer(text, parse_mode="Markdown")


@require_permission(Permission.ADMIN)
async def cmd_run_learning(message: types.Message) -> None:
    """
    اجرای چرخه کامل یادگیری به صورت دستی.
    فقط ADMIN+
    """
    await message.answer(
        "🔄 *چرخه یادگیری شروع شد...*
"
        "_لطفاً چند لحظه صبر کنید_",
        parse_mode="Markdown"
    )

    service = _get_service()
    result = await service.run_full_learning_cycle()

    ml_icon = "✅" if result.ml_retrained else "⏸"
    weight_icon = "✅" if result.weights_adjusted else "⏸"

    weight_text = ""
    if result.weight_updates:
        lines = []
        for u in result.weight_updates[:5]:
            sign = "+" if u.delta > 0 else ""
            lines.append(f"  • {u.factor}: `{sign}{u.delta:.3f}`")
        weight_text = "
*تغییرات وزن:*
" + "
".join(lines) + "
"

    violation_text = ""
    if result.top_violation_types:
        violation_text = (
            "
*رایج‌ترین نقض‌ها:*
"
            + "
".join(f"  ⚠️ `{v}`" for v in result.top_violation_types)
            + "
"
        )

    text = (
        "🧠 *Galaxy Vast — نتیجه چرخه یادگیری*
"
        "━━━━━━━━━━━━━━━━━━━━━━

"
        f"📊 *معاملات تحلیل‌شده:* `{result.trades_analyzed}`
"
        f"✅ *زیان‌های معتبر:* `{result.valid_losses}`
"
        f"❌ *نقض قوانین:* `{result.rule_violations}`
"
        f"🤖 *ML بازآموزی:* {ml_icon}
"
        f"⚖️ *وزن‌ها تنظیم:* {weight_icon}
"
        f"{weight_text}"
        f"{violation_text}"
        "━━━━━━━━━━━━━━━━━━━━━━
"
        "_Galaxy Vast AI Engine_"
    )
    await message.answer(text, parse_mode="Markdown")


def register_intelligence_handlers(dp: Dispatcher) -> None:
    """
    ثبت همه هندلرهای intelligence در Dispatcher.
    """
    dp.message.register(cmd_memory_stats, Command("memory_stats"))
    dp.message.register(cmd_weights, Command("weights"))
    dp.message.register(cmd_run_learning, Command("run_learning"))
    logger.info("Intelligence handlers ثبت شدند (3 دستور)")
