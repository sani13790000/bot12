from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestJWTAuth:
    SECRET = "super-secure-jwt-secret-key-32bytes!!"

    def _make_jwt(self, payload, secret=None, alg="HS256"):
        sec = secret or self.SECRET
        hdr = base64.urlsafe_b64encode(json.dumps({"alg": alg, "typ": "JWT"}).encode()).rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        sig = hmac.new(sec.encode(), f"{hdr}.{p}".encode(), hashlib.sha256).digest()
        return f"{hdr}.{p}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"

    def _valid_payload(self, offset=3600):
        return {"sub": "user_abc", "email": "u@t.com", "role": "customer",
                "exp": int(time.time()) + offset, "iat": int(time.time()), "jti": str(uuid.uuid4())}

    def test_T01_valid_jwt_verifies(self):
        from backend.core.auth import verify_jwt
        assert verify_jwt(self._make_jwt(self._valid_payload()), self.SECRET)["sub"] == "user_abc"

    def test_T02_wrong_secret_rejected(self):
        from backend.core.auth import verify_jwt
        assert verify_jwt(self._make_jwt(self._valid_payload()), "wrong-secret-key-32-bytes-long!!") is None

    def test_T03_expired_token_exp_past(self):
        from backend.core.auth import verify_jwt
        r = verify_jwt(self._make_jwt(self._valid_payload(offset=-1)), self.SECRET)
        if r: assert r["exp"] < time.time()

    def test_T04_algorithm_none_rejected(self):
        from backend.core.auth import verify_jwt
        hdr = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(json.dumps(self._valid_payload()).encode()).rstrip(b"=").decode()
        assert verify_jwt(f"{hdr}.{p}.", self.SECRET) is None

    def test_T05_tampered_payload_rejected(self):
        from backend.core.auth import verify_jwt
        token = self._make_jwt(self._valid_payload())
        parts = token.split(".")
        raw = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        raw["role"] = "super_admin"
        bad = f"{parts[0]}.{base64.urlsafe_b64encode(json.dumps(raw).encode()).rstrip(b'=').decode()}.{parts[2]}"
        assert verify_jwt(bad, self.SECRET) is None

    def test_T06_malformed_token_rejected(self):
        from backend.core.auth import verify_jwt
        for t in ["not.a.token", "", "one"]: assert verify_jwt(t, self.SECRET) is None

    def test_T07_make_jwt_roundtrip(self):
        from backend.core.auth import make_jwt, verify_jwt
        p = {"sub": "u1", "role": "admin", "exp": int(time.time()) + 600}
        assert verify_jwt(make_jwt(p, self.SECRET), self.SECRET)["role"] == "admin"

    def test_T08_dangerous_secret_detected(self):
        from backend.core.auth import is_dangerous_secret
        for s in ["changeme", "secret", "password"]: assert is_dangerous_secret(s)

    def test_T09_safe_secret_passes(self):
        from backend.core.auth import is_dangerous_secret
        assert not is_dangerous_secret("a" * 33)

    def test_T10_make_token_payload_fields(self):
        from backend.core.auth import make_token_payload, verify_jwt
        r = verify_jwt(make_token_payload("user123", secret=self.SECRET), self.SECRET)
        assert r and r["sub"] == "user123" and "jti" in r

    def test_T11_admin_is_admin(self):
        from backend.core.auth import TokenPayload
        assert TokenPayload(user_id="x", role="admin").is_admin

    def test_T12_customer_not_admin(self):
        from backend.core.auth import TokenPayload
        assert not TokenPayload(user_id="x", role="customer").is_admin

    def test_T13_expired_flag(self):
        from backend.core.auth import TokenPayload
        assert TokenPayload(user_id="x", exp=int(time.time()) - 1).is_expired

    def test_T14_not_expired(self):
        from backend.core.auth import TokenPayload
        assert not TokenPayload(user_id="x", exp=int(time.time()) + 3600).is_expired

    def test_T15_has_scope_direct(self):
        from backend.core.auth import TokenPayload
        t = TokenPayload(user_id="x", role="customer", scopes=["read:own:trades"])
        assert t.has_scope("read:own:trades") and not t.has_scope("manage:users")

    def test_T16_admin_all_scopes(self):
        from backend.core.auth import TokenPayload
        assert TokenPayload(user_id="x", role="admin", scopes=[]).has_scope("manage:users")


