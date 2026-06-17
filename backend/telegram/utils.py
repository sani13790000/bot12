"""
توابع کمکی ربات تلگرام

نویسنده: MT5 Trading Team
"""

from datetime import datetime
from typing import Dict, Any, Optional


def format_welcome_message(username: str) -> str:
    """
    فرمت پیام خوش‌آمدگویی
    """
    return f"""
👋 سلام <b>{username}</b>!

🎮 به ربات معاملاتی MT5 خوش آمدید.

📊 <b>امکانات:</b>
• تحلیل市場 SMC و Price Action
• سیگنال‌های خرید و فروش
• مدیریت معاملات
• گزارش‌های جامع

⚠️ <b>حداقل امتیاز ورود:</b> 65 از 100

🚀 برای شروع از منوی زیر استفاده کنید.
"""


def format_analysis_result(result: Dict[str, Any]) -> str:
    """
    فرمت نتیجه تحلیل
    """
    smc = result.get("smc", {})
    pa = result.get("price_action", {})
    decision = result.get("decision", {})

    symbol = decision.get("symbol", "---")
    timeframe = decision.get("timeframe", "---")
    direction = decision.get("direction", "neutral")
    score = decision.get("total_score", 0)
    entry_allowed = decision.get("entry_allowed", False)

    direction_emoji = "🟢 خرید" if direction == "buy" else "🔴 فروش" if direction == "sell" else "⚪ خنثی"
    entry_emoji = "✅" if entry_allowed else "❌"

    text = f"""
📊 <b>تحلیل جامع</b>
<b>{symbol}</b> | {timeframe}

{'='*30}

🎯 <b>تصمیم:</b>
• جهت: {direction_emoji}
• امتیاز: <b>{score:.0f}/100</b>
• مجاز ورود: {entry_emoji}

"""

    # SMC بخش
    if smc:
        structure = smc.get("structure", {})
        text += f"""
📈 <b>SMC:</b>
• ساختار: {structure.get('trend', 'نامشخص')}
• BOS: {'✅' if structure.get('bos') else '❌'}
• CHOCH: {'✅' if structure.get('choch') else '❌'}
"""

        liquidity = smc.get("liquidity", {})
        if liquidity:
            text += f"• لیکوییدیتی: {liquidity.get('type', '---')}\n"

    # Price Action بخش
    if pa:
        patterns = pa.get("patterns", [])
        if patterns:
            text += f"\n📉 <b>Price Action:</b>\n"
            for p in patterns[:3]:
                text += f"• {p.get('name', '---')}: {p.get('bias', '---')}\n"

    # سطوح
    levels = decision.get("levels", {})
    if levels:
        text += f"""
📍 <b>سطوح:</b>
• ورود: {levels.get('entry', '---')}
• حد سود: {levels.get('tp', '---')}
• حد ضرر: {levels.get('sl', '---')}
"""

    # فیلترها
    filters = decision.get("filters_passed", [])
    if filters:
        text += "\n✅ <b>فیلترهای رد شده:</b>\n"
        for f in filters:
            text += f"• {f}\n"

    return text


def format_trade_list(trades: list, title: str = "معاملات") -> str:
    """
    فرمت لیست معاملات
    """
    if not trades:
        return f"📭 <b>{title}</b>\n\nهیچ معامله‌ای یافت نشد."

    text = f"📋 <b>{title}</b>\n\n"

    for trade in trades[:10]:
        symbol = trade.get("symbol", "---")
        direction = trade.get("direction", "---")
        profit = trade.get("profit_money", 0) or 0
        status = trade.get("status", "---")

        dir_emoji = "🟢" if direction == "buy" else "🔴"
        profit_emoji = "💰" if profit >= 0 else "📉"

        text += f"{dir_emoji} <b>{symbol}</b> | {profit_emoji} ${profit:.2f}\n"

    return text


def format_trade_detail(trade: Dict[str, Any]) -> str:
    """
    فرمت جزئیات معامله
    """
    symbol = trade.get("symbol", "---")
    direction = trade.get("direction", "---")
    status = trade.get("status", "---")

    volume = trade.get("volume", 0)
    entry_price = trade.get("entry_price", 0)
    current_price = trade.get("current_price", 0)
    profit = trade.get("profit_money", 0) or 0
    sl = trade.get("stop_loss", 0) or "---"
    tp = trade.get("take_profit", 0) or "---"

    opened_at = trade.get("opened_at", "---")
    closed_at = trade.get("closed_at", "---")

    dir_emoji = "🟢 خرید" if direction == "buy" else "🔴 فروش"
    profit_emoji = "💰" if profit >= 0 else "📉"

    text = f"""
📊 <b>جزئیات معامله</b>

📈 <b>{symbol}</b> | {dir_emoji}
وضعیت: {status}

📍 <b>اطلاعات:</b>
• حجم: {volume}
• قیمت ورود: {entry_price}
• قیمت فعلی: {current_price}
• حد ضرر: {sl}
• حد سود: {tp}

{profit_emoji} <b>سود/ضرر:</b> ${profit:.2f}

📅 <b>زمان:</b>
• باز شده: {opened_at}
• {'بسته شده: ' + closed_at if closed_at != '---' else ''}
"""
    return text


def format_signal_card(signal: Dict[str, Any]) -> str:
    """
    فرمت کارت سیگنال
    """
    symbol = signal.get("symbol", "---")
    direction = signal.get("direction", "---")
    score = signal.get("total_score", 0)

    entry = signal.get("entry_price", "---")
    sl = signal.get("stop_loss", "---")
    tp = signal.get("take_profit", "---")

    valid_until = signal.get("valid_until", "---")

    dir_emoji = "🟢 خرید" if direction == "buy" else "🔴 فروش"
    score_emoji = "⭐" * min(5, int(score / 20))

    text = f"""
🔔 <b>سیگنال جدید</b>

📈 <b>{symbol}</b> | {dir_emoji}
امتیاز: {score:.0f}/100 {score_emoji}

📍 <b>سطوح:</b>
• ورود: {entry}
• حد سود: {tp}
• حد ضرر: {sl}

⏰ اعتبار تا: {valid_until}
"""
    return text


def format_report_summary(report: Dict[str, Any]) -> str:
    """
    فرمت خلاصه گزارش
    """
    summary = report.get("summary", {})

    total_trades = summary.get("total_trades", 0)
    win_rate = summary.get("win_rate", 0)
    net_profit = summary.get("net_profit", 0)

    profit_emoji = "✅" if net_profit >= 0 else "📉"
    status = "سودده" if net_profit >= 0 else "زیان‌ده"

    text = f"""
📊 <b>خلاصه گزارش</b>

• معاملات: {total_trades}
• وین ریت: {win_rate:.1f}%
• سود/ضرر: ${net_profit:.2f}

{profit_emoji} وضعیت: {status}
"""
    return text


def format_error_message(error_type: str, details: str = "") -> str:
    """
    فرمت پیام خطا
    """
    messages = {
        "server": "❌ خطا در ارتباط با سرور",
        "not_found": "❌ اطلاعات یافت نشد",
        "unauthorized": "❌ دسترسی غیرمجاز",
        "validation": "❌ اطلاعات وارد شده نامعتبر است",
        "unknown": "❌ خطای ناشناخته رخ داد"
    }

    text = messages.get(error_type, messages["unknown"])

    if details:
        text += f"\n\n<i>{details}</i>"

    return text


def escape_html(text: str) -> str:
    """
    فرار از کاراکترهای HTML
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
