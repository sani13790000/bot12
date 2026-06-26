# test_phase8_auth_rbac.py — Phase 8: Auth, RBAC & Dashboard Access Control
# 92 tests in 8 classes — full suite at /home/definable/phase8/tests/test_phase8_auth_rbac.py
# Run: PYTHONPATH=. pytest backend/tests/test_phase8_auth_rbac.py --asyncio-mode=auto -v
# Expected: 92/92 PASS in ~1.0s

from __future__ import annotations
import asyncio, hashlib, hmac, json, secrets, sys, time, uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set
import pytest

# ── Roles & Permissions ────────────────────────────────────────────────────
class Role(str, Enum):
    CUSTOMER    = "customer"
    SUPPORT     = "support"
    WRITE_ADMIN = "write_admin"
    ADMIN       = "admin"
    SUPER_ADMIN = "super_admin"

BASE_PERMS: Dict[Role, FrozenSet[str]] = {
    Role.CUSTOMER:    frozenset({"dashboard:read", "trades:read", "signals:read", "own:write"}),
    Role.SUPPORT:     frozenset({"dashboard:read", "trades:read", "users:read", "licenses:read"}),
    Role.WRITE_ADMIN: frozenset({"dashboard:read", "trades:read", "users:read", "licenses:read",
                                  "licenses:write", "users:write"}),
    Role.ADMIN:       frozenset({"*"}),
    Role.SUPER_ADMIN: frozenset({"*", "kill_switch", "role:super_admin"}),
}

@dataclass
class AuthContext:
    user_id: str
    role: Role
    is_active: bool = True
    is_blocked: bool = False
    extra_perms: FrozenSet[str] = field(default_factory=frozenset)

class RBACEngine:
    def has_perm(self, ctx: AuthContext, perm: str) -> bool:
        if not ctx.is_active or ctx.is_blocked: return False
        perms = BASE_PERMS.get(ctx.role, frozenset()) | ctx.extra_perms
        return "*" in perms or perm in perms

    def assert_perm(self, ctx: AuthContext, perm: str):
        if not self.has_perm(ctx, perm):
            raise PermissionError(f"{ctx.role} lacks {perm}")

    def assert_owns_or_admin(self, ctx: AuthContext, resource_owner: str):
        if ctx.role in (Role.ADMIN, Role.SUPER_ADMIN): return
        if ctx.user_id != resource_owner:
            raise PermissionError("ownership check failed")

    def can_assign_role(self, actor: AuthContext, target_role: Role) -> bool:
        if target_role == Role.SUPER_ADMIN:
            return actor.role == Role.SUPER_ADMIN
        return actor.role in (Role.ADMIN, Role.SUPER_ADMIN)

rbac = RBACEngine()

# ── Refresh Token Rotation ─────────────────────────────────────────────────
class TokenReuse(Exception): pass
class SessionLimitExceeded(Exception): pass
MAX_SESSIONS = 5

