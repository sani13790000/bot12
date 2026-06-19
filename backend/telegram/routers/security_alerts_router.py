"""
backend/telegram/routers/security_alerts_router.py
Phase-9 Telegram Security Commands

Commands (admin-only):
  /security  -- current score + dimensions
  /score     -- alias
  /threats   -- last 10 anomalies
  /blocked   -- blocked IPs
  /report    -- trigger manual report
"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

log = logging.getLogger(__name__)
router = Router(name="security_alerts")


@router.message(Command("security", "score"))
async def cmd_security(msg: Message) -> None:
    is_admin: bool = getattr(getattr(msg, "from_user", None), "_is_admin", False)
    if not is_admin:
        await msg.answer("Access denied.")
        return
    try:
        from backend.security_reporting.security_score_engine import security_score_engine
        snap = security_score_engine.current()
        if snap is None:
            await msg.answer("Score not computed yet. Try again in 30s.")
            return
        level_emoji = {"secure": "\U0001f7e2", "moderate": "\U0001f7e1", "high_risk": "\U0001f7e0", "critical": "\U0001f534"}
        trend_emoji = {"improving": "\U0001f4c8", "stable": "\u27a1\ufe0f", "degrading": "\U0001f4c9"}
        em    = level_emoji.get(snap.level.value, "?")
        trend = trend_emoji.get(snap.trend, "->")
        lines = [
            f"{em} *Security Score: {snap.score:.1f}/100*",
            f"Level: `{snap.level.value.upper()}` | Trend: {trend} `{snap.trend}`",
            "",
            "*Dimensions:*",
        ]
        for d in sorted(snap.dimensions, key=lambda x: x.weighted, reverse=True):
            bar = "\u2588" * int(d.score * 10) + "\u2591" * (10 - int(d.score * 10))
            lines.append(f"  `{d.name[:16]:<16}` {bar} `{d.score*100:.0f}%`")
        if snap.top_risks:
            lines += ["", "*Top risks:*"] + [f"  * {r}" for r in snap.top_risks[:4]]
        delta = f" (delta-1h: `{snap.delta_1h:+.1f}`)" if snap.delta_1h is not None else ""
        lines.append(f"\n_{snap.timestamp.strftime('%Y-%m-%d %H:%M')} UTC{delta}_")
        await msg.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        log.error("cmd_security: %s", exc)
        await msg.answer(f"Error: {exc}")


@router.message(Command("threats"))
async def cmd_threats(msg: Message) -> None:
    is_admin: bool = getattr(getattr(msg, "from_user", None), "_is_admin", False)
    if not is_admin:
        await msg.answer("Access denied.")
        return
    try:
        from backend.institutional.data_store import data_store
        rows = await data_store.query(
            "SELECT ip_address,user_id,risk_level,anomaly_score,event_type,self_heal_action,created_at "
            "FROM security_ai_analysis ORDER BY created_at DESC LIMIT 10"
        )
        if not rows:
            await msg.answer("No anomalies detected recently.")
            return
        level_emoji = {"critical": "\U0001f534", "high": "\U0001f7e0", "medium": "\U0001f7e1", "low": "\U0001f7e2"}
        lines = ["\U0001f6a8 *Last 10 Anomalies:*", ""]
        for r in rows:
            em  = level_emoji.get(r.get("risk_level", "low"), "\u26aa")
            ip  = r.get("ip_address", "?")
            lvl = r.get("risk_level", "?")
            sc  = r.get("anomaly_score", 0.0)
            act = r.get("self_heal_action") or "monitor"
            ts  = r.get("created_at", "")
            if hasattr(ts, "strftime"): ts = ts.strftime("%m-%d %H:%M")
            lines.append(f"{em} `{ip}` [{lvl}] score:`{sc:.3f}` -> {act} _{ts}_")
        await msg.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        log.error("cmd_threats: %s", exc)
        await msg.answer(f"Error: {exc}")


@router.message(Command("blocked"))
async def cmd_blocked(msg: Message) -> None:
    is_admin: bool = getattr(getattr(msg, "from_user", None), "_is_admin", False)
    if not is_admin:
        await msg.answer("Access denied.")
        return
    try:
        from backend.institutional.data_store import data_store
        rows = await data_store.query(
            "SELECT ip_address,reason,block_type,expires_at,created_at "
            "FROM security_blocked_ips WHERE expires_at > NOW() OR expires_at IS NULL "
            "ORDER BY created_at DESC LIMIT 15"
        )
        if not rows:
            await msg.answer("No IPs currently blocked.")
            return
        lines = [f"\U0001f6d1 *Blocked IPs ({len(rows)}):*", ""]
        for r in rows:
            ip  = r.get("ip_address", "?")
            rsn = r.get("reason", "?")[:40]
            bt  = r.get("block_type", "?")
            exp = r.get("expires_at")
            exp_str = exp.strftime("%m-%d %H:%M") if exp and hasattr(exp, "strftime") else "permanent"
            lines.append(f"`{ip}` [{bt}] until `{exp_str}`\n  _{rsn}_")
        await msg.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        log.error("cmd_blocked: %s", exc)
        await msg.answer(f"Error: {exc}")


@router.message(Command("report"))
async def cmd_report(msg: Message) -> None:
    is_admin: bool = getattr(getattr(msg, "from_user", None), "_is_admin", False)
    if not is_admin:
        await msg.answer("Access denied.")
        return
    parts = (msg.text or "").split()
    try:
        days = int(parts[1]) if len(parts) > 1 else 7
        days = max(1, min(days, 90))
    except (ValueError, IndexError):
        await msg.answer("Usage: /report [days] (e.g. /report 30)")
        return
    await msg.answer(f"Generating {days}-day security report...")
    try:
        from backend.security_reporting.report_scheduler import report_scheduler
        run_record = await report_scheduler.trigger(period_hours=days * 24, label="telegram_manual")
        if run_record.get("error"):
            await msg.answer(f"Report failed: {run_record['error']}")
            return
        rep_id  = run_record.get("report_id") or "?"
        dur     = run_record.get("duration_s", 0)
        exports = run_record.get("exports", {})
        await msg.answer(
            f"Report Ready\nPeriod: {days}d | Duration: {dur:.1f}s\n"
            f"ID: {str(rep_id)[:12]}\nJSON: {exports.get('json','N/A')}",
        )
    except Exception as exc:
        log.error("cmd_report: %s", exc)
        await msg.answer(f"Error: {exc}")