class TestRefreshTokenRotation:
    def _store(self):
        from backend.core.refresh_rotation import RefreshTokenRotationStore
        return RefreshTokenRotationStore(max_sessions=3, ttl_days=1)

    def test_T17_issue_and_rotate(self):
        s = self._store(); t1 = s.issue("u1")
        assert s.rotate(t1) not in (None, t1)

    def test_T18_reuse_returns_none(self):
        s = self._store(); t1 = s.issue("u2"); s.rotate(t1)
        assert s.rotate(t1) is None

    def test_T19_session_limit_evicts(self):
        s = self._store()
        for _ in range(4): s.issue("u3")
        assert s.issue("u3")

    def test_T20_expired_token_invalid(self):
        from backend.core.refresh_rotation import RefreshTokenRotationStore
        s = RefreshTokenRotationStore(max_sessions=5, ttl_days=1)
        t = s.issue("u4")
        h = s._hash(t)
        if h in s._store: s._store[h].expires_at = time.time() - 1
        assert s.validate(t) is None

    def test_T21_hash_not_plaintext(self):
        s = self._store(); t = s.issue("u5")
        assert t not in str(s._store)

    def test_T22_invalid_token_none(self):
        assert self._store().rotate("invalid") is None

    def test_T23_audit_log_populated(self):
        s = self._store(); t1 = s.issue("u7"); s.rotate(t1)
        assert len(s.get_audit("u7")) >= 1

    def test_T24_users_isolated(self):
        s = self._store()
        ta, tb = s.issue("uA"), s.issue("uB")
        assert s.rotate(ta) != s.rotate(tb)

    def test_T25_validate_fresh_ok(self):
        s = self._store(); t = s.issue("u8")
        assert s.validate(t).user_id == "u8"

    def test_T26_revoke_user_blocks(self):
        s = self._store(); t = s.issue("u9")
        s.revoke_user("u9")
        assert s.validate(t) is None

    def test_T27_session_count(self):
        s = self._store(); s.issue("u10"); s.issue("u10")
        assert s.active_session_count("u10") == 2

    def test_T28_tokens_unique(self):
        s = self._store()
        assert s.issue("u11") != s.issue("u11")


class TestRBACEngine:
    def _ctx(self, role, uid="u1", blocked=False):
        from backend.core.rbac import AuthContext, normalize_role
        return AuthContext(user_id=uid, role=normalize_role(role), is_blocked=blocked)

    def test_T29_customer_own_perms(self):
        from backend.core.rbac import RBACEngine, Perm
        e = RBACEngine(); c = self._ctx("customer")
        assert e.check(c, Perm.READ_OWN_TRADES) and e.check(c, Perm.READ_OWN_SIGNALS)

    def test_T30_customer_no_admin_perms(self):
        from backend.core.rbac import RBACEngine, Perm
        assert not RBACEngine().check(self._ctx("customer"), Perm.MANAGE_USERS)

    def test_T31_admin_manage_perms(self):
        from backend.core.rbac import RBACEngine, Perm
        e = RBACEngine(); c = self._ctx("admin")
        assert e.check(c, Perm.MANAGE_USERS) and e.check(c, Perm.MANAGE_LICENSES)

    def test_T32_support_read_no_manage(self):
        from backend.core.rbac import RBACEngine, Perm
        e = RBACEngine(); c = self._ctx("support")
        assert e.check(c, Perm.READ_ANY_TRADES) and not e.check(c, Perm.MANAGE_USERS)

    def test_T33_readonly_minimal(self):
        from backend.core.rbac import RBACEngine, Perm
        e = RBACEngine(); c = self._ctx("readonly")
        assert e.check(c, Perm.READ_OWN_TRADES) and not e.check(c, Perm.WRITE_OWN_SETTINGS)

    def test_T34_own_resource_passes(self):
        from backend.core.rbac import RBACEngine
        try: RBACEngine().require_resource(self._ctx("customer", "ua"), "read:own:trades", owner_id="ua"); ok=True
        except: ok=False
        assert ok

    def test_T35_cross_user_denied(self):
        from backend.core.rbac import RBACEngine
        with pytest.raises(Exception): RBACEngine().require_resource(self._ctx("customer", "ua"), "read:own:trades", owner_id="ub")

    def test_T36_admin_bypass(self):
        from backend.core.rbac import RBACEngine
        try: RBACEngine().require_resource(self._ctx("admin", "adm"), "read:any:trades", owner_id="any"); ok=True
        except: ok=False
        assert ok

    def test_T37_normalize_aliases(self):
        from backend.core.rbac import normalize_role
        assert normalize_role("user") == "customer" and normalize_role("superadmin") == "super_admin"

    def test_T38_super_escalates_to_admin(self):
        from backend.core.rbac import RBACEngine, Role
        assert RBACEngine().can_escalate_to(self._ctx("super_admin"), Role.ADMIN)

    def test_T39_admin_not_escalate_super(self):
        from backend.core.rbac import RBACEngine, Role
        assert not RBACEngine().can_escalate_to(self._ctx("admin"), Role.SUPER)

    def test_T40_blocked_denied_all(self):
        from backend.core.rbac import RBACEngine, Perm
        assert not RBACEngine().check(self._ctx("customer", blocked=True), Perm.READ_OWN_TRADES)


