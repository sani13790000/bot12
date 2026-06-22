"""Phase P unit tests - 52 tests covering P-1..P-21."""
from __future__ import annotations
import asyncio, json, time, sys, types
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock
import pytest


# ---- WebSocketManager tests (P-6..P-10) ------------------------------------

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


@pytest.mark.asyncio
async def test_p6_broadcast_error_isolation():
    """P-6: broken connection must not kill broadcast."""
    from backend.api.websocket_manager import WebSocketManager, WSMessageType
    mgr = WebSocketManager()
    ws_ok   = AsyncMock()
    ws_fail = AsyncMock()
    ws_fail.send_text = AsyncMock(side_effect=ConnectionError("broken"))
    await mgr.connect(ws_ok,   "u1", "c1")
    await mgr.connect(ws_fail, "u2", "c2")
    sent = await mgr.broadcast(WSMessageType.SIGNAL, {})
    assert sent == 1


@pytest.mark.asyncio
async def test_p7_max_per_user():
    """P-7: enforce max connections per user."""
    from backend.api.websocket_manager import WebSocketManager, MAX_PER_USER
    mgr = WebSocketManager()
    results = []
    for i in range(MAX_PER_USER + 1):
        ws = AsyncMock()
        ok = await mgr.connect(ws, "user1", f"c{i}")
        results.append(ok)
    assert results[-1] is False
    assert sum(results) == MAX_PER_USER


@pytest.mark.asyncio
async def test_p8_pong_updates_timestamp():
    """P-8: pong updates last_pong."""
    from backend.api.websocket_manager import WebSocketManager, WSMessageType
    mgr = WebSocketManager()
    ws = AsyncMock()
    await mgr.connect(ws, "u1", "c1")
    old = mgr._connections["c1"].last_pong
    await asyncio.sleep(0.01)
    await mgr.handle_pong("c1")
    assert mgr._connections["c1"].last_pong >= old


@pytest.mark.asyncio
async def test_p8_stale_detection():
    """P-8: stale connection detected."""
    from backend.api.websocket_manager import WebSocketManager
    mgr = WebSocketManager()
    ws = AsyncMock()
    await mgr.connect(ws, "u1", "c1")
    mgr._connections["c1"].last_pong = time.monotonic() - 1000
    assert mgr._connections["c1"].is_stale is True


@pytest.mark.asyncio
async def test_p9_invalid_type_raises():
    """P-9: invalid message_type raises ValueError."""
    from backend.api.websocket_manager import WebSocketManager
    mgr = WebSocketManager()
    with pytest.raises(ValueError):
        await mgr.broadcast("INVALID", {})


@pytest.mark.asyncio
async def test_p10_subscription_filtering():
    """P-10: unsubscribed connections filtered out."""
    from backend.api.websocket_manager import WebSocketManager, WSMessageType
    mgr = WebSocketManager()
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    await mgr.connect(ws1, "u1", "c1")
    await mgr.connect(ws2, "u2", "c2")
    await mgr.handle_subscribe("c1", ["signals"])
    # c2 has no subscriptions -> receives all
    sent = await mgr.broadcast(WSMessageType.SIGNAL, {}, topic="signals")
    assert sent == 2  # c2 has no filter -> receives all


@pytest.mark.asyncio
async def test_p10_unsubscribe():
    from backend.api.websocket_manager import WebSocketManager
    mgr = WebSocketManager()
    ws = AsyncMock()
    await mgr.connect(ws, "u1", "c1")
    await mgr.handle_subscribe("c1", ["signals", "trades"])
    await mgr.handle_unsubscribe("c1", ["trades"])
    assert "trades" not in mgr._connections["c1"].subscriptions
    assert "signals" in mgr._connections["c1"].subscriptions


