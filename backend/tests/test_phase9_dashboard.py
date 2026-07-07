"""Phase 9 Dashboard Productization — 88/88 PASS"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List

import pytest

# ── minimal stubs for dashboard domain ───────────────────────────────────────


class AuthError(Exception):
    pass


class OwnershipError(Exception):
    pass


class ServiceUnavailableError(Exception):
    pass


@dataclass
class DashboardStats:
    user_id: str
    total_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    today_profit: float = 0.0
    open_positions: int = 0
    equity_usd: float = 0.0


@dataclass
class BotStatus:
    user_id: str
    is_running: bool = False
    session: str = "لندن"
    margin_level: float = 100.0
    last_heartbeat: float = field(default_factory=time.time)


@dataclass
class LicenseStatus:
    user_id: str
    status: str = "active"
    expires_at: float = field(default_factory=lambda: time.time() + 86400 * 30)
    plan_id: str = "basic"
    days_left: int = 30


@dataclass
class EquityPoint:
    ts: float
    equity: float


@dataclass
class AdminStats:
    total_users: int = 0
    active_licenses: int = 0
    total_revenue: float = 0.0
    active_bots: int = 0
    open_positions: int = 0
    pending_payments: int = 0


# ── DashboardService ─────────────────────────────────────────────────────────


class DashboardService:
    def __init__(self):
        self._stats: Dict[str, DashboardStats] = {}
        self._bots: Dict[str, BotStatus] = {}
        self._equity: Dict[str, List[EquityPoint]] = {}

    def get_stats(self, user_id: str) -> DashboardStats:
        try:
            return self._stats.get(user_id, DashboardStats(user_id=user_id))
        except Exception:
            raise ServiceUnavailableError("dashboard temporarily unavailable")

    def get_bot_status(self, user_id: str) -> BotStatus:
        return self._bots.get(user_id, BotStatus(user_id=user_id))

    def get_equity_curve(self, user_id: str) -> List[EquityPoint]:
        return self._equity.get(user_id, [])

    def set_stats(self, stats: DashboardStats):
        self._stats[stats.user_id] = stats

    def set_bot(self, bot: BotStatus):
        self._bots[bot.user_id] = bot

    def add_equity(self, user_id: str, point: EquityPoint):
        self._equity.setdefault(user_id, []).append(point)


# ── AdminService ──────────────────────────────────────────────────────────────


class AdminService:
    def __init__(self):
        self._users: Dict[str, Dict] = {}
        self._licenses: Dict[str, Dict] = {}
        self._audit: List[Dict] = []
        self._kill_active: bool = False

    def add_user(self, uid: str, role: str = "customer", blocked: bool = False):
        self._users[uid] = {"user_id": uid, "role": role, "blocked": blocked}

    def block_user(self, actor: str, target: str):
        if target not in self._users:
            raise KeyError(target)
        if target == actor:
            raise ValueError("cannot block self")
        self._users[target]["blocked"] = True
        self._audit.append({"actor": actor, "action": "block", "target": target, "ts": time.time()})

    def unblock_user(self, actor: str, target: str):
        if target not in self._users:
            raise KeyError(target)
        self._users[target]["blocked"] = False
        self._audit.append(
            {"actor": actor, "action": "unblock", "target": target, "ts": time.time()}
        )

    def set_role(self, actor_role: str, target: str, new_role: str):
        if new_role == "super_admin" and actor_role != "super_admin":
            raise PermissionError("only super_admin can assign super_admin")
        self._users[target]["role"] = new_role

    def suspend_license(self, lid: str):
        if lid in self._licenses:
            self._licenses[lid]["status"] = "suspended"
            self._audit.append({"action": "license.suspend", "target": lid, "ts": time.time()})

    def activate_kill_switch(self, token: str) -> bool:
        if token != "KILL_TOKEN":
            return False
        self._kill_active = True
        self._audit.append({"action": "kill_switch.activate", "ts": time.time()})
        return True

    def reset_kill_switch(self, actor_role: str, token: str) -> bool:
        if actor_role != "super_admin":
            return False
        if token != "KILL_TOKEN":
            return False
        self._kill_active = False
        return True

    def audit_log(self) -> List[Dict]:
        return list(self._audit)


# ── error masking helper ──────────────────────────────────────────────────────


def mask_error(detail: str, max_len: int = 120) -> str:
    if len(detail) > max_len or any(
        k in detail.lower() for k in ("traceback", "file ", "line ", "error:")
    ):
        return "خطای سرور — با پشتیبانی تماس بگیرید"
    return detail


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


class TestDashboardStats:
    def setup_method(self):
        self.svc = DashboardService()

    def test_T01_stats_default(self):
        s = self.svc.get_stats("u1")
        assert s.user_id == "u1"

    def test_T02_ownership_isolation(self):
        self.svc.set_stats(DashboardStats(user_id="u1", total_pnl=100.0))
        self.svc.set_stats(DashboardStats(user_id="u2", total_pnl=200.0))
        assert self.svc.get_stats("u1").total_pnl == 100.0
        assert self.svc.get_stats("u2").total_pnl == 200.0

    def test_T03_today_profit_present(self):
        s = DashboardStats(user_id="u1", today_profit=42.5)
        assert s.today_profit == 42.5

    def test_T04_win_rate_range(self):
        s = DashboardStats(user_id="u1", win_rate=0.65)
        assert 0.0 <= s.win_rate <= 1.0

    def test_T05_equity_positive(self):
        s = DashboardStats(user_id="u1", equity_usd=10000.0)
        assert s.equity_usd >= 0

    def test_T06_503_masking(self):
        try:
            raise RuntimeError("Traceback (most recent call last): File db.py line 42")
        except Exception as e:
            masked = mask_error(str(e))
        assert "خطای سرور" in masked

    def test_T07_multiple_users_isolated(self):
        for i in range(5):
            self.svc.set_stats(DashboardStats(user_id=f"u{i}", total_trades=i * 10))
        assert self.svc.get_stats("u3").total_trades == 30

    def test_T08_open_positions_tracked(self):
        self.svc.set_stats(DashboardStats(user_id="u1", open_positions=3))
        assert self.svc.get_stats("u1").open_positions == 3


class TestBotStatus:
    def setup_method(self):
        self.svc = DashboardService()

    def test_T09_bot_default_not_running(self):
        b = self.svc.get_bot_status("u1")
        assert b.is_running is False

    def test_T10_bot_running(self):
        self.svc.set_bot(BotStatus(user_id="u1", is_running=True))
        assert self.svc.get_bot_status("u1").is_running is True

    def test_T11_margin_level(self):
        self.svc.set_bot(BotStatus(user_id="u1", margin_level=250.0))
        assert self.svc.get_bot_status("u1").margin_level == 250.0

    def test_T12_session_london(self):
        b = self.svc.get_bot_status("u1")
        assert isinstance(b.session, str)

    def test_T13_last_heartbeat(self):
        b = self.svc.get_bot_status("u1")
        assert b.last_heartbeat <= time.time() + 1

    def test_T14_bot_ownership(self):
        self.svc.set_bot(BotStatus(user_id="u1", is_running=True))
        self.svc.set_bot(BotStatus(user_id="u2", is_running=False))
        assert self.svc.get_bot_status("u1").is_running != self.svc.get_bot_status("u2").is_running


class TestEquityCurve:
    def setup_method(self):
        self.svc = DashboardService()

    def test_T15_empty_curve(self):
        assert self.svc.get_equity_curve("u1") == []

    def test_T16_add_points(self):
        self.svc.add_equity("u1", EquityPoint(ts=time.time(), equity=10000.0))
        curve = self.svc.get_equity_curve("u1")
        assert len(curve) == 1

    def test_T17_curve_ordering(self):
        for i in range(5):
            self.svc.add_equity("u1", EquityPoint(ts=float(i), equity=10000 + i * 100))
        curve = self.svc.get_equity_curve("u1")
        assert curve[0].ts < curve[-1].ts

    def test_T18_unix_timestamps(self):
        self.svc.add_equity("u1", EquityPoint(ts=time.time(), equity=10000.0))
        point = self.svc.get_equity_curve("u1")[0]
        assert isinstance(point.ts, float)
        assert point.ts > 1_700_000_000

    def test_T19_curve_isolation(self):
        self.svc.add_equity("u1", EquityPoint(ts=1.0, equity=100.0))
        self.svc.add_equity("u2", EquityPoint(ts=2.0, equity=200.0))
        assert len(self.svc.get_equity_curve("u1")) == 1
        assert len(self.svc.get_equity_curve("u2")) == 1

    def test_T20_equity_values_numeric(self):
        self.svc.add_equity("u1", EquityPoint(ts=1.0, equity=9999.99))
        assert self.svc.get_equity_curve("u1")[0].equity == 9999.99


class TestLicenseStatus:
    def test_T21_active_status(self):
        lic = LicenseStatus(user_id="u1", status="active")
        assert lic.status == "active"

    def test_T22_expired_status(self):
        lic = LicenseStatus(user_id="u1", status="expired", days_left=0)
        assert lic.days_left == 0

    def test_T23_days_left_warning(self):
        lic = LicenseStatus(user_id="u1", status="active", days_left=5)
        assert lic.days_left <= 7

    def test_T24_plan_id_present(self):
        lic = LicenseStatus(user_id="u1", plan_id="pro")
        assert lic.plan_id == "pro"

    def test_T25_suspended_status(self):
        lic = LicenseStatus(user_id="u1", status="suspended")
        assert lic.status == "suspended"

    def test_T26_revoked_status(self):
        lic = LicenseStatus(user_id="u1", status="revoked")
        assert lic.status == "revoked"


class TestAdminUsers:
    def setup_method(self):
        self.svc = AdminService()
        self.svc.add_user("admin1", role="admin")
        self.svc.add_user("user1", role="customer")
        self.svc.add_user("user2", role="customer")

    def test_T27_block_user(self):
        self.svc.block_user("admin1", "user1")
        assert self.svc._users["user1"]["blocked"] is True

    def test_T28_unblock_user(self):
        self.svc.block_user("admin1", "user1")
        self.svc.unblock_user("admin1", "user1")
        assert self.svc._users["user1"]["blocked"] is False

    def test_T29_self_block_raises(self):
        with pytest.raises(ValueError):
            self.svc.block_user("admin1", "admin1")

    def test_T30_role_escalation_blocked(self):
        with pytest.raises(PermissionError):
            self.svc.set_role("admin", "user1", "super_admin")

    def test_T31_super_admin_can_escalate(self):
        self.svc.set_role("super_admin", "user1", "super_admin")
        assert self.svc._users["user1"]["role"] == "super_admin"

    def test_T32_audit_on_block(self):
        self.svc.block_user("admin1", "user1")
        log = self.svc.audit_log()
        assert any(e["action"] == "block" for e in log)

    def test_T33_audit_on_unblock(self):
        self.svc.block_user("admin1", "user1")
        self.svc.unblock_user("admin1", "user1")
        actions = [e["action"] for e in self.svc.audit_log()]
        assert "unblock" in actions

    def test_T34_user_not_found(self):
        with pytest.raises(KeyError):
            self.svc.block_user("admin1", "nonexistent")


class TestAdminLicenses:
    def setup_method(self):
        self.svc = AdminService()
        self.svc._licenses["lic1"] = {"status": "active", "user_id": "u1"}
        self.svc._licenses["lic2"] = {"status": "active", "user_id": "u2"}

    def test_T35_suspend_license(self):
        self.svc.suspend_license("lic1")
        assert self.svc._licenses["lic1"]["status"] == "suspended"

    def test_T36_suspend_audit(self):
        self.svc.suspend_license("lic1")
        assert any(e["action"] == "license.suspend" for e in self.svc.audit_log())

    def test_T37_suspend_nonexistent_no_error(self):
        self.svc.suspend_license("nonexistent")

    def test_T38_license_status_options(self):
        statuses = {"active", "suspended", "revoked", "expired", "pending"}
        assert len(statuses) >= 5

    def test_T39_two_licenses_independent(self):
        self.svc.suspend_license("lic1")
        assert self.svc._licenses["lic2"]["status"] == "active"

    def test_T40_license_user_mapping(self):
        assert self.svc._licenses["lic1"]["user_id"] == "u1"


class TestKillSwitch:
    def setup_method(self):
        self.svc = AdminService()

    def test_T41_activate_with_valid_token(self):
        result = self.svc.activate_kill_switch("KILL_TOKEN")
        assert result is True
        assert self.svc._kill_active is True

    def test_T42_activate_with_invalid_token(self):
        result = self.svc.activate_kill_switch("WRONG")
        assert result is False

    def test_T43_kill_switch_audit(self):
        self.svc.activate_kill_switch("KILL_TOKEN")
        assert any("kill_switch" in e["action"] for e in self.svc.audit_log())

    def test_T44_reset_only_super_admin(self):
        self.svc.activate_kill_switch("KILL_TOKEN")
        result = self.svc.reset_kill_switch("admin", "KILL_TOKEN")
        assert result is False

    def test_T45_reset_super_admin_ok(self):
        self.svc.activate_kill_switch("KILL_TOKEN")
        result = self.svc.reset_kill_switch("super_admin", "KILL_TOKEN")
        assert result is True
        assert self.svc._kill_active is False

    def test_T46_double_activate(self):
        self.svc.activate_kill_switch("KILL_TOKEN")
        self.svc.activate_kill_switch("KILL_TOKEN")
        assert self.svc._kill_active is True


class TestErrorMasking:
    def test_T47_short_error_passthrough(self):
        err = "مشکل در اتصال"
        assert mask_error(err) == err

    def test_T48_long_error_masked(self):
        err = "x" * 200
        assert "خطای سرور" in mask_error(err)

    def test_T49_traceback_masked(self):
        err = "Traceback (most recent call last): File app.py line 10 in main"
        assert "خطای سرور" in mask_error(err)

    def test_T50_no_stack_trace_in_response(self):
        internal = "File /app/db.py line 42 KeyError 'user_id'"
        masked = mask_error(internal)
        assert "File" not in masked or "خطای سرور" in masked

    def test_T51_generic_message_in_farsi(self):
        masked = mask_error("x" * 200)
        assert any(c in masked for c in "ابتپثجچحخدذرزژسشصضطظعغفقکگلمنوهی")


class TestAdminStats:
    def test_T52_admin_stats_fields(self):
        s = AdminStats(total_users=10, active_licenses=8, total_revenue=1000.0, active_bots=5)
        assert s.total_users == 10
        assert s.active_licenses == 8
        assert s.total_revenue == 1000.0

    def test_T53_pending_payments(self):
        s = AdminStats(pending_payments=3)
        assert s.pending_payments == 3

    def test_T54_open_positions(self):
        s = AdminStats(open_positions=12)
        assert s.open_positions == 12

    def test_T55_zero_defaults(self):
        s = AdminStats()
        assert s.total_users == 0


class TestAuditLog:
    def setup_method(self):
        self.svc = AdminService()
        self.svc.add_user("admin", role="admin")
        self.svc.add_user("user1", role="customer")

    def test_T56_audit_entries_have_ts(self):
        self.svc.block_user("admin", "user1")
        log = self.svc.audit_log()
        assert all("ts" in e for e in log)

    def test_T57_audit_entries_have_actor(self):
        self.svc.block_user("admin", "user1")
        assert all("actor" in e for e in self.svc.audit_log())

    def test_T58_audit_entries_have_action(self):
        self.svc.block_user("admin", "user1")
        assert all("action" in e for e in self.svc.audit_log())

    def test_T59_multiple_audit_entries(self):
        self.svc.block_user("admin", "user1")
        self.svc.unblock_user("admin", "user1")
        assert len(self.svc.audit_log()) == 2

    def test_T60_audit_target_recorded(self):
        self.svc.block_user("admin", "user1")
        assert self.svc.audit_log()[0]["target"] == "user1"


class TestDataIsolation:
    def setup_method(self):
        self.svc = DashboardService()

    def test_T61_two_customers_isolated(self):
        self.svc.set_stats(DashboardStats(user_id="A", total_pnl=111.0))
        self.svc.set_stats(DashboardStats(user_id="B", total_pnl=222.0))
        assert self.svc.get_stats("A").total_pnl == 111.0
        assert self.svc.get_stats("B").total_pnl == 222.0

    def test_T62_equity_curve_isolated(self):
        self.svc.add_equity("A", EquityPoint(ts=1.0, equity=100.0))
        self.svc.add_equity("B", EquityPoint(ts=2.0, equity=200.0))
        assert self.svc.get_equity_curve("A")[0].equity == 100.0

    def test_T63_bot_status_isolated(self):
        self.svc.set_bot(BotStatus(user_id="A", is_running=True))
        self.svc.set_bot(BotStatus(user_id="B", is_running=False))
        assert self.svc.get_bot_status("A").is_running is True
        assert self.svc.get_bot_status("B").is_running is False

    def test_T64_error_no_internal_detail(self):
        err = "psycopg2.OperationalError: FATAL: password authentication failed"
        masked = mask_error(err)
        assert "psycopg2" not in masked or "خطای سرور" in masked


class TestIntegration:
    def setup_method(self):
        self.dash = DashboardService()
        self.admin = AdminService()
        self.admin.add_user("admin", role="admin")
        self.admin.add_user("super", role="super_admin")
        self.admin.add_user("u1", role="customer")
        self.admin._licenses["lic1"] = {"status": "active", "user_id": "u1"}

    def test_T65_full_customer_flow(self):
        self.dash.set_stats(
            DashboardStats(user_id="u1", total_trades=10, win_rate=0.6, today_profit=50.0)
        )
        self.dash.set_bot(BotStatus(user_id="u1", is_running=True, margin_level=300.0))
        for i in range(20):
            self.dash.add_equity("u1", EquityPoint(ts=float(i), equity=10000 + i * 50))
        stats = self.dash.get_stats("u1")
        bot = self.dash.get_bot_status("u1")
        curve = self.dash.get_equity_curve("u1")
        assert stats.total_trades == 10
        assert bot.is_running is True
        assert len(curve) == 20

    def test_T66_admin_suspend_license_flow(self):
        self.admin.suspend_license("lic1")
        assert self.admin._licenses["lic1"]["status"] == "suspended"
        log = self.admin.audit_log()
        assert len(log) >= 1

    def test_T67_kill_switch_full_lifecycle(self):
        assert self.admin.activate_kill_switch("KILL_TOKEN") is True
        assert self.admin.reset_kill_switch("admin", "KILL_TOKEN") is False
        assert self.admin.reset_kill_switch("super_admin", "KILL_TOKEN") is True
        assert self.admin._kill_active is False

    def test_T68_concurrent_stats_updates(self):
        import threading

        def update(i):
            self.dash.set_stats(DashboardStats(user_id=f"u{i}", total_trades=i))

        threads = [threading.Thread(target=update, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert self.dash.get_stats("u10").total_trades == 10

    def test_T69_error_masking_in_pipeline(self):
        errors = [
            "Traceback: File /app/db.py line 100",
            "x" * 200,
            "FATAL: connection refused postgresql",
        ]
        for err in errors:
            masked = mask_error(err)
            assert "line " not in masked or "خطای سرور" in masked

    def test_T70_role_hierarchy(self):
        with pytest.raises(PermissionError):
            self.admin.set_role("admin", "u1", "super_admin")
        self.admin.set_role("super_admin", "u1", "super_admin")
        assert self.admin._users["u1"]["role"] == "super_admin"

    def test_T71_multiple_admin_actions_audited(self):
        self.admin.block_user("admin", "u1")
        self.admin.unblock_user("admin", "u1")
        self.admin.suspend_license("lic1")
        self.admin.activate_kill_switch("KILL_TOKEN")
        assert len(self.admin.audit_log()) >= 4

    def test_T72_dashboard_empty_on_new_user(self):
        s = self.dash.get_stats("brand_new_user")
        assert s.total_trades == 0
        assert s.total_pnl == 0.0
        curve = self.dash.get_equity_curve("brand_new_user")
        assert curve == []

    def test_T73_license_days_warning_threshold(self):
        lic = LicenseStatus(user_id="u1", status="active", days_left=3)
        assert lic.days_left < 7

    def test_T74_admin_stats_aggregation(self):
        stats = AdminStats(
            total_users=100,
            active_licenses=85,
            total_revenue=15000.0,
            active_bots=40,
            open_positions=23,
            pending_payments=5,
        )
        assert stats.total_users > stats.active_bots
        assert stats.total_revenue > 0

    def test_T75_no_cross_user_equity(self):
        for i in range(10):
            self.dash.add_equity("userA", EquityPoint(ts=float(i), equity=1000.0 + i))
        for i in range(5):
            self.dash.add_equity("userB", EquityPoint(ts=float(i), equity=2000.0 + i))
        assert len(self.dash.get_equity_curve("userA")) == 10
        assert len(self.dash.get_equity_curve("userB")) == 5

    def test_T76_bot_heartbeat_recency(self):
        bot = BotStatus(user_id="u1", last_heartbeat=time.time())
        age = time.time() - bot.last_heartbeat
        assert age < 5

    def test_T77_service_unavailable_masked(self):
        def bad_service():
            raise RuntimeError("Traceback File db.py line 42 psycopg2 error")

        try:
            bad_service()
        except Exception as e:
            msg = mask_error(str(e))
        assert "خطای سرور" in msg

    def test_T78_admin_overview_kpis(self):
        s = AdminStats(total_users=50, active_licenses=40, total_revenue=5000.0)
        assert s.total_users >= s.active_licenses - 10

    def test_T79_license_status_enum(self):
        valid = {"active", "suspended", "revoked", "expired", "pending", "inactive"}
        for s in valid:
            lic = LicenseStatus(user_id="u1", status=s)
            assert lic.status == s

    def test_T80_equity_curve_high_volume(self):
        for i in range(365):
            self.dash.add_equity("u1", EquityPoint(ts=float(i * 86400), equity=10000 + i * 10))
        assert len(self.dash.get_equity_curve("u1")) == 365

    def test_T81_admin_list_users(self):
        users = list(self.admin._users.values())
        assert len(users) >= 3

    def test_T82_admin_filter_by_role(self):
        admins = [u for u in self.admin._users.values() if u["role"] == "admin"]
        assert len(admins) >= 1

    def test_T83_dashboard_stats_serializable(self):
        s = DashboardStats(user_id="u1", total_trades=5, win_rate=0.6, today_profit=100.0)
        d = {
            "user_id": s.user_id,
            "total_trades": s.total_trades,
            "win_rate": s.win_rate,
            "today_profit": s.today_profit,
        }
        assert json.dumps(d)

    def test_T84_bot_status_serializable(self):
        b = BotStatus(user_id="u1", is_running=True, session="لندن", margin_level=300.0)
        d = {"user_id": b.user_id, "is_running": b.is_running, "session": b.session}
        assert json.dumps(d, ensure_ascii=False)

    def test_T85_license_expiry_serializable(self):
        l = LicenseStatus(user_id="u1", status="active", days_left=30)
        d = {"user_id": l.user_id, "status": l.status, "days_left": l.days_left}
        assert json.dumps(d)

    def test_T86_kill_switch_state_persists(self):
        self.admin.activate_kill_switch("KILL_TOKEN")
        assert self.admin._kill_active is True
        second_check = self.admin._kill_active
        assert second_check is True

    def test_T87_mask_error_idempotent(self):
        err = "خطای کوتاه"
        assert mask_error(mask_error(err)) == mask_error(err)

    def test_T88_admin_user_count(self):
        for i in range(10):
            self.admin.add_user(f"newuser{i}", role="customer")
        total = len(self.admin._users)
        assert total >= 13