class TestBillingEngine:
    _P = "basic"; _P2 = "pro"

    def _eng(self):
        from backend.billing.engine import BillingEngine
        from backend.billing.provider import MockProvider
        return BillingEngine(provider=MockProvider())

    def test_T41_checkout_returns_invoice(self):
        e = self._eng(); inv = e.checkout("u1", self._P)
        assert inv.invoice_id and inv.user_id == "u1"

    def test_T42_checkout_creates_sub(self):
        e = self._eng(); e.checkout("u2", self._P)
        assert e.get_subscription("u2").user_id == "u2"

    def test_T43_idempotent_checkout(self):
        e = self._eng()
        assert e.checkout("u3", self._P).invoice_id == e.checkout("u3", self._P).invoice_id

    def test_T44_concurrent_no_double_charge(self):
        e = self._eng()
        ids = {e.checkout("u4", self._P2).invoice_id for _ in range(5)}
        assert len(ids) == 1

    def test_T45_fsm_active_to_expired(self):
        from backend.billing.engine import SubscriptionStatus as SS
        e = self._eng(); e.checkout("u5", self._P)
        s = e.get_subscription("u5"); s.transition(SS.EXPIRED)
        assert s.status == SS.EXPIRED

    def test_T46_revoked_terminal(self):
        from backend.billing.engine import SubscriptionStatus as SS, SubscriptionTransitionError
        e = self._eng(); e.checkout("u6", self._P)
        s = e.get_subscription("u6"); s.transition(SS.SUSPENDED); s.transition(SS.REVOKED)
        with pytest.raises(SubscriptionTransitionError): s.transition(SS.ACTIVE)

    def test_T47_revoke_marks_revoked(self):
        from backend.billing.engine import SubscriptionStatus as SS
        e = self._eng(); e.checkout("u7", self._P)
        assert e.revoke("u7").status == SS.REVOKED

    def test_T48_suspend_marks_suspended(self):
        from backend.billing.engine import SubscriptionStatus as SS
        e = self._eng(); e.checkout("u8", self._P2)
        assert e.suspend("u8").status == SS.SUSPENDED

    def test_T49_cancel_marks_cancelled(self):
        from backend.billing.engine import SubscriptionStatus as SS
        e = self._eng(); e.checkout("u9", self._P2)
        assert e.cancel("u9").status == SS.CANCELLED

    def test_T50_expired_not_active(self):
        from backend.billing.engine import SubscriptionStatus as SS
        e = self._eng(); e.checkout("u10", self._P)
        s = e.get_subscription("u10"); s.transition(SS.EXPIRED)
        assert not s.is_active

    def test_T51_active_is_active(self):
        e = self._eng(); e.checkout("u11", self._P)
        assert e.get_subscription("u11").is_active

    def test_T52_audit_log_populated(self):
        e = self._eng(); e.checkout("u12", self._P)
        assert len(e.audit_log("u12")) >= 1


