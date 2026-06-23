"""tests/test_phase_u.py -- Phase U, 48 unit tests"""
from __future__ import annotations
import asyncio, sys, os, time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'services'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'risk'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'core'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'api', 'routes'))


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running() or loop.is_closed():
            raise RuntimeError
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# stubs
class _FakeLogger:
    def warning(self, *a, **k): pass
    def info(self, *a, **k): pass
    def error(self, *a, **k): pass
    def critical(self, *a, **k): pass


# ---- trade_service_patch stubs ----
import types
_tsm = types.ModuleType("backend"); _tsm.core = types.ModuleType("backend.core")
_lg = types.ModuleType("backend.core.logger"); _lg.get_logger = lambda n: _FakeLogger()
_tsm.core.logger = _lg
sys.modules["backend"] = _tsm; sys.modules["backend.core"] = _tsm.core
sys.modules["backend.core.logger"] = _lg

import importlib.util, pathlib

def _load(rel: str):
    repo = pathlib.Path(__file__).parents[2]
    spec = importlib.util.spec_from_file_location(rel.replace('/','.'), repo / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

tsp  = _load("backend/services/trade_service_patch.py")
epp  = _load("backend/risk/equity_protection_patch.py")


# ===================== U-1..U-5 trade_service_patch =====================

class TestU1Statistics:
    def test_empty(self):
        s = tsp.compute_statistics([])
        assert s["total_trades"] == 0 and s["profit_factor"] == 0.0

    def test_only_wins(self):
        t = [{"status":"closed","pnl_usd":100},{"status":"closed","pnl_usd":200}]
        s = tsp.compute_statistics(t)
        assert s["win_rate"] == 100.0 and s["profit_factor"] == 0.0

    def test_mixed(self):
        t = [{"status":"closed","pnl_usd":200},{"status":"closed","pnl_usd":-100}]
        s = tsp.compute_statistics(t)
        assert s["profit_factor"] == pytest.approx(2.0) and s["win_rate"] == 50.0

    def test_open_excluded(self):
        t = [{"status":"open","pnl_usd":999},{"status":"closed","pnl_usd":50}]
        assert tsp.compute_statistics(t)["total_trades"] == 1

    def test_safe_div_zero(self):
        assert tsp._safe_div(100,0) == 0.0

    def test_none_pnl(self):
        t = [{"status":"closed","pnl_usd":None}]
        s = tsp.compute_statistics(t)
        assert s["total_pnl"] == 0.0


class TestU3OpenFilter:
    def test_no_symbol(self):
        f = tsp.build_open_trades_filters("u1")
        assert f["status"]=="open" and "symbol" not in f

    def test_symbol_upper(self):
        assert tsp.build_open_trades_filters("u"," eurusd ")["symbol"] == "EURUSD"


class TestU4HistoryFilters:
    def test_dates_pushed(self):
        f = tsp.build_history_filters("u",from_date="2025-01-01",to_date="2025-12-31")
        assert f["opened_at__gte"]=="2025-01-01" and f["opened_at__lte"]=="2025-12-31"

    def test_no_dates(self):
        f = tsp.build_history_filters("u")
        assert "opened_at__gte" not in f


class TestU5Idempotency:
    def test_scoped(self):
        db = MagicMock(); db.select_one = AsyncMock(return_value={"id":"t1"})
        run(tsp.check_signal_idempotency(db,"s1","u1"))
        db.select_one.assert_called_once_with("trades",{"signal_id":"s1","user_id":"u1"})

    def test_db_error_returns_none(self):
        db = MagicMock(); db.select_one = AsyncMock(side_effect=Exception("down"))
        assert run(tsp.check_signal_idempotency(db,"s1","u1")) is None


# ===================== U-6..U-10 equity_protection_patch =====================

class MockEP:
    def __init__(self):
        self.is_initialized=False; self.state=MagicMock()
        self.state.high_water_mark=0.0; self.state.current_drawdown_percent=5.0
        self._halt=None; self._reset=False
    def initialize(self, b):
        self.is_initialized=True; self.state.high_water_mark=b
    def _set_halt(self, r): self._halt=r
    def reset_daily(self): self._reset=True


class TestU6SafeInit:
    def test_zero_uses_default(self):
        ep=MockEP(); epp.safe_initialize(ep,0.0)
        assert ep.state.high_water_mark == epp._DEFAULT_BALANCE

    def test_normal(self):
        ep=MockEP(); epp.safe_initialize(ep,5000.0)
        assert ep.state.high_water_mark == 5000.0

    def test_negative_uses_default(self):
        ep=MockEP(); epp.safe_initialize(ep,-1.0)
        assert ep.state.high_water_mark == epp._DEFAULT_BALANCE


class TestU7AutoInit:
    def test_auto_inits(self):
        ep=MockEP(); epp.auto_init_guard(ep,9500,10000)
        assert ep.is_initialized and ep.state.high_water_mark==10000

    def test_no_op_if_initialized(self):
        ep=MockEP(); ep.is_initialized=True; ep.state.high_water_mark=9999
        epp.auto_init_guard(ep,9500,10000)
        assert ep.state.high_water_mark==9999


class TestU10DailyReset:
    def test_resets_on_new_day(self):
        epp._last_reset_date="2020-01-01"
        ep=MockEP(); run(epp.maybe_reset_daily(ep))
        assert ep._reset

    def test_no_reset_same_day(self):
        today=datetime.now(timezone.utc).strftime("%Y-%m-%d")
        epp._last_reset_date=today
        ep=MockEP(); run(epp.maybe_reset_daily(ep))
        assert not ep._reset


# ===================== U-11..U-15 users =====================

from pydantic import ValidationError

_up = _load("backend/api/routes/users_patch.py")


class TestU11Strip:
    def test_removes_sensitive(self):
        row={"id":"u1","email":"a@b","full_name":"A","password_hash":"s","role":"admin","is_admin":True,"created_at":"now"}
        safe=_up._strip_sensitive(row)
        assert "password_hash" not in safe and "role" not in safe

    def test_keeps_safe_fields(self):
        row={k:"v" for k in _up._PROFILE_SAFE_FIELDS}; row["password_hash"]="x"
        assert set(_up._strip_sensitive(row).keys())==_up._PROFILE_SAFE_FIELDS


class TestU12UpdateProfile:
    def test_valid(self):
        r=_up.UpdateProfileRequest(full_name="Bob"); assert r.full_name=="Bob"

    def test_strips_whitespace(self):
        r=_up.UpdateProfileRequest(full_name="  Al  "); assert r.full_name=="Al"

    def test_empty_rejected(self):
        with pytest.raises(Exception): _up.UpdateProfileRequest(full_name="")


class TestU14Settings:
    def test_valid_theme(self):
        r=_up.UserSettingsRequest(theme="dark"); assert r.theme=="dark"

    def test_invalid_theme(self):
        with pytest.raises(Exception): _up.UserSettingsRequest(theme="pink")

    def test_risk_bounds(self):
        with pytest.raises(Exception): _up.UserSettingsRequest(default_risk_pct=0.0)
        with pytest.raises(Exception): _up.UserSettingsRequest(default_risk_pct=11.0)

    def test_only_allowed_keys(self):
        r=_up.UserSettingsRequest(language="fa",notifications_enabled=True)
        assert all(k in _up._SETTINGS_ALLOWED_KEYS for k in r.model_dump(exclude_none=True))


# ===================== U-16..U-20 security =====================

sp = _load("backend/core/security_patch.py")
_SECRET = "test_secret_32_chars_for_tests!!!"


class TestU16Cap:
    def test_normal(self):
        t=sp.create_access_token_safe({"sub":"u1"},_SECRET)
        p=sp.validate_access_token_safe(t,_SECRET)
        assert p["sub"]=="u1" and "jti" in p

    def test_cap(self):
        t=sp.create_access_token_safe({"sub":"u1"},_SECRET,expires_minutes=99999)
        import jwt
        p=jwt.decode(t,_SECRET,algorithms=["HS256"])
        assert (p["exp"]-p["iat"]) <= sp._MAX_ACCESS_EXPIRE_MINUTES*60+5

    def test_invalid(self):
        with pytest.raises(ValueError): sp.validate_access_token_safe("bad.token",_SECRET)


class TestU17Revocation:
    def test_revoked_rejected(self):
        import jwt
        t=sp.create_access_token_safe({"sub":"u1"},_SECRET)
        p=jwt.decode(t,_SECRET,algorithms=["HS256"])
        sp.revoke_token(p["jti"],float(p["exp"]))
        with pytest.raises(ValueError,match="revoked"): sp.validate_access_token_safe(t,_SECRET)

    def test_valid_passes(self):
        t=sp.create_access_token_safe({"sub":"u2"},_SECRET)
        assert sp.validate_access_token_safe(t,_SECRET)["sub"]=="u2"


class TestU19Refresh:
    def test_create(self):
        t,jti=sp.create_refresh_token_safe("u1",_SECRET)
        assert len(jti)==64
        p=sp.validate_refresh_token_safe(t,_SECRET)
        assert p["sub"]=="u1" and p["jti"]==jti and p["type"]=="refresh"

    def test_access_rejected(self):
        t=sp.create_access_token_safe({"sub":"u1"},_SECRET)
        with pytest.raises(ValueError,match="Not a refresh"): sp.validate_refresh_token_safe(t,_SECRET)

    def test_expired(self):
        t,_=sp.create_refresh_token_safe("u1",_SECRET,expires_days=-1)
        with pytest.raises(ValueError): sp.validate_refresh_token_safe(t,_SECRET)


# ===================== Integration =====================

class TestPhaseUIntegration:
    def test_full_token_lifecycle(self):
        import jwt
        t=sp.create_access_token_safe({"sub":"u-i"},_SECRET)
        p=sp.validate_access_token_safe(t,_SECRET)
        sp.revoke_token(p["jti"],float(p["exp"]))
        with pytest.raises(ValueError): sp.validate_access_token_safe(t,_SECRET)

    def test_stats_no_zero_div(self):
        for trades in [[],[{"status":"closed","pnl_usd":0.0}]]:
            s=tsp.compute_statistics(trades)
            assert isinstance(s["profit_factor"],float)

    def test_strip_idempotent(self):
        row={"id":"u1","password_hash":"s","email":"a@b","created_at":"now"}
        assert "password_hash" not in _up._strip_sensitive(_up._strip_sensitive(row))

    def test_settings_no_extra_keys(self):
        r=_up.UserSettingsRequest(language="de",theme="light")
        assert set(r.model_dump(exclude_none=True)).issubset(_up._SETTINGS_ALLOWED_KEYS)

    def test_refresh_jti_unique(self):
        _,j1=sp.create_refresh_token_safe("u",_SECRET)
        _,j2=sp.create_refresh_token_safe("u",_SECRET)
        assert j1 != j2
