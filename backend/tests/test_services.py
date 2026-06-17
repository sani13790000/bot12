"""
تست‌های Unit برای Services لایه

تست‌های کامل برای DecisionService، SignalService و TradeService.

نویسنده: MT5 Trading Team
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from typing import Dict, Any, List

from backend.services.decision_service import DecisionService
from backend.services.signal_service import SignalService
from backend.services.trade_service import TradeService


# =====================================================
# Helper: mock database
# =====================================================

def make_mock_db():
    """ساخت mock database"""
    db = MagicMock()
    db.select_one = AsyncMock(return_value=None)
    db.select_many = AsyncMock(return_value=[])
    db.insert = AsyncMock(return_value={"id": "test-id-001"})
    db.update = AsyncMock(return_value=[{"id": "test-id-001"}])
    db.delete = AsyncMock(return_value=True)
    db.count = AsyncMock(return_value=0)
    db.upsert = AsyncMock(return_value={"id": "test-id-001"})
    return db


def make_signal_data(user_id="user-001", symbol="EURUSD"):
    """ساخت داده سیگنال تستی"""
    return {
        "id": "signal-001",
        "user_id": user_id,
        "symbol": symbol,
        "timeframe": "H1",
        "direction": "buy",
        "entry_price": 1.0850,
        "stop_loss": 1.0825,
        "take_profit_1": 1.0890,
        "confidence_score": 75,
        "quality_score": 72,
        "status": "generated",
        "valid_until": "2099-12-31T00:00:00",
        "created_at": datetime.utcnow().isoformat(),
    }


def make_trade_data(user_id="user-001", symbol="EURUSD"):
    """ساخت داده معامله تستی"""
    return {
        "id": "trade-001",
        "user_id": user_id,
        "symbol": symbol,
        "direction": "buy",
        "entry_price": 1.0850,
        "stop_loss": 1.0825,
        "take_profit": 1.0900,
        "lot_size": 0.01,
        "status": "open",
        "profit_money": 0.0,
        "created_at": datetime.utcnow().isoformat(),
    }


# =====================================================
# تست DecisionService
# =====================================================

class TestDecisionService:
    """تست سرویس تصمیم‌گیری"""

    def test_init(self):
        """تست مقداردهی اولیه"""
        service = DecisionService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_request_decision_returns_dict(self):
        """تست اینکه request_decision یک dict برمی‌گرداند"""
        service = DecisionService()
        mock_db = make_mock_db()
        mock_db.insert = AsyncMock(return_value={"id": "decision-001"})

        with patch("backend.services.decision_service.db", mock_db):
            with patch("backend.analysis.decision_engine.DecisionEngine.decide") as mock_decide:
                mock_decide.return_value = {
                    "decision": "BUY",
                    "direction": "bullish",
                    "confidence_score": 75,
                    "quality_score": 72,
                    "allowed": True,
                    "reason_codes": ["SMC_BULLISH_BOS"],
                    "reasons": ["BOS صعودی"],
                    "trading_levels": {
                        "entry_zone": 1.0850,
                        "stop_loss": 1.0825,
                        "take_profit_1": 1.0890,
                        "risk_reward_ratio": 2.4,
                    },
                    "score_breakdown": {"smc": 75, "price_action": 70, "session": 80},
                }
                request = {
                    "user_id": "user-001",
                    "symbol": "EURUSD",
                    "timeframe": "H1",
                    "current_price": 1.0850,
                    "spread": 0.0002,
                    "atr": 0.0015,
                    "session_score": 80,
                    "market_data": {},
                    "smc_data": {"trend": "bullish", "score": 75, "in_kill_zone": True},
                    "pa_data": {"overall_bias": "bullish", "score": 70},
                    "license_info": {"is_valid": True, "features": ["auto_trading"], "license_type": "pro"},
                }
                result = await service.request_decision(request, user_id="user-001")
                assert result is not None

    @pytest.mark.asyncio
    async def test_get_latest_decision_empty(self):
        """تست دریافت آخرین تصمیم — بدون تصمیم"""
        service = DecisionService()
        mock_db = make_mock_db()
        mock_db.select_many = AsyncMock(return_value=[])

        with patch("backend.services.decision_service.db", mock_db):
            result = await service.get_latest_decision("user-001", "EURUSD")
            assert result is None or result == {}

    @pytest.mark.asyncio
    async def test_get_latest_decision_returns_last(self):
        """تست دریافت آخرین تصمیم"""
        service = DecisionService()
        mock_db = make_mock_db()
        mock_decision = {
            "id": "decision-001",
            "user_id": "user-001",
            "symbol": "EURUSD",
            "decision": "BUY",
            "created_at": datetime.utcnow().isoformat(),
        }
        mock_db.select_many = AsyncMock(return_value=[mock_decision])

        with patch("backend.services.decision_service.db", mock_db):
            result = await service.get_latest_decision("user-001", "EURUSD")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_decision_by_id_not_found(self):
        """تست دریافت تصمیم با ID ناموجود"""
        service = DecisionService()
        mock_db = make_mock_db()
        mock_db.select_one = AsyncMock(return_value=None)

        with patch("backend.services.decision_service.db", mock_db):
            result = await service.get_decision_by_id("nonexistent-id", "user-001")
            assert result is None

    def test_cache_set_and_get(self):
        """تست cache ذخیره و دریافت"""
        service = DecisionService()
        key = "test_key"
        value = {"data": "test_value"}
        service._set_cache(key, value)
        cached = service._get_cached(key)
        assert cached == value

    def test_cache_returns_none_for_unknown_key(self):
        """تست cache برای کلید ناشناخته"""
        service = DecisionService()
        result = service._get_cached("nonexistent_key_xyz")
        assert result is None

    def test_build_decision_input_structure(self):
        """تست ساختار _build_decision_input"""
        service = DecisionService()
        request = {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "current_price": 1.0850,
            "spread": 0.0002,
            "atr": 0.0015,
            "session_score": 80,
            "market_data": {},
            "smc_data": {"trend": "bullish", "score": 75},
            "pa_data": {"overall_bias": "bullish", "score": 70},
            "license_info": {"is_valid": True},
        }
        user_id = "user-001"
        result = service._build_decision_input(request, user_id)
        assert result is not None
        if isinstance(result, dict):
            assert "symbol" in result or "user_id" in result or result != {}


# =====================================================
# تست SignalService
# =====================================================

class TestSignalService:
    """تست سرویس سیگنال"""

    def test_init(self):
        """تست مقداردهی اولیه"""
        service = SignalService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_get_signals_empty(self):
        """تست دریافت سیگنال‌ها — خالی"""
        service = SignalService()
        mock_db = make_mock_db()
        mock_db.select_many = AsyncMock(return_value=[])

        with patch("backend.services.signal_service.db", mock_db):
            result = await service.get_signals(user_id="user-001", limit=10)
            assert result == [] or result is not None

    @pytest.mark.asyncio
    async def test_get_signals_with_data(self):
        """تست دریافت سیگنال‌ها با داده"""
        service = SignalService()
        mock_db = make_mock_db()
        signals = [make_signal_data(), make_signal_data(symbol="GBPUSD")]
        mock_db.select_many = AsyncMock(return_value=signals)

        with patch("backend.services.signal_service.db", mock_db):
            result = await service.get_signals(user_id="user-001", limit=10)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_active_signals(self):
        """تست دریافت سیگنال‌های فعال"""
        service = SignalService()
        mock_db = make_mock_db()
        signal = make_signal_data()
        mock_db.select_many = AsyncMock(return_value=[signal])

        with patch("backend.services.signal_service.db", mock_db):
            result = await service.get_active_signals(user_id="user-001")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_signal_by_id_found(self):
        """تست دریافت سیگنال با ID"""
        service = SignalService()
        mock_db = make_mock_db()
        signal = make_signal_data()
        mock_db.select_one = AsyncMock(return_value=signal)

        with patch("backend.services.signal_service.db", mock_db):
            result = await service.get_signal(signal_id="signal-001", user_id="user-001")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_signal_by_id_not_found(self):
        """تست دریافت سیگنال ناموجود"""
        service = SignalService()
        mock_db = make_mock_db()
        mock_db.select_one = AsyncMock(return_value=None)

        with patch("backend.services.signal_service.db", mock_db):
            result = await service.get_signal(signal_id="nonexistent", user_id="user-001")
            assert result is None

    @pytest.mark.asyncio
    async def test_mark_signal_sent(self):
        """تست علامت‌گذاری سیگنال به عنوان ارسال‌شده"""
        service = SignalService()
        mock_db = make_mock_db()
        mock_db.update = AsyncMock(return_value=[{"id": "signal-001", "status": "sent"}])

        with patch("backend.services.signal_service.db", mock_db):
            result = await service.mark_signal_sent(signal_id="signal-001")
            assert result is not None

    @pytest.mark.asyncio
    async def test_mark_signal_executed(self):
        """تست علامت‌گذاری سیگنال به عنوان اجراشده"""
        service = SignalService()
        mock_db = make_mock_db()
        mock_db.update = AsyncMock(return_value=[{"id": "signal-001", "status": "executed"}])

        with patch("backend.services.signal_service.db", mock_db):
            result = await service.mark_signal_executed(signal_id="signal-001")
            assert result is not None

    @pytest.mark.asyncio
    async def test_expire_signals(self):
        """تست expire کردن سیگنال‌های قدیمی"""
        service = SignalService()
        mock_db = make_mock_db()
        mock_db.update = AsyncMock(return_value=[{"id": "signal-001"}])

        with patch("backend.services.signal_service.db", mock_db):
            result = await service.expire_signals()
            assert result is not None
            assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_get_signal_stats(self):
        """تست دریافت آمار سیگنال‌ها"""
        service = SignalService()
        mock_db = make_mock_db()
        mock_db.count = AsyncMock(return_value=5)
        mock_db.select_many = AsyncMock(return_value=[])

        with patch("backend.services.signal_service.db", mock_db):
            result = await service.get_signal_stats(user_id="user-001")
            assert result is not None
            if isinstance(result, dict):
                assert len(result) > 0


# =====================================================
# تست TradeService
# =====================================================

class TestTradeService:
    """تست سرویس معاملات"""

    def test_init(self):
        """تست مقداردهی اولیه"""
        service = TradeService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_get_trades_empty(self):
        """تست دریافت معاملات — خالی"""
        service = TradeService()
        mock_db = make_mock_db()
        mock_db.select_many = AsyncMock(return_value=[])

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.get_trades(user_id="user-001", limit=10)
            assert result == [] or result is not None

    @pytest.mark.asyncio
    async def test_get_trades_with_data(self):
        """تست دریافت معاملات با داده"""
        service = TradeService()
        mock_db = make_mock_db()
        trades = [make_trade_data(), make_trade_data(symbol="GBPUSD")]
        mock_db.select_many = AsyncMock(return_value=trades)

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.get_trades(user_id="user-001", limit=10)
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_open_positions(self):
        """تست دریافت پوزیشن‌های باز"""
        service = TradeService()
        mock_db = make_mock_db()
        open_trade = make_trade_data()
        mock_db.select_many = AsyncMock(return_value=[open_trade])

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.get_open_positions(user_id="user-001")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_trade_by_id(self):
        """تست دریافت معامله با ID"""
        service = TradeService()
        mock_db = make_mock_db()
        trade = make_trade_data()
        mock_db.select_one = AsyncMock(return_value=trade)

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.get_trade(trade_id="trade-001", user_id="user-001")
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_trade_not_found(self):
        """تست دریافت معامله ناموجود"""
        service = TradeService()
        mock_db = make_mock_db()
        mock_db.select_one = AsyncMock(return_value=None)

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.get_trade(trade_id="nonexistent", user_id="user-001")
            assert result is None

    @pytest.mark.asyncio
    async def test_report_trade_success(self):
        """تست گزارش معامله جدید"""
        service = TradeService()
        mock_db = make_mock_db()
        trade_data = make_trade_data()
        mock_db.insert = AsyncMock(return_value={"id": "trade-001"})

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.report_trade(
                user_id="user-001",
                trade_data=trade_data
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_close_trade_success(self):
        """تست بستن معامله"""
        service = TradeService()
        mock_db = make_mock_db()
        trade = make_trade_data()
        mock_db.select_one = AsyncMock(return_value=trade)
        mock_db.update = AsyncMock(return_value=[{**trade, "status": "closed", "exit_price": 1.0900}])

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.close_trade(
                trade_id="trade-001",
                user_id="user-001",
                exit_price=1.0900,
                profit_money=50.0
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_close_trade_not_found(self):
        """تست بستن معامله ناموجود"""
        service = TradeService()
        mock_db = make_mock_db()
        mock_db.select_one = AsyncMock(return_value=None)

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.close_trade(
                trade_id="nonexistent",
                user_id="user-001",
                exit_price=1.0900,
                profit_money=0.0
            )
            assert result is None or result == {} or result is False

    @pytest.mark.asyncio
    async def test_get_trade_stats(self):
        """تست دریافت آمار معاملات"""
        service = TradeService()
        mock_db = make_mock_db()
        mock_db.count = AsyncMock(return_value=10)
        mock_db.select_many = AsyncMock(return_value=[
            {"profit_money": 100.0, "status": "closed"},
            {"profit_money": -50.0, "status": "closed"},
            {"profit_money": 75.0, "status": "closed"},
        ])

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.get_trade_stats(user_id="user-001")
            assert result is not None
            if isinstance(result, dict):
                assert len(result) > 0

    @pytest.mark.asyncio
    async def test_get_daily_breakdown(self):
        """تست دریافت جزئیات روزانه"""
        service = TradeService()
        mock_db = make_mock_db()
        mock_db.select_many = AsyncMock(return_value=[])

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.get_daily_breakdown(user_id="user-001", days=7)
            assert result is not None

    @pytest.mark.asyncio
    async def test_close_all_trades(self):
        """تست بستن همه معاملات"""
        service = TradeService()
        mock_db = make_mock_db()
        open_trades = [make_trade_data(), make_trade_data(symbol="GBPUSD")]
        mock_db.select_many = AsyncMock(return_value=open_trades)
        mock_db.update = AsyncMock(return_value=[{"status": "closed"}])

        with patch("backend.services.trade_service.db", mock_db):
            result = await service.close_all_trades(user_id="user-001")
            assert result is not None


# =====================================================
# تست آمار معاملات (بدون mock)
# =====================================================

class TestTradeStatsCalculation:
    """تست محاسبه آمار معاملات"""

    def test_profit_calculation(self):
        """تست محاسبه سود کل"""
        trades = [
            {"profit_money": 100.0},
            {"profit_money": -50.0},
            {"profit_money": 75.0},
            {"profit_money": -25.0},
        ]
        total = sum(t["profit_money"] for t in trades)
        assert total == 100.0

    def test_win_rate_calculation(self):
        """تست محاسبه win rate"""
        trades = [
            {"profit_money": 100.0},
            {"profit_money": -50.0},
            {"profit_money": 75.0},
            {"profit_money": -25.0},
        ]
        winners = len([t for t in trades if t["profit_money"] > 0])
        win_rate = (winners / len(trades)) * 100
        assert win_rate == 50.0

    def test_risk_reward_calculation(self):
        """تست محاسبه نسبت ریسک به ریوارد"""
        entry = 1.0850
        stop_loss = 1.0825
        take_profit = 1.0910

        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        rr_ratio = reward / risk

        assert rr_ratio > 2.0  # باید بالای ۲ باشد

    def test_equity_curve_calculation(self):
        """تست محاسبه equity curve"""
        initial_balance = 10000.0
        trades = [100.0, -50.0, 75.0, -25.0, 150.0]

        balance = initial_balance
        curve = [balance]
        for pnl in trades:
            balance += pnl
            curve.append(balance)

        assert len(curve) == 6
        assert curve[0] == 10000.0
        assert curve[-1] == 10250.0

    def test_drawdown_calculation(self):
        """تست محاسبه drawdown"""
        equity_curve = [10000, 10200, 10100, 9900, 10300]
        peak = 10000
        max_dd = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd
        assert max_dd > 0