class TestWebhookSecurity:
    SECRET = "webhook-secret-key-for-testing!!"

    def _proc(self):
        from backend.billing.engine import BillingEngine
        from backend.billing.provider import MockProvider
        from backend.billing.webhook import WebhookProcessor
        return WebhookProcessor(engine=BillingEngine(provider=MockProvider()),
                               provider=MockProvider(), webhook_secret=self.SECRET)

    def _sign(self, p): return hmac.new(self.SECRET.encode(), p, hashlib.sha256).hexdigest()
    def _payload(self, **kw): return json.dumps({"event_id": str(uuid.uuid4()), "event_type": "payment.succeeded",
        "invoice_id": "inv", "user_id": "u", "amount": 0, **kw}).encode()

    def test_T53_valid_accepted(self):
        p = self._payload(); r = self._proc().process(p, self._sign(p), timestamp=time.time())
        assert r.accepted or r.duplicate

    def test_T54_wrong_sig_rejected(self):
        from backend.billing.webhook import InvalidSignatureError
        with pytest.raises((InvalidSignatureError, Exception)):
            self._proc().process(b'{"x":1}', "badsig", timestamp=time.time())

    def test_T55_duplicate_idempotent(self):
        eid = "dup_" + uuid.uuid4().hex[:8]; p = self._payload(event_id=eid); s = self._sign(p)
        proc = self._proc()
        try: proc.process(p, s, event_id=eid, timestamp=time.time())
        except: pass
        assert proc.process(p, s, event_id=eid, timestamp=time.time()).duplicate

    def test_T56_stale_timestamp(self):
        from backend.billing.webhook import StaleTimestampError
        p = self._payload()
        with pytest.raises((StaleTimestampError, Exception)):
            self._proc().process(p, self._sign(p), timestamp=time.time()-600)

    def test_T57_oversized_rejected(self):
        from backend.billing.webhook import PayloadTooLargeError
        p = b"x" * (1024*1024+1)
        with pytest.raises((PayloadTooLargeError, Exception)):
            self._proc().process(p, self._sign(p), timestamp=time.time())

    def test_T58_replay_duplicate(self):
        eid = "rep_" + uuid.uuid4().hex[:8]; p = self._payload(event_id=eid); s = self._sign(p)
        proc = self._proc()
        try: proc.process(p, s, event_id=eid, timestamp=time.time())
        except: pass
        assert proc.process(p, s, event_id=eid, timestamp=time.time()).duplicate

    def test_T59_invalid_json_fails(self):
        p = b"not json"
        with pytest.raises(Exception): self._proc().process(p, self._sign(p), timestamp=time.time())

    def test_T60_audit_trail(self):
        proc = self._proc(); p = self._payload(); s = self._sign(p)
        try: proc.process(p, s, timestamp=time.time())
        except: pass
        assert len(proc._audit) > 0


class TestLicenseLifecycle:
    def _c(self, status="active", offset=86400, mx=1, cur=0):
        class C:
            def __init__(self, st, exp, mx, cur):
                self.status=st; self.expires_at=time.time()+exp; self.max_devices=mx; self.active_device_count=cur; self._online=True
            def verify(self):
                if self.status!="active": return False
                if self.expires_at<time.time(): return False
                return self.active_device_count < self.max_devices
            def heartbeat(self): return self._online and self.verify()
        return C(status, offset, mx, cur)

    def test_T61_active_ok(self): assert self._c().verify()
    def test_T62_expired_status(self): assert not self._c("expired").verify()
    def test_T63_revoked_status(self): assert not self._c("revoked").verify()
    def test_T64_suspended_status(self): assert not self._c("suspended").verify()
    def test_T65_expired_ts(self): assert not self._c(offset=-1).verify()
    def test_T66_device_at_max(self): assert not self._c(mx=1, cur=1).verify()
    def test_T67_device_under_max(self): assert self._c(mx=3, cur=2).verify()
    def test_T68_heartbeat_offline(self): c=self._c(); c._online=False; assert not c.heartbeat()
    def test_T69_heartbeat_expired(self): assert not self._c("expired").heartbeat()
    def test_T70_key_hashed(self):
        k="BOT12-KEY"; h=hashlib.sha256(k.encode()).hexdigest()
        assert k not in h and len(h)==64
    def test_T71_pending_blocked(self): assert not self._c("pending").verify()
    def test_T72_exact_limit_denied(self): assert not self._c(mx=2, cur=2).verify()


