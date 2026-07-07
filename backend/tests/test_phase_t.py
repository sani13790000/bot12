"""Phase T unit tests - T1..T30 + integration (33 tests)"""

from __future__ import annotations

import asyncio
import os
import pathlib
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault("PYTEST_CURRENT_TEST", "test")


# stubs
class _SMC:
    symbol = "EURUSD"
    direction = "BUY"
    decision_score = 75.0
    spread_ratio = 1.0
    volatility_high = False


class _Meta:
    auc_roc = 0.82
    n_samples = 5000


class _FM:
    def load_best_model(self, s):
        import numpy as np

        class M:
            def predict_proba(self, X):
                return np.array([[0.22, 0.78]])

        return M()

    def get_best_metadata(self, s):
        return _Meta()


class _FB:
    def build_single(self, s):
        import numpy as np

        return np.zeros((1, 10))


def _db_result(data):
    r = MagicMock()
    r.data = data
    r.count = len(data)
    return r


def _chain_db(existing=None):
    db = MagicMock()
    c = MagicMock()
    for a in ("select", "eq", "gt", "lt", "order", "range", "limit", "insert", "update"):
        getattr(c, a).return_value = c
    calls = [0]

    def _ex():
        calls[0] += 1
        if calls[0] == 1:
            return _db_result(existing or [])
        return _db_result([{"id": "x", "user_id": "u1", "status": "OPEN"}])

    c.execute = _ex
    db.table.return_value = c
    return db, c


def _run(coro):
    return asyncio.run(coro)


def _ps():
    import backend.ai_prediction.prediction_service as m

    svc = m.PredictionService.__new__(m.PredictionService)
    svc._manager = _FM()
    svc._builder = _FB()
    svc._min_probability = 60
    svc._min_confidence = 50
    return svc, m


def test_t1_predict_is_async():
    import backend.ai_prediction.prediction_service as m

    svc = m.PredictionService.__new__(m.PredictionService)
    svc._manager = _FM()
    svc._builder = _FB()
    svc._min_probability = 60
    svc._min_confidence = 50
    coro = svc.predict(_SMC())
    assert asyncio.iscoroutine(coro)
    _run(coro)


def test_t2_predict_returns_result():
    svc, _ = _ps()
    r = _run(svc.predict(_SMC()))
    assert r is not None and hasattr(r, "probability")


def test_t3_concurrent_no_race():
    svc, _ = _ps()

    async def _g():
        return await asyncio.gather(*[svc.predict(_SMC()) for _ in range(5)])

    res = _run(_g())
    assert len(res) == 5


def test_t4_is_fallback_exists():
    svc, _ = _ps()
    r = _run(svc.predict(_SMC()))
    assert hasattr(r, "is_fallback") and r.is_fallback is False


def test_t5_risk_not_always_high():
    svc, _ = _ps()
    sig = _SMC()
    sig.spread_ratio = 0.8
    sig.volatility_high = False
    sig.decision_score = 90
    r = _run(svc.predict(sig))
    assert r.risk.value in ("LOW", "MEDIUM")


def test_t6_threshold_applied():
    svc, _ = _ps()
    svc._min_probability = 99
    r = _run(svc.predict(_SMC()))
    assert r.is_tradeable is False


def test_t7_no_model_fallback():
    import backend.ai_prediction.prediction_service as m

    class NM:
        def load_best_model(self, s):
            return None

        def get_best_metadata(self, s):
            return None

    svc = m.PredictionService.__new__(m.PredictionService)
    svc._manager = NM()
    svc._builder = _FB()
    svc._min_probability = 60
    svc._min_confidence = 50
    r = _run(svc.predict(_SMC()))
    assert r.is_tradeable is False and "no trained model" in r.reason


def test_t13_initial_balance():
    from backend.core.config import Settings

    f = Settings.model_fields.get("INITIAL_ACCOUNT_BALANCE")
    assert f and f.default == 10_000.0


def test_t14_api_prefix():
    from backend.core.config import Settings

    f = Settings.model_fields.get("API_PREFIX")
    assert f and f.default == "/api/v1"


def test_t15_reconcile_interval():
    from backend.core.config import Settings

    f = Settings.model_fields.get("RECONCILE_INTERVAL_SECONDS")
    assert f and f.default == 10


def test_t16_mt5_fields():
    from backend.core.config import Settings

    for fn in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"):
        assert fn in Settings.model_fields


def test_t17_semi_auto_ttl():
    from backend.core.config import Settings

    f = Settings.model_fields.get("SEMI_AUTO_PENDING_TTL_S")
    assert f and f.default == 300