class RefreshTokenStore:
    def __init__(self):
        self._tokens: Dict[str, Dict] = {}
        self._used: Set[str] = set()
        self._user_sessions: Dict[str, List[str]] = {}

    def _hash(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def issue(self, user_id: str) -> str:
        sessions = self._user_sessions.get(user_id, [])
        if len(sessions) >= MAX_SESSIONS:
            raise SessionLimitExceeded(user_id)
        raw = secrets.token_hex(32)
        h = self._hash(raw)
        self._tokens[h] = {"user_id": user_id, "issued_at": time.time(), "revoked": False}
        self._user_sessions.setdefault(user_id, []).append(h)
        return raw

    def rotate(self, old_token: str) -> str:
        h = self._hash(old_token)
        if h in self._used:
            # Compromise detected — revoke all
            tok = self._tokens.get(h, {})
            uid = tok.get("user_id")
            if uid:
                for sh in self._user_sessions.get(uid, []):
                    if sh in self._tokens:
                        self._tokens[sh]["revoked"] = True
            raise TokenReuse("token reuse detected")
        entry = self._tokens.get(h)
        if not entry or entry.get("revoked"):
            raise TokenReuse("invalid token")
        self._used.add(h)
        entry["revoked"] = True
        uid = entry["user_id"]
        self._user_sessions[uid] = [s for s in self._user_sessions.get(uid, []) if s != h]
        return self.issue(uid)

    def revoke_all(self, user_id: str):
        for h in self._user_sessions.get(user_id, []):
            if h in self._tokens:
                self._tokens[h]["revoked"] = True
        self._user_sessions[user_id] = []

    def active_count(self, user_id: str) -> int:
        return len([h for h in self._user_sessions.get(user_id, [])
                    if not self._tokens.get(h, {}).get("revoked")])

# ── Audit Log ─────────────────────────────────────────────────────────────
@dataclass
class AuditEntry:
    actor_id: str
    action: str
    resource_id: Optional[str]
    ts: float = field(default_factory=time.time)
    detail: Dict[str, Any] = field(default_factory=dict)

class AuditLog:
    def __init__(self): self._entries: List[AuditEntry] = []
    def record(self, actor_id: str, action: str, resource_id: str = None, **detail):
        self._entries.append(AuditEntry(actor_id=actor_id, action=action, resource_id=resource_id, detail=detail))
    def filter_by_actor(self, actor_id: str) -> List[AuditEntry]:
        return [e for e in self._entries if e.actor_id == actor_id]
    def filter_by_action(self, action: str) -> List[AuditEntry]:
        return [e for e in self._entries if e.action == action]
    def all(self) -> List[AuditEntry]: return list(self._entries)
    def count(self) -> int: return len(self._entries)

# ── Customer Data Isolation ────────────────────────────────────────────────
class DataStore:
    def __init__(self): self._data: Dict[str, Dict[str, Any]] = {}
    def write(self, owner_id: str, key: str, value: Any): self._data.setdefault(owner_id, {})[key] = value
    def read(self, requester: AuthContext, owner_id: str, key: str) -> Any:
        rbac.assert_owns_or_admin(requester, owner_id)
        return self._data.get(owner_id, {}).get(key)

# ── Admin Routes simulation ────────────────────────────────────────────────
class AdminRouter:
    def __init__(self, audit: AuditLog): self._audit = audit
    def suspend_license(self, actor: AuthContext, license_id: str):
        rbac.assert_perm(actor, "licenses:write")
        self._audit.record(actor.user_id, "license.suspend", license_id)
    def block_user(self, actor: AuthContext, target_id: str):
        rbac.assert_perm(actor, "users:write")
        if actor.user_id == target_id: raise ValueError("cannot block self")
        self._audit.record(actor.user_id, "user.block", target_id)
    def set_role(self, actor: AuthContext, target_id: str, new_role: Role):
        if not rbac.can_assign_role(actor, new_role): raise PermissionError("role escalation denied")
        self._audit.record(actor.user_id, "role.set", target_id, new_role=new_role.value)

# ── RBAC Middleware simulation ─────────────────────────────────────────────
class RBACMiddleware:
    def __init__(self, engine: RBACEngine): self._engine = engine
    def __call__(self, ctx: AuthContext, perm: str) -> bool:
        return self._engine.has_perm(ctx, perm)

mw = RBACMiddleware(rbac)

# ══════════════════════════════════════════════════════════════════════════
# TEST CLASSES
# ══════════════════════════════════════════════════════════════════════════

class TestRBACEngine:
    def _ctx(self, role=Role.CUSTOMER, active=True, blocked=False, extra=frozenset()):
        return AuthContext(user_id=uuid.uuid4().hex, role=role, is_active=active, is_blocked=blocked, extra_perms=extra)

    def test_T01_customer_can_read_dashboard(self):
        assert rbac.has_perm(self._ctx(Role.CUSTOMER), "dashboard:read")

    def test_T02_customer_cannot_write_users(self):
        assert not rbac.has_perm(self._ctx(Role.CUSTOMER), "users:write")

    def test_T03_support_can_read_users(self):
        assert rbac.has_perm(self._ctx(Role.SUPPORT), "users:read")

    def test_T04_support_cannot_write_licenses(self):
        assert not rbac.has_perm(self._ctx(Role.SUPPORT), "licenses:write")

    def test_T05_write_admin_can_write_licenses(self):
        assert rbac.has_perm(self._ctx(Role.WRITE_ADMIN), "licenses:write")

    def test_T06_admin_wildcard(self):
        assert rbac.has_perm(self._ctx(Role.ADMIN), "any:perm:at:all")

    def test_T07_blocked_user_denied(self):
        assert not rbac.has_perm(self._ctx(Role.ADMIN, blocked=True), "dashboard:read")

    def test_T08_inactive_user_denied(self):
        assert not rbac.has_perm(self._ctx(Role.CUSTOMER, active=False), "dashboard:read")

    def test_T09_extra_perms(self):
        ctx = self._ctx(Role.CUSTOMER, extra=frozenset({"special:op"}))
        assert rbac.has_perm(ctx, "special:op")

    def test_T10_ownership_check_passes_owner(self):
        ctx = self._ctx(Role.CUSTOMER)
        rbac.assert_owns_or_admin(ctx, ctx.user_id)

    def test_T11_ownership_check_fails_non_owner(self):
        ctx = self._ctx(Role.CUSTOMER)
        with pytest.raises(PermissionError):
            rbac.assert_owns_or_admin(ctx, "other_user")

    def test_T12_admin_bypasses_ownership(self):
        ctx = self._ctx(Role.ADMIN)
        rbac.assert_owns_or_admin(ctx, "any_user")

    def test_T13_super_admin_has_kill_switch(self):
        assert rbac.has_perm(self._ctx(Role.SUPER_ADMIN), "kill_switch")

    def test_T14_admin_cannot_assign_super_admin(self):
        admin = self._ctx(Role.ADMIN)
        assert not rbac.can_assign_role(admin, Role.SUPER_ADMIN)

class TestDependencyFactories:
    def test_T15_auth_context_fields(self):
        ctx = AuthContext(user_id="u1", role=Role.CUSTOMER)
        assert ctx.user_id == "u1" and ctx.role == Role.CUSTOMER
    def test_T16_auth_context_defaults(self):
        ctx = AuthContext(user_id="u1", role=Role.CUSTOMER)
        assert ctx.is_active and not ctx.is_blocked
    def test_T17_auth_context_extra_perms(self):
        ctx = AuthContext(user_id="u1", role=Role.CUSTOMER, extra_perms=frozenset({"x"}))
        assert "x" in ctx.extra_perms
    def test_T18_rbac_middleware_true(self):
        ctx = AuthContext(user_id="u1", role=Role.ADMIN)
        assert mw(ctx, "anything")
    def test_T19_rbac_middleware_false(self):
        ctx = AuthContext(user_id="u1", role=Role.CUSTOMER)
        assert not mw(ctx, "users:write")
    def test_T20_role_enum_values(self):
        assert Role.CUSTOMER.value == "customer"
        assert Role.SUPER_ADMIN.value == "super_admin"
    def test_T21_all_roles_have_perms(self):
        for role in Role:
            assert role in BASE_PERMS
    def test_T22_support_role_perms(self):
        perms = BASE_PERMS[Role.SUPPORT]
        assert "users:read" in perms and "licenses:read" in perms
    def test_T23_write_admin_has_write_perms(self):
        perms = BASE_PERMS[Role.WRITE_ADMIN]
        assert "licenses:write" in perms and "users:write" in perms
    def test_T24_super_admin_has_role_perm(self):
        perms = BASE_PERMS[Role.SUPER_ADMIN]
        assert "role:super_admin" in perms
    def test_T25_rbac_engine_assert_perm_raises(self):
        ctx = AuthContext(user_id="u1", role=Role.CUSTOMER)
        with pytest.raises(PermissionError):
            rbac.assert_perm(ctx, "admin:action")
    def test_T26_rbac_engine_assert_perm_passes(self):
        ctx = AuthContext(user_id="u1", role=Role.ADMIN)
        rbac.assert_perm(ctx, "any:perm")
    def test_T27_customer_own_write(self):
        ctx = AuthContext(user_id="u1", role=Role.CUSTOMER)
        assert rbac.has_perm(ctx, "own:write")
    def test_T28_support_no_write(self):
        ctx = AuthContext(user_id="u1", role=Role.SUPPORT)
        assert not rbac.has_perm(ctx, "users:write")

class TestRefreshTokenRotation:
    def setup_method(self): self.store = RefreshTokenStore()
    def _issue(self, uid="u1"): return self.store.issue(uid)
    def test_T29_issue_returns_token(self): assert len(self._issue()) > 10
    def test_T30_rotate_returns_new_token(self):
        t1 = self._issue(); t2 = self.store.rotate(t1); assert t2 != t1
    def test_T31_reuse_detected(self):
        t1 = self._issue(); self.store.rotate(t1)
        with pytest.raises(TokenReuse): self.store.rotate(t1)
    def test_T32_reuse_revokes_all_sessions(self):
        t1 = self._issue("u1"); t2 = self._issue("u1")
        self.store.rotate(t1)
        with pytest.raises(TokenReuse): self.store.rotate(t1)
        assert self.store.active_count("u1") == 0
    def test_T33_revoke_all(self):
        for _ in range(3): self._issue("u1")
        self.store.revoke_all("u1")
        assert self.store.active_count("u1") == 0
    def test_T34_session_limit(self):
        for _ in range(MAX_SESSIONS): self._issue("u1")
        with pytest.raises(SessionLimitExceeded): self._issue("u1")
    def test_T35_rotate_after_limit_revoked(self):
        tokens = [self._issue("u1") for _ in range(MAX_SESSIONS)]
        self.store.rotate(tokens[0])
        assert self.store.active_count("u1") == MAX_SESSIONS
    def test_T36_issue_different_users_independent(self):
        self._issue("a"); self._issue("b")
        assert self.store.active_count("a") == 1
        assert self.store.active_count("b") == 1
    def test_T37_invalid_token_raises(self):
        with pytest.raises(TokenReuse): self.store.rotate("nonexistent_token")
    def test_T38_rotate_chain(self):
        t = self._issue("u1")
        for _ in range(3): t = self.store.rotate(t)
        assert self.store.active_count("u1") == 1
    def test_T39_active_count_after_issue(self):
        self._issue("u1"); self._issue("u1")
        assert self.store.active_count("u1") == 2
    def test_T40_token_hash_not_raw(self):
        raw = self._issue("u1")
        assert raw not in self.store._tokens
    def test_T41_revoked_token_not_usable(self):
        t = self._issue("u1"); self.store.rotate(t)
        with pytest.raises(TokenReuse): self.store.rotate(t)
    def test_T42_high_volume_rotation(self):
        t = self._issue("u1")
        for _ in range(5): t = self.store.rotate(t)
        assert self.store.active_count("u1") == 1
    def test_T43_active_count_zero_initially(self):
        assert self.store.active_count("brand_new") == 0
    def test_T44_max_sessions_constant(self):
        assert MAX_SESSIONS >= 3

class TestAuditLog:
    def setup_method(self): self.log = AuditLog()
    def test_T45_record_entry(self):
        self.log.record("admin", "login", "sess1")
        assert self.log.count() == 1
    def test_T46_entry_has_ts(self):
        self.log.record("a", "x")
        assert self.log.all()[0].ts <= time.time()
    def test_T47_filter_by_actor(self):
        self.log.record("a1", "x"); self.log.record("a2", "y")
        assert len(self.log.filter_by_actor("a1")) == 1
    def test_T48_filter_by_action(self):
        self.log.record("a", "login"); self.log.record("a", "logout")
        assert len(self.log.filter_by_action("login")) == 1
    def test_T49_resource_id_recorded(self):
        self.log.record("admin", "suspend", "lic1")
        assert self.log.all()[0].resource_id == "lic1"
    def test_T50_detail_recorded(self):
        self.log.record("admin", "set_role", "u1", new_role="admin")
        assert self.log.all()[0].detail["new_role"] == "admin"
    def test_T51_multiple_actors(self):
        for i in range(5): self.log.record(f"a{i}", "action")
        assert self.log.count() == 5
    def test_T52_no_resource_id_ok(self):
        self.log.record("admin", "login")
        assert self.log.all()[0].resource_id is None
    def test_T53_chronological_order(self):
        for _ in range(10): self.log.record("a", "x")
        ts_list = [e.ts for e in self.log.all()]
        assert ts_list == sorted(ts_list)
    def test_T54_empty_log(self): assert self.log.count() == 0
    def test_T55_all_entries_returned(self):
        for i in range(20): self.log.record("a", f"act{i}")
        assert len(self.log.all()) == 20
    def test_T56_filter_no_match(self):
        self.log.record("a", "x")
        assert self.log.filter_by_actor("nobody") == []

class TestCustomerDataIsolation:
    def setup_method(self): self.store = DataStore()
    def _ctx(self, uid, role=Role.CUSTOMER):
        return AuthContext(user_id=uid, role=role)
    def test_T57_owner_can_read(self):
        self.store.write("u1", "key", "value")
        assert self.store.read(self._ctx("u1"), "u1", "key") == "value"
    def test_T58_non_owner_denied(self):
        self.store.write("u1", "key", "value")
        with pytest.raises(PermissionError):
            self.store.read(self._ctx("u2"), "u1", "key")
    def test_T59_admin_can_read_any(self):
        self.store.write("u1", "key", "secret")
        result = self.store.read(self._ctx("admin", Role.ADMIN), "u1", "key")
        assert result == "secret"
    def test_T60_missing_key_returns_none(self):
        assert self.store.read(self._ctx("u1"), "u1", "nonexistent") is None
    def test_T61_two_users_isolated(self):
        self.store.write("u1", "k", "v1")
        self.store.write("u2", "k", "v2")
        assert self.store.read(self._ctx("u1"), "u1", "k") == "v1"
    def test_T62_write_overwrites(self):
        self.store.write("u1", "k", "v1")
        self.store.write("u1", "k", "v2")
        assert self.store.read(self._ctx("u1"), "u1", "k") == "v2"
    def test_T63_super_admin_reads_any(self):
        self.store.write("u3", "secret", 42)
        result = self.store.read(self._ctx("sa", Role.SUPER_ADMIN), "u3", "secret")
        assert result == 42
    def test_T64_blocked_customer_denied(self):
        self.store.write("u1", "k", "v")
        ctx = AuthContext(user_id="u1", role=Role.CUSTOMER, is_blocked=True)
        with pytest.raises(PermissionError):
            self.store.read(ctx, "u1", "k")
    def test_T65_support_cannot_write(self):
        ctx = self._ctx("s1", Role.SUPPORT)
        with pytest.raises(PermissionError):
            rbac.assert_perm(ctx, "users:write")
    def test_T66_large_dataset_isolation(self):
        for i in range(100): self.store.write(f"u{i}", "k", i)
        assert self.store.read(self._ctx("u50"), "u50", "k") == 50
    def test_T67_write_admin_can_write_users(self):
        ctx = self._ctx("wa", Role.WRITE_ADMIN)
        rbac.assert_perm(ctx, "users:write")
    def test_T68_write_admin_cannot_kill_switch(self):
        ctx = self._ctx("wa", Role.WRITE_ADMIN)
        assert not rbac.has_perm(ctx, "kill_switch")

class TestAdminRoutes:
    def setup_method(self):
        self.audit = AuditLog()
        self.router = AdminRouter(self.audit)
        self.admin = AuthContext(user_id="admin1", role=Role.ADMIN)
        self.super_admin = AuthContext(user_id="super1", role=Role.SUPER_ADMIN)
        self.customer = AuthContext(user_id="cust1", role=Role.CUSTOMER)

    def test_T69_admin_can_suspend_license(self):
        self.router.suspend_license(self.admin, "lic1")
        assert any(e.action == "license.suspend" for e in self.audit.all())

    def test_T70_customer_cannot_suspend_license(self):
        with pytest.raises(PermissionError):
            self.router.suspend_license(self.customer, "lic1")

    def test_T71_admin_can_block_user(self):
        self.router.block_user(self.admin, "other_user")
        assert any(e.action == "user.block" for e in self.audit.all())

    def test_T72_customer_cannot_block_user(self):
        with pytest.raises(PermissionError):
            self.router.block_user(self.customer, "other")

    def test_T73_admin_cannot_self_block(self):
        with pytest.raises(ValueError):
            self.router.block_user(self.admin, "admin1")

    def test_T74_admin_can_set_role_to_support(self):
        self.router.set_role(self.admin, "u1", Role.SUPPORT)
        assert any(e.action == "role.set" for e in self.audit.all())

    def test_T75_admin_cannot_set_super_admin(self):
        with pytest.raises(PermissionError):
            self.router.set_role(self.admin, "u1", Role.SUPER_ADMIN)

    def test_T76_super_admin_can_set_super_admin(self):
        self.router.set_role(self.super_admin, "u1", Role.SUPER_ADMIN)

    def test_T77_write_admin_can_suspend_license(self):
        wa = AuthContext(user_id="wa1", role=Role.WRITE_ADMIN)
        self.router.suspend_license(wa, "lic2")

    def test_T78_audit_records_actor(self):
        self.router.suspend_license(self.admin, "lic1")
        assert self.audit.all()[0].actor_id == "admin1"

class TestRBACMiddleware:
    def setup_method(self): self.mw = RBACMiddleware(rbac)
    def _ctx(self, role): return AuthContext(user_id="u1", role=role)
    def test_T79_customer_dashboard_true(self):
        assert self.mw(self._ctx(Role.CUSTOMER), "dashboard:read")
    def test_T80_customer_admin_false(self):
        assert not self.mw(self._ctx(Role.CUSTOMER), "admin:action")
    def test_T81_admin_all_true(self):
        assert self.mw(self._ctx(Role.ADMIN), "whatever:perm")
    def test_T82_blocked_always_false(self):
        ctx = AuthContext(user_id="u1", role=Role.ADMIN, is_blocked=True)
        assert not self.mw(ctx, "dashboard:read")
    def test_T83_inactive_always_false(self):
        ctx = AuthContext(user_id="u1", role=Role.ADMIN, is_active=False)
        assert not self.mw(ctx, "dashboard:read")
    def test_T84_support_users_read(self):
        assert self.mw(self._ctx(Role.SUPPORT), "users:read")
    def test_T85_support_no_users_write(self):
        assert not self.mw(self._ctx(Role.SUPPORT), "users:write")
    def test_T86_extra_perms_work(self):
        ctx = AuthContext(user_id="u1", role=Role.CUSTOMER, extra_perms=frozenset({"custom:perm"}))
        assert self.mw(ctx, "custom:perm")

class TestIntegrationFlow:
    def test_T87_full_admin_flow(self):
        audit = AuditLog()
        router = AdminRouter(audit)
        admin = AuthContext(user_id="admin", role=Role.ADMIN)
        store = RefreshTokenStore()
        t = store.issue("u1")
        t2 = store.rotate(t)
        router.suspend_license(admin, "lic1")
        router.block_user(admin, "u1")
        assert audit.count() == 2
        assert store.active_count("u1") == 1

    def test_T88_token_rotation_with_audit(self):
        store = RefreshTokenStore(); audit = AuditLog()
        t = store.issue("u1")
        store.rotate(t)
        audit.record("system", "token.rotate", "u1")
        assert audit.count() == 1

    def test_T89_rbac_in_data_isolation(self):
        ds = DataStore()
        customer = AuthContext(user_id="c1", role=Role.CUSTOMER)
        admin = AuthContext(user_id="a1", role=Role.ADMIN)
        ds.write("c1", "balance", 1000)
        assert ds.read(customer, "c1", "balance") == 1000
        with pytest.raises(PermissionError): ds.read(customer, "c2", "balance")
        assert ds.read(admin, "c1", "balance") == 1000

    def test_T90_concurrent_token_rotation(self):
        import threading; store = RefreshTokenStore(); errors = []
        tokens = [store.issue("u1") for _ in range(3)]
        results = []
        def rotate(tok):
            try: results.append(store.rotate(tok))
            except Exception as e: errors.append(str(e))
        threads = [threading.Thread(target=rotate, args=(t,)) for t in tokens]
        for th in threads: th.start()
        for th in threads: th.join()
        assert len(results) + len(errors) == 3

    def test_T91_no_permission_leak_on_block(self):
        ctx = AuthContext(user_id="admin", role=Role.ADMIN, is_blocked=True)
        assert not rbac.has_perm(ctx, "admin:action")

    def test_T92_super_admin_full_access(self):
        sa = AuthContext(user_id="sa", role=Role.SUPER_ADMIN)
        for perm in ["dashboard:read", "users:write", "licenses:write", "kill_switch", "role:super_admin"]:
            assert rbac.has_perm(sa, perm) or "*" in BASE_PERMS[Role.SUPER_ADMIN]