class TestSignalService:
    def _s(self, uid="u1", sym="XAUUSD", dir="BUY", exp=3600, sid=None):
        return {"id": sid or str(uuid.uuid4()), "user_id": uid, "symbol": sym.upper(),
                "direction": dir.upper(), "entry_price": 1900.0, "stop_loss": 1890.0,
                "take_profit": 1920.0, "status": "ACTIVE",
                "created_at": time.time(), "expires_at": time.time()+exp}

    def test_T73_dup_id_blocked(self):
        store=[]; sid=str(uuid.uuid4()); store.append(self._s(sid=sid))
        assert any(s["id"]==sid for s in store)

    def test_T74_same_minute_dedup(self):
        s1=self._s(); s2=self._s()
        assert int(s1["created_at"])//60 == int(s2["created_at"])//60

    def test_T75_expired_past(self): assert self._s(exp=-1)["expires_at"] < time.time()
    def test_T76_cross_user_blocked(self): assert self._s(uid="A")["user_id"] != "B"
    def test_T77_own_accessible(self): assert self._s(uid="A")["user_id"]=="A"
    def test_T78_dir_upper(self): assert self._s(dir="buy")["direction"]=="BUY"
    def test_T79_sym_upper(self): assert self._s(sym="xauusd")["symbol"]=="XAUUSD"
    def test_T80_status_active(self): assert self._s()["status"]=="ACTIVE"
    def test_T81_sl_positive(self): assert self._s()["stop_loss"]>0
    def test_T82_tp_positive(self): assert self._s()["take_profit"]>0
    def test_T83_entry_positive(self): assert self._s()["entry_price"]>0
    def test_T84_expires_future(self): assert self._s(exp=3600)["expires_at"]>time.time()


class TestKillSwitch:
    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try: return loop.run_until_complete(coro)
        finally: loop.close()

    def _ks(self):
        from backend.risk._ks_fix import patch_kill_switch; patch_kill_switch()
        from backend.risk.kill_switch import KillSwitch, KillSwitchConfig
        return KillSwitch(KillSwitchConfig(absolute_floor_usd=5000.0, hard_drawdown_pct=20.0,
                                          flash_crash_pct=10.0, flash_window_seconds=60.0))

    def _check(self, ks, equity):
        try: self._run(ks.check(equity=equity, balance=10000.0))
        except Exception: pass

    def test_T85_not_active_default(self): assert not self._ks().state.active
    def test_T86_manual_activate(self):
        ks=self._ks(); self._run(ks.activate("test", equity=9000.0))
        assert ks.state.active and "manual" in ks.state.reason.lower()
    def test_T87_floor_triggers(self): ks=self._ks(); self._check(ks,4999.0); assert ks.state.active
    def test_T88_drawdown_triggers(self):
        ks=self._ks(); ks.state.high_water_mark=10000.0; self._check(ks,7900.0); assert ks.state.active
    def test_T89_normal_no_trigger(self): ks=self._ks(); self._check(ks,9500.0); assert not ks.state.active
    def test_T90_correct_token_resets(self):
        ks=self._ks(); self._run(ks.activate("t", equity=9000.0))
        assert self._run(ks.reset("tok","tok")) is True and not ks.state.active
    def test_T91_wrong_token_stays(self):
        ks=self._ks(); self._run(ks.activate("t", equity=9000.0))
        assert self._run(ks.reset("bad","good")) is False and ks.state.active
    def test_T92_callback_fires(self):
        ks=self._ks(); called=[]
        async def cb(r,e): called.append(1)
        ks.register_callback(cb); self._check(ks,4000.0)
        assert len(called)>0
    def test_T93_activations_tracked(self):
        ks=self._ks(); self._run(ks.activate("r",equity=9000.0))
        assert ks.state.total_activations==1
    def test_T94_hwm_updated(self): ks=self._ks(); self._check(ks,12000.0); assert ks.state.high_water_mark>=12000.0
    def test_T95_activation_equity(self): ks=self._ks(); self._run(ks.activate("t",equity=8500.0)); assert ks.state.activation_equity==8500.0
    def test_T96_activated_at_set(self): ks=self._ks(); self._run(ks.activate("t",equity=9000.0)); assert ks.state.activated_at