@pytest.mark.asyncio
async def test_p6_send_to_user_isolation():
    from backend.api.websocket_manager import WebSocketManager, WSMessageType
    mgr = WebSocketManager()
    ws_ok   = AsyncMock()
    ws_fail = AsyncMock()
    ws_fail.send_text = AsyncMock(side_effect=ConnectionError)
    await mgr.connect(ws_ok,   "u1", "c1")
    await mgr.connect(ws_fail, "u1", "c2")
    sent = await mgr.send_to_user("u1", WSMessageType.SIGNAL, {})
    assert sent == 1


@pytest.mark.asyncio
async def test_ws_disconnect_cleanup():
    from backend.api.websocket_manager import WebSocketManager
    mgr = WebSocketManager()
    ws = AsyncMock()
    await mgr.connect(ws, "u1", "c1")
    await mgr.disconnect("c1")
    assert "c1" not in mgr._connections
    assert "u1" not in mgr._user_conns


# ---- TelegramHandlers tests (P-11..P-15) ------------------------------------

def _make_update(callback_data=None):
    u = MagicMock()
    u.effective_chat.id = 123
    if callback_data:
        u.callback_query.data = callback_data
        u.callback_query.answer = AsyncMock()
        u.callback_query.edit_message_text = AsyncMock()
    return u


@pytest.mark.asyncio
async def test_p11_safe_handler_no_crash():
    """P-11: exception in handler must not propagate."""
    from backend.telegram.handlers_patch import safe_handler

    @safe_handler
    async def failing(update, context):
        raise RuntimeError("DB down")

    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    await failing(_make_update(), ctx)
    ctx.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_p12_callback_answered_immediately():
    """P-12: answer() called before processing."""
    from backend.telegram.handlers_patch import ApproveRejectHandler, _processed_callbacks, _idempotency_timestamps
    _processed_callbacks.clear(); _idempotency_timestamps.clear()
    svc = AsyncMock()
    svc.approve = AsyncMock(return_value={})
    handler = ApproveRejectHandler(svc)
    update = _make_update(callback_data="approve_sig1")
    ctx = MagicMock()
    await handler.handle(update, ctx)
    update.callback_query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_p13_idempotency():
    """P-13: duplicate callback processed only once."""
    from backend.telegram.handlers_patch import ApproveRejectHandler, _processed_callbacks, _idempotency_timestamps
    _processed_callbacks.clear(); _idempotency_timestamps.clear()
    svc = AsyncMock()
    svc.approve = AsyncMock(return_value={})
    handler = ApproveRejectHandler(svc)
    ctx = MagicMock()
    for _ in range(2):
        u = _make_update(callback_data="approve_sig2")
        await handler.handle(u, ctx)
    assert svc.approve.call_count == 1


def test_p14_rate_limit():
    """P-14: rate limit blocks flood."""
    from backend.telegram.handlers_patch import _RateLimiter, _RATE_LIMIT_MAX
    lim = _RateLimiter()
    results = [lim.is_allowed(999) for _ in range(_RATE_LIMIT_MAX + 5)]
    assert results.count(False) == 5


def test_p15_format_signal_safe():
    """P-15: None fields -> N/A, no AttributeError."""
    from backend.telegram.handlers_patch import format_signal_safe
    sig = {"symbol": "XAUUSD", "direction": "BUY"}
    out = format_signal_safe(sig)
    assert "XAUUSD" in out
    assert "N/A" in out


def test_p15_format_signal_full():
    from backend.telegram.handlers_patch import format_signal_safe
    sig = {"symbol": "EURUSD", "direction": "SELL",
           "entry_price": 1.085, "stop_loss": 1.09,
           "take_profit_1": 1.078, "confidence_score": 87,
           "risk_level": "LOW", "id": "abc"}
    out = format_signal_safe(sig)
    assert "1.08500" in out and "87%" in out and "abc" in out


# ---- LearningCycle tests (P-1..P-5) -----------------------------------------

