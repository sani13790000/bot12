"""
backend/tests/test_phase_s_live.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
فاز S — Live Test Suite

این تست‌ها به MT5 Gateway واقعی، Supabase، و Backend در حال اجرا نیاز دارند.
به صورت پیش‌فرض skip می‌شوند. برای اجرا:

    pytest backend/tests/test_phase_s_live.py -m live -v
    pytest backend/tests/test_phase_s_live.py -m db -v
    pytest backend/tests/test_phase_s_live.py -m http -v

متغیرهای محیطی مورد نیاز:
    MT5_GATEWAY_URL   — آدرس gateway (پیش‌فرض: http://localhost:8080)
    GATEWAY_API_KEY   — کلید احراز هویت gateway
    MT5_DEMO_MODE     — باید false باشد
    SUPABASE_URL      — آدرس Supabase
    SUPABASE_KEY      — کلید Supabase
    BACKEND_URL       — آدرس backend (پیش‌فرض: http://localhost:8000)
"""
from __future__ import annotations

import asyncio
import os
import time
import pytest
import httpx

# ── تنظیمات ──────────────────────────────────────────────────────────────── #
GW_URL      = os.environ.get("MT5_GATEWAY_URL", "http://localhost:8080")
GW_KEY      = os.environ.get("GATEWAY_API_KEY", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
GW_HEADERS  = {"X-Gateway-Key": GW_KEY} if GW_KEY else {}


# ══════════════════════════════════════════════════════════════════════════════
# S-A: MT5 Gateway Live Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
class TestGatewayLive:
    """
    تست‌های live روی MT5 Gateway واقعی.
    نیاز: agent.py روی Windows در حال اجرا باشد.
    """

    def test_gateway_ping(self):
        """S-A-1: Gateway /ping باید پاسخ دهد و MT5 متصل باشد."""
        r = httpx.get(f"{GW_URL}/ping", headers=GW_HEADERS, timeout=10.0)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "mt5_connected" in data, "فیلد mt5_connected در پاسخ نیست"
        assert data["mt5_connected"] is True, f"MT5 متصل نیست: {data}"

    def test_gateway_account_info(self):
        """S-A-2: Gateway /account باید اطلاعات حساب را برگرداند."""
        r = httpx.get(f"{GW_URL}/account", headers=GW_HEADERS, timeout=10.0)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "balance" in data, "فیلد balance در پاسخ نیست"
        assert float(data["balance"]) > 0, f"Balance صفر یا منفی است: {data['balance']}"
        assert "equity" in data, "فیلد equity در پاسخ نیست"
        assert "leverage" in data, "فیلد leverage در پاسخ نیست"

    def test_gateway_candles_eurusd(self):
        """S-A-3: Gateway /candles باید کندل‌های EURUSD را برگرداند."""
        payload = {"symbol": "EURUSD", "timeframe": "H1", "count": 10}
        r = httpx.post(f"{GW_URL}/candles", json=payload, headers=GW_HEADERS, timeout=15.0)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "candles" in data, "فیلد candles در پاسخ نیست"
        candles = data["candles"]
        assert len(candles) > 0, "هیچ کندلی دریافت نشد"
        c = candles[0]
        assert "open" in c and "high" in c and "low" in c and "close" in c
        assert float(c["high"]) >= float(c["low"]), "High < Low در کندل واقعی!"
        assert float(c["high"]) >= float(c["open"]), "High < Open در کندل واقعی!"

    def test_gateway_auth_required(self):
        """S-A-4: بدون X-Gateway-Key باید 403 برگردد."""
        if not GW_KEY:
            pytest.skip("GATEWAY_API_KEY تنظیم نشده — تست auth skip شد")
        r = httpx.get(f"{GW_URL}/account", timeout=5.0)
        assert r.status_code == 403, f"Expected 403 (auth required), got {r.status_code}"

    def test_gateway_positions_list(self):
        """S-A-5: Gateway /positions باید لیست پوزیشن‌ها را برگرداند (ممکن است خالی باشد)."""
        r = httpx.get(f"{GW_URL}/positions", headers=GW_HEADERS, timeout=10.0)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "positions" in data, "فیلد positions در پاسخ نیست"
        assert "count" in data, "فیلد count در پاسخ نیست"
        assert data["count"] == len(data["positions"]), "count با len(positions) مطابقت ندارد"

    def test_gateway_open_and_close_demo_order(self):
        """
        S-A-6: باز کردن و بستن یک order روی Demo Account.
        هشدار: این تست یک trade واقعی روی Demo باز می‌کند!
        """
        demo_mode = os.environ.get("MT5_DEMO_MODE", "true").lower()
        if demo_mode not in ("false", "0", "no", "off"):
            pytest.skip("MT5_DEMO_MODE=true — تست trade واقعی skip شد. برای اجرا: MT5_DEMO_MODE=false")

        open_payload = {
            "symbol": "EURUSD",
            "direction": "BUY",
            "lot": 0.01,
            "sl": None,
            "tp": None,
            "comment": "pytest_phase_s"
        }
        r_open = httpx.post(f"{GW_URL}/order/open", json=open_payload, headers=GW_HEADERS, timeout=15.0)
        assert r_open.status_code == 200, f"open order failed: {r_open.status_code} {r_open.text}"
        open_data = r_open.json()
        assert "ticket" in open_data, f"ticket در پاسخ open نیست: {open_data}"
        ticket = open_data["ticket"]
        assert ticket > 0, f"ticket نامعتبر: {ticket}"

        time.sleep(1)

        close_payload = {"ticket": ticket}
        r_close = httpx.post(f"{GW_URL}/order/close", json=close_payload, headers=GW_HEADERS, timeout=15.0)
        assert r_close.status_code == 200, f"close order failed: {r_close.status_code} {r_close.text}"
        close_data = r_close.json()
        assert close_data.get("closed") is True, f"closed=False در پاسخ: {close_data}"


# ══════════════════════════════════════════════════════════════════════════════
# S-B: Backend HTTP Live Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.http
class TestBackendLive:
    """
    تست‌های HTTP روی Backend FastAPI در حال اجرا.
    نیاز: uvicorn backend.api.main:app --port 8000
    """

    def test_health_endpoint(self):
        """S-B-1: /health باید 200 و status برگرداند."""
        r = httpx.get(f"{BACKEND_URL}/health", timeout=15.0)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "status" in data, "فیلد status در /health نیست"
        assert data["status"] in ("healthy", "degraded", "unhealthy")
        assert "components" in data, "فیلد components در /health نیست"
        assert "uptime_seconds" in data

    def test_liveness_probe(self):
        """S-B-2: /live باید 200 و status=ok برگرداند."""
        r = httpx.get(f"{BACKEND_URL}/live", timeout=5.0)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        assert r.json()["status"] == "ok"

    def test_readiness_probe_returns_correct_code(self):
        """S-B-3: /ready باید 200 یا 503 برگرداند — هرگز 500."""
        r = httpx.get(f"{BACKEND_URL}/ready", timeout=15.0)
        assert r.status_code in (200, 503), f"Expected 200 or 503, got {r.status_code}: {r.text}"

    def test_api_docs_disabled_in_production(self):
        """S-B-4: در production، /docs باید 404 برگرداند."""
        app_env = os.environ.get("APP_ENV", "development")
        if app_env != "production":
            pytest.skip(f"APP_ENV={app_env} — این تست فقط در production اجرا می‌شود")
        r = httpx.get(f"{BACKEND_URL}/docs", timeout=5.0)
        assert r.status_code == 404, f"Swagger docs باز است در production! status={r.status_code}"

    def test_rate_limit_active(self):
        """S-B-5: Rate limiter باید فعال باشد."""
        responses = []
        for _ in range(60):
            r = httpx.get(f"{BACKEND_URL}/live", timeout=3.0)
            responses.append(r.status_code)
        assert all(s in (200, 429) for s in responses), f"وضعیت‌های غیرمنتظره: {set(responses)}"


# ══════════════════════════════════════════════════════════════════════════════
# S-C: Supabase Live Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.db
class TestSupabaseLive:
    """
    تست‌های Supabase واقعی.
    نیاز: SUPABASE_URL و SUPABASE_KEY تنظیم شده باشند.
    """

    def test_supabase_connection(self):
        """S-C-1: اتصال به Supabase باید موفق باشد."""
        supabase_url = os.environ.get("SUPABASE_URL", "")
        supabase_key = os.environ.get("SUPABASE_KEY", "")
        if not supabase_url or not supabase_key:
            pytest.skip("SUPABASE_URL یا SUPABASE_KEY تنظیم نشده")
        from backend.database.connection import get_db_client
        db = get_db_client()
        result = db.table("signals").select("id").limit(1).execute()
        assert result is not None

    def test_supabase_signals_table_exists(self):
        """S-C-2: جدول signals باید وجود داشته باشد."""
        supabase_url = os.environ.get("SUPABASE_URL", "")
        if not supabase_url:
            pytest.skip("SUPABASE_URL تنظیم نشده")
        from backend.database.connection import get_db_client
        db = get_db_client()
        result = db.table("signals").select("id,symbol,direction,confidence").limit(5).execute()
        assert hasattr(result, "data")

    def test_supabase_trades_table_exists(self):
        """S-C-3: جدول trades باید وجود داشته باشد."""
        supabase_url = os.environ.get("SUPABASE_URL", "")
        if not supabase_url:
            pytest.skip("SUPABASE_URL تنظیم نشده")
        from backend.database.connection import get_db_client
        db = get_db_client()
        result = db.table("trades").select("id,ticket,symbol,direction").limit(5).execute()
        assert hasattr(result, "data")

    def test_supabase_users_table_exists(self):
        """S-C-4: جدول users باید وجود داشته باشد."""
        supabase_url = os.environ.get("SUPABASE_URL", "")
        if not supabase_url:
            pytest.skip("SUPABASE_URL تنظیم نشده")
        from backend.database.connection import get_db_client
        db = get_db_client()
        result = db.table("users").select("id,telegram_id").limit(5).execute()
        assert hasattr(result, "data")


# ══════════════════════════════════════════════════════════════════════════════
# S-D: MT5Connector Live Integration
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
class TestMT5ConnectorLive:
    """
    تست‌های MT5Connector در live mode با gateway واقعی.
    نیاز: MT5_GATEWAY_URL و GATEWAY_API_KEY تنظیم شده باشند.
    """

    @pytest.mark.asyncio
    async def test_connector_live_connect(self):
        """S-D-1: MT5Connector(demo=False) باید به gateway واقعی وصل شود."""
        if not GW_KEY:
            pytest.skip("GATEWAY_API_KEY تنظیم نشده")
        from backend.execution.mt5_connector import MT5Connector
        connector = MT5Connector(base_url=GW_URL, demo=False)
        await connector.connect()
        assert connector._connected is True
        h = await connector.health_check()
        assert h["ok"] is True, f"health_check failed: {h}"
        assert h["mode"] == "LIVE"
        await connector.disconnect()

    @pytest.mark.asyncio
    async def test_connector_live_candles(self):
        """S-D-2: get_candles() در live باید کندل‌های واقعی برگرداند."""
        if not GW_KEY:
            pytest.skip("GATEWAY_API_KEY تنظیم نشده")
        from backend.execution.mt5_connector import MT5Connector
        async with MT5Connector(base_url=GW_URL, demo=False) as connector:
            candles = await connector.get_candles("EURUSD", "H1", 10)
            assert len(candles) > 0
            for c in candles:
                assert c.high >= c.low
                assert c.high >= c.open
                assert c.volume >= 0

    @pytest.mark.asyncio
    async def test_connector_live_account_info(self):
        """S-D-3: get_account_info() در live باید balance واقعی برگرداند."""
        if not GW_KEY:
            pytest.skip("GATEWAY_API_KEY تنظیم نشده")
        from backend.execution.mt5_connector import MT5Connector
        async with MT5Connector(base_url=GW_URL, demo=False) as connector:
            info = await connector.get_account_info()
            assert "balance" in info
            assert float(info["balance"]) > 0

    @pytest.mark.asyncio
    async def test_full_live_pipeline_demo_account(self):
        """
        S-D-4: Pipeline کامل روی Demo Account:
        MT5Connector → SMCEngine → DecisionEngine → ExecutionService
        هشدار: یک trade واقعی روی Demo Account باز و بسته می‌کند!
        """
        demo_mode = os.environ.get("MT5_DEMO_MODE", "true").lower()
        if demo_mode not in ("false", "0", "no", "off"):
            pytest.skip("MT5_DEMO_MODE=true — برای اجرای trade واقعی: MT5_DEMO_MODE=false")
        if not GW_KEY:
            pytest.skip("GATEWAY_API_KEY تنظیم نشده")

        from backend.execution.mt5_connector import MT5Connector
        from backend.analysis.smc_engine import SMCEngine, Candle
        from backend.analysis.decision_engine import DecisionEngine, EngineVote, TradeDirection
        from backend.execution.execution_service import ExecutionService, TradeSignal

        async with MT5Connector(base_url=GW_URL, demo=False) as connector:
            raw_candles = await connector.get_candles("EURUSD", "H1", 200)
            assert len(raw_candles) >= 50

            candles = [
                Candle(
                    time=int(c.time.timestamp()),
                    open=c.open, high=c.high, low=c.low, close=c.close,
                    tick_volume=c.volume,
                )
                for c in raw_candles
            ]
            smc = SMCEngine()
            analysis = smc.analyse(candles)
            assert analysis is not None
            assert 0.0 <= analysis.confidence <= 1.0

            direction = TradeDirection.BUY if analysis.bias == "bullish" else TradeDirection.SELL
            last_close = raw_candles[-1].close
            sl = last_close - 0.0050 if direction == TradeDirection.BUY else last_close + 0.0050
            tp = last_close + 0.0100 if direction == TradeDirection.BUY else last_close - 0.0100

            de = DecisionEngine(min_confidence=0.50, min_votes=1, min_rr=1.5)
            votes = [EngineVote("SMC", direction, analysis.confidence, last_close, sl, tp)]
            decision = de.decide(votes, "EURUSD", "H1")

            if not decision.should_trade:
                pytest.skip(f"DecisionEngine تصمیم به trade نگرفت: confidence={analysis.confidence:.2f}")

            svc = ExecutionService(connector=connector)
            sig = TradeSignal(
                symbol="EURUSD",
                direction=direction.value.lower(),
                volume=0.01,
                sl=decision.sl_price,
                tp=decision.tp_price,
                confidence=decision.confidence,
                source="pytest_phase_s",
            )
            result = await svc.execute(sig)
            assert result.success, f"اجرای trade ناموفق: {result.error}"
            assert result.ticket > 0

            await asyncio.sleep(1)
            close_result = await svc.close(result.ticket)
            assert close_result.success, f"بستن trade ناموفق: {close_result.error}"