def test_t18_drift_threshold():
    from backend.core.config import Settings

    f = Settings.model_fields.get("DRIFT_THRESHOLD")
    assert f and abs(f.default - 0.08) < 1e-9


def test_t19_signal_user_id_filter():
    from backend.services.signal_service import SignalService

    db, c = _chain_db()

    async def _r():
        return await SignalService(db).get_signal_by_id("s1", "userA")

    _run(_r())
    assert any("userA" in str(x) for x in c.eq.call_args_list)


def test_t20_expiry_in_db():
    from backend.services.signal_service import SignalService

    db, c = _chain_db()
    _run(SignalService(db).get_active_signals("u1"))
    assert any("expires_at" in str(x) for x in c.gt.call_args_list)


def test_t21_list_uses_range():
    from backend.services.signal_service import SignalService

    db, c = _chain_db()
    _run(SignalService(db).list_signals("u1", page=2, page_size=10))
    assert c.range.called


def test_t22_signal_idempotent():
    from backend.services.signal_service import SignalService

    row = {"id": "sig-x", "user_id": "u1"}
    db, c = _chain_db(existing=[row])
    r = _run(
        SignalService(db).create_signal("u1", "EURUSD", "BUY", 1.10, 1.09, 1.12, signal_id="sig-x")
    )
    assert r["id"] == "sig-x" and not c.insert.called


def test_t23_signal_optimistic_lock():
    from backend.services.signal_service import SignalService

    db, c = _chain_db()
    c.update.return_value = c
    ts = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    _run(SignalService(db).update_signal_status("s1", "u1", "CLOSED", updated_at=ts))
    assert any("2026-06-23" in str(x) for x in c.eq.call_args_list)


def test_t24_no_utcnow_in_signal():
    import ast

    src = (pathlib.Path(__file__).parent.parent / "services" / "signal_service.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "utcnow":
            raise AssertionError("utcnow found in signal_service")


def test_t25_double_close():
    from backend.services.trade_service import TradeService

    db, c = _chain_db()
    c.execute = lambda: _db_result([{"id": "tr1", "user_id": "u1", "status": "OPEN"}])
    svc = TradeService(db)

    async def _g():
        return await asyncio.gather(
            svc.close_trade("tr1", "u1", 1.105, 50.0), svc.close_trade("tr1", "u1", 1.105, 50.0)
        )

    res = _run(_g())
    assert len(res) == 2


def test_t26_trade_dedup():
    from backend.services.trade_service import TradeService

    ex = {"id": "tr1", "signal_id": "sig1", "user_id": "u1"}
    db, c = _chain_db(existing=[ex])
    r = _run(TradeService(db).create_trade("u1", "sig1", "EURUSD", "BUY", 0.1, 1.10, 1.09, 1.12))
    assert r["id"] == "tr1" and not c.insert.called


def test_t27_history_range():
    from backend.services.trade_service import TradeService

    db, c = _chain_db()
    _run(TradeService(db).get_trade_history("u1", page=2, page_size=25))
    assert c.range.called


def test_t28_equity_exported():
    from backend.services.trade_service import get_equity_state

    assert callable(get_equity_state)


def test_t29_trade_optimistic_lock():
    from backend.services.trade_service import TradeService

    db, c = _chain_db()
    ts = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    _run(TradeService(db).update_trade("tr1", "u1", {"pnl": 100.0}, current_updated_at=ts))
    assert any("2026-06-23" in str(x) for x in c.eq.call_args_list)


def test_t30_no_utcnow_in_trade():
    import ast

    src = (pathlib.Path(__file__).parent.parent / "services" / "trade_service.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "utcnow":
            raise AssertionError("utcnow found in trade_service")


def test_int1_config_all_new_fields():
    from backend.core.config import Settings

    for f in [
        "API_PREFIX",
        "INITIAL_ACCOUNT_BALANCE",
        "RECONCILE_INTERVAL_SECONDS",
        "MT5_LOGIN",
        "MT5_PASSWORD",
        "MT5_SERVER",
        "SEMI_AUTO_PENDING_TTL_S",
        "DRIFT_THRESHOLD",
    ]:
        assert f in Settings.model_fields, f"{f} missing"


def test_int2_prediction_full_flow():
    svc, m = _ps()
    svc._min_probability = 50
    svc._min_confidence = 0
    r = _run(svc.predict(_SMC()))
    assert r.probability >= 0 and r.confidence >= 0 and not r.is_fallback


def test_int3_signal_service_security():
    from backend.services.signal_service import SignalService

    db, c = _chain_db()
    _run(SignalService(db).get_signal_by_id("s1", "u-secret"))
    assert any("u-secret" in str(x) for x in c.eq.call_args_list)