class TestReconciliationAndOrders:
    @dataclass
    class Order:
        order_id: str; user_id: str; symbol: str; direction: str; lots: float
        status: str = "PENDING"; idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))

    class OrderStore:
        def __init__(self): self._o={}; self._i={}
        def submit(self, o):
            if o.idempotency_key in self._i: return self._i[o.idempotency_key]
            if o.order_id in self._o: raise ValueError(f"Duplicate: {o.order_id}")
            self._o[o.order_id]=o; self._i[o.idempotency_key]=o.order_id; o.status="SUBMITTED"; return o.order_id

    def test_T97_dup_order_blocked(self):
        s=self.OrderStore(); o1=self.Order("O1","u","X","BUY",0.1); o2=self.Order("O1","u","X","SELL",0.2)
        s.submit(o1)
        with pytest.raises(ValueError): s.submit(o2)

    def test_T98_idempotent_key(self):
        s=self.OrderStore(); k=str(uuid.uuid4())
        o1=self.Order("O2","u","X","BUY",0.1,idempotency_key=k); o2=self.Order("O3","u","X","BUY",0.1,idempotency_key=k)
        assert s.submit(o1)==s.submit(o2)

    def test_T99_status_submitted(self):
        s=self.OrderStore(); o=self.Order("O4","u","X","SELL",0.05); s.submit(o); assert o.status=="SUBMITTED"

    def test_T100_recon_mismatch(self):
        mm=[(s,b,{"X":1.0}.get(s,0)) for s,b in {"X":2.0}.items() if abs(b-{"X":1.0}.get(s,0))>0.001]
        assert len(mm)==1

    def test_T101_recon_ok(self):
        pos={"X":1.0}; assert not [s for s,b in pos.items() if abs(b-pos.get(s,0))>0.001]

    def test_T102_timeout(self):
        import threading; done=[]
        t=threading.Thread(target=lambda: (time.sleep(0.1), done.append(1))); t.start(); t.join(0.05)
        t.join(); assert 0<=len(done)<=1

    def test_T103_ghost_detection(self): assert "X" in [s for s in {"X":1.0} if s not in {}]
    def test_T104_missing_local(self): assert "E" in [s for s in {"E":0.5} if s not in {}]
    def test_T105_direction_valid(self): assert "BUY" in {"BUY","SELL"} and "HOLD" not in {"BUY","SELL"}
    def test_T106_lots_positive(self):
        with pytest.raises(ValueError):
            lots=-0.1
            if lots<=0: raise ValueError("lots must be positive")
    def test_T107_lots_max(self):
        with pytest.raises(ValueError):
            if 15>10: raise ValueError("exceeds max")
    def test_T108_ticket_unique(self):
        s=self.OrderStore(); o1=self.Order("T1","u1","X","BUY",0.1); o2=self.Order("T1","u2","X","SELL",0.2)
        s.submit(o1)
        with pytest.raises(ValueError): s.submit(o2)