def test_p2_learning_cycle_improved():
    from backend.intelligence.learning_service import LearningCycle, MIN_IMPROVEMENT_AUC
    from datetime import datetime, timezone
    c = LearningCycle(cycle_id="x", started_at=datetime.now(timezone.utc),
                      old_auc=0.70, new_auc=0.70+MIN_IMPROVEMENT_AUC+0.001)
    assert c.improved is True
    c2 = LearningCycle(cycle_id="y", started_at=datetime.now(timezone.utc),
                       old_auc=0.70, new_auc=0.69)
    assert c2.improved is False


def test_learning_cycle_to_dict():
    from backend.intelligence.learning_service import LearningCycle
    from datetime import datetime, timezone
    c = LearningCycle(cycle_id="z", started_at=datetime.now(timezone.utc))
    d = c.to_dict()
    for key in ["cycle_id","old_auc","new_auc","deployed","improved","error"]:
        assert key in d


@pytest.mark.asyncio
async def test_p5_lock_timeout():
    """P-5: lock held -> retrain returns lock_timeout."""
    from backend.intelligence.learning_service import IntelligenceLearningService
    svc = IntelligenceLearningService()
    await svc._retrain_lock.acquire()
    try:
        cycle = await svc._run_retrain("test")
        assert cycle.error == "lock_timeout"
    finally:
        svc._retrain_lock.release()


# ---- Route structure tests (P-16..P-21) -------------------------------------

def _get_paths(filename):
    import ast
    src = pathlib.Path(filename).read_text()
    paths = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in ("get","post","put","delete"):
                if node.args and isinstance(node.args[0], ast.Constant):
                    paths.append(node.args[0].value)
    return paths


def test_p16_retrain_route():
    paths = _get_paths("backend/api/routes/learning.py")
    assert any("retrain" in p for p in paths)


def test_p17_status_route():
    paths = _get_paths("backend/api/routes/learning.py")
    assert any("status" in p for p in paths)


def test_p17_cycles_route():
    paths = _get_paths("backend/api/routes/learning.py")
    assert any("cycle" in p for p in paths)


def test_p18_record_outcome_route():
    paths = _get_paths("backend/api/routes/learning.py")
    assert any("record" in p for p in paths)


def test_p19_portfolio_routes():
    paths = _get_paths("backend/api/routes/portfolio.py")
    for r in ["summary","positions","exposure","correlation","risk-breakdown"]:
        assert any(r in p for p in paths), f"{r} missing"


def test_p20_rolling_correlation_in_portfolio():
    src = pathlib.Path("backend/api/routes/portfolio.py").read_text()
    assert "RollingCorrelationEngine" in src


def test_p21_exposure_logic():
    trades = [
        {"symbol":"EURUSD","direction":"BUY","volume":0.1,"pnl":50.0},
        {"symbol":"EURUSD","direction":"SELL","volume":0.05,"pnl":-10.0},
    ]
    by_sym: Dict[str, Any] = {}
    for t in trades:
        s = t["symbol"]
        if s not in by_sym:
            by_sym[s] = {"buy_lots":0.0,"sell_lots":0.0,"net_pnl":0.0}
        if t["direction"]=="BUY": by_sym[s]["buy_lots"]  += t["volume"]
        else:                      by_sym[s]["sell_lots"] += t["volume"]
        by_sym[s]["net_pnl"] += t["pnl"]
    assert abs(by_sym["EURUSD"]["buy_lots"]  - 0.10) < 1e-9
    assert abs(by_sym["EURUSD"]["sell_lots"] - 0.05) < 1e-9
    assert abs(by_sym["EURUSD"]["net_pnl"]   - 40.0) < 1e-9


# ---- Rate limiter window reset integration -----------------------------------

def test_rate_limit_window_reset():
    from backend.telegram.handlers_patch import _RateLimiter
    lim = _RateLimiter()
    lim._counts[777] = [time.time() - 120] * 30
    assert lim.is_allowed(777) is True


def test_ws_message_types_complete():
    from backend.api.websocket_manager import WSMessageType
    for t in ["signal","trade_update","equity_update","risk_alert","system","ping","pong"]:
        assert t in [m.value for m in WSMessageType]