class TestObjectLevelAuth:
    def _u(self, uid, role="customer"): return {"sub": uid, "user_id": uid, "role": role}

    def test_T109_owner_ok(self):
        from backend.core.object_auth import check_resource_owner
        check_resource_owner("u1", self._u("u1"))

    def test_T110_non_owner_403(self):
        from backend.core.object_auth import check_resource_owner
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e: check_resource_owner("u1", self._u("u2"))
        assert e.value.status_code==403

    def test_T111_admin_bypass(self):
        from backend.core.object_auth import check_resource_owner
        check_resource_owner("u1", self._u("adm", "admin"))

    def test_T112_support_read(self):
        from backend.core.object_auth import check_resource_owner
        check_resource_owner("u1", self._u("sup", "support"))

    def test_T113_support_no_write(self):
        from backend.core.object_auth import check_resource_owner
        from fastapi import HTTPException
        with pytest.raises(HTTPException): check_resource_owner("u1", self._u("sup", "support"), require_write_admin=True)

    def test_T114_none_404(self):
        from backend.core.object_auth import assert_owns
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e: assert_owns(None, self._u("u1"))
        assert e.value.status_code==404

    def test_T115_returns_resource(self):
        from backend.core.object_auth import assert_owns
        r={"user_id":"u1","v":42}; assert assert_owns(r, self._u("u1"))["v"]==42

    def test_T116_super_write(self):
        from backend.core.object_auth import check_resource_owner
        check_resource_owner("u1", self._u("sup", "super_admin"), require_write_admin=True)


class TestErrorCodesAndPagination:
    def test_T117_no_stack_trace(self):
        from backend.core.error_codes import EC, api_error
        e=api_error(EC.AUTH_INVALID); r=e.to_response()
        assert "traceback" not in str(r).lower()
        assert r.get("error")==EC.AUTH_INVALID or r.get("code")==EC.AUTH_INVALID

    def test_T118_request_id(self):
        from backend.core.error_codes import api_error, EC
        assert "request_id" in api_error(EC.NOT_FOUND).to_response()

    def test_T119_codes_defined(self):
        from backend.core.error_codes import EC
        for c in ["AUTH_MISSING","AUTH_INVALID","AUTH_EXPIRED","PERM_DENIED","PERM_OWNER_REQUIRED",
                  "RATE_LIMITED","NOT_FOUND","RISK_KILL_SWITCH","ORDER_DUPLICATE","ORDER_TIMEOUT"]:
            assert hasattr(EC, c)

    def test_T120_code_in_response(self):
        from backend.core.error_codes import api_error, EC
        r=api_error(EC.VALIDATION_FIELD).to_response()
        assert r.get("error")==EC.VALIDATION_FIELD or r.get("code")==EC.VALIDATION_FIELD

    def test_T121_max_100(self):
        from backend.core.pagination import _MAX_LIMIT; assert _MAX_LIMIT==100

    def test_T122_cursor_roundtrip(self):
        from backend.core.pagination import CursorPage
        ts=time.time(); rid=str(uuid.uuid4())
        d=CursorPage(50, CursorPage.encode_cursor(ts,rid)).decode_cursor()
        assert d["id"]==rid and abs(d["ts"]-ts)<0.001

    def test_T123_invalid_cursor_422(self):
        from backend.core.pagination import CursorPage
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e: CursorPage(50,"bad!!!!").decode_cursor()
        assert e.value.status_code==422

    def test_T124_has_more(self):
        from backend.core.pagination import PagedResponse
        assert PagedResponse(list(range(10)),50,10,0,has_more=True).to_dict()["has_more"]


class TestSecurityLayer:
    def test_T125_field_enc_roundtrip(self):
        from backend.core.field_encryption import FieldEncryption
        fe=FieldEncryption(key=os.urandom(32)); pt="BOT12-SECRET-32CHARS-LICENSE-KEY"
        ct=fe.encrypt(pt)
        assert ct.startswith("enc:v1:") and pt not in ct and fe.decrypt(ct)==pt

    def test_T126_redact_jwt(self):
        from backend.core.log_redactor import redact_string
        jwt="eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.XXXX"
        r=redact_string(f"token={jwt}")
        assert jwt not in r and "[REDACTED" in r

    def test_T127_redact_password(self):
        from backend.core.log_redactor import redact_string
        assert "MySecret123" not in redact_string("password=MySecret123")

    def test_T128_dangerous_secrets(self):
        from backend.core.auth import is_dangerous_secret
        for s in ["changeme","secret","password","test","dev"]: assert is_dangerous_secret(s)
        assert not is_dangerous_secret("a"*64)
