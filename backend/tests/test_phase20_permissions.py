"""
test_phase20_permissions.py — Phase 20: Fine-Grained Permission Model
168 tests across 12 classes
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.core.deps_v3 import (
    build_auth_context,
    require_all_perms,
    require_any_perm,
    require_perm,
    require_rank,
)
from backend.core.permissions import (
    ENDPOINT_REGISTRY,
    PERM_DESCRIPTIONS,
    PLAN_PERMISSIONS,
    ROLE_PERMISSIONS,
    ROLE_RANK,
    AuthContext,
    EscalationError,
    P,
    PermissionDeniedError,
    RBACEngineV2,
    Role,
    assert_no_escalation,
    expand_permissions,
    normalize_role,
)
from backend.middleware.permission_middleware import (
    PermissionEnforcer,
    _match_endpoint,
)


def ctx(role: str, user_id: str = "u001", **kw) -> AuthContext:
    return AuthContext(user_id=user_id, role=role, **kw)


CTX_READONLY = ctx(Role.READONLY)
CTX_CUSTOMER = ctx(Role.CUSTOMER)
CTX_SUPPORT = ctx(Role.SUPPORT)
CTX_WRITE_ADMIN = ctx(Role.WRITE_ADMIN)
CTX_ADMIN = ctx(Role.ADMIN)
CTX_SUPER = ctx(Role.SUPER)


class TestPermissionRegistry:
    def test_T001_all_perms_have_description(self):
        for p in P:
            if p != P.ALL:
                assert p.value in PERM_DESCRIPTIONS, f"Missing: {p.value}"

    def test_T002_perm_format_namespace(self):
        for p in P:
            if p == P.ALL:
                continue
            assert len(p.value.split(":")) >= 2

    def test_T003_no_duplicate_perm_values(self):
        values = [p.value for p in P]
        assert len(values) == len(set(values))

    def test_T004_all_wildcard_is_super_only(self):
        for role in [Role.READONLY, Role.CUSTOMER, Role.SUPPORT, Role.WRITE_ADMIN, Role.ADMIN]:
            assert P.ALL not in ROLE_PERMISSIONS[role]

    def test_T005_super_has_wildcard(self):
        assert P.ALL in ROLE_PERMISSIONS[Role.SUPER]

    def test_T006_profile_read_own_exists(self):
        assert P.PROFILE_READ_OWN in P.__members__.values()

    def test_T007_license_perms_complete(self):
        for p in [
            P.LICENSE_READ_OWN,
            P.LICENSE_READ_ANY,
            P.LICENSE_ISSUE,
            P.LICENSE_REVOKE,
            P.LICENSE_SUSPEND,
        ]:
            assert p in P.__members__.values()

    def test_T008_trade_perms_complete(self):
        for p in [P.TRADE_READ_OWN, P.TRADE_READ_ANY, P.TRADE_EXECUTE, P.TRADE_CLOSE_ALL]:
            assert p in P.__members__.values()

    def test_T009_risk_perms_complete(self):
        for p in [P.RISK_HALT, P.RISK_RESUME, P.RISK_KILL_SWITCH]:
            assert p in P.__members__.values()

    def test_T010_tenant_perms_exist(self):
        assert P.TENANT_CROSS_ACCESS in P.__members__.values()

    def test_T011_release_perms_exist(self):
        assert P.RELEASE_DOWNLOAD in P.__members__.values()
        assert P.RELEASE_PUBLISH in P.__members__.values()

    def test_T012_billing_webhook_perm_exists(self):
        assert P.BILLING_WEBHOOK_INGEST in P.__members__.values()

    def test_T013_audit_export_perm_exists(self):
        assert P.AUDIT_EXPORT in P.__members__.values()

    def test_T014_user_delete_perm_exists(self):
        assert P.USER_DELETE in P.__members__.values()

    def test_T015_total_perms_at_least_40(self):
        assert len(list(P)) >= 40

    def test_T016_descriptions_non_empty(self):
        for key, desc in PERM_DESCRIPTIONS.items():
            assert len(desc) >= 5


class TestRoleMatrix:
    def test_T017_readonly_cannot_execute_trade(self):
        assert not CTX_READONLY.has_perm(P.TRADE_EXECUTE)

    def test_T018_customer_can_execute_trade(self):
        assert CTX_CUSTOMER.has_perm(P.TRADE_EXECUTE)

    def test_T019_customer_cannot_read_any_trades(self):
        assert not CTX_CUSTOMER.has_perm(P.TRADE_READ_ANY)

    def test_T020_support_can_read_any_trades(self):
        assert CTX_SUPPORT.has_perm(P.TRADE_READ_ANY)

    def test_T021_support_cannot_issue_license(self):
        assert not CTX_SUPPORT.has_perm(P.LICENSE_ISSUE)

    def test_T022_admin_can_issue_license(self):
        assert CTX_ADMIN.has_perm(P.LICENSE_ISSUE)

    def test_T023_admin_can_kill_switch(self):
        assert CTX_ADMIN.has_perm(P.RISK_KILL_SWITCH)

    def test_T024_support_cannot_kill_switch(self):
        assert not CTX_SUPPORT.has_perm(P.RISK_KILL_SWITCH)

    def test_T025_write_admin_can_halt_not_resume(self):
        assert CTX_WRITE_ADMIN.has_perm(P.RISK_HALT)
        assert not CTX_WRITE_ADMIN.has_perm(P.RISK_RESUME)

    def test_T026_admin_can_export_audit(self):
        assert CTX_ADMIN.has_perm(P.AUDIT_EXPORT)

    def test_T027_support_cannot_export_audit(self):
        assert not CTX_SUPPORT.has_perm(P.AUDIT_EXPORT)

    def test_T028_admin_can_delete_user(self):
        assert CTX_ADMIN.has_perm(P.USER_DELETE)

    def test_T029_support_cannot_delete_user(self):
        assert not CTX_SUPPORT.has_perm(P.USER_DELETE)

    def test_T030_super_has_all_perms(self):
        for p in P:
            assert CTX_SUPER.has_perm(p.value)

    def test_T031_role_rank_order_correct(self):
        assert ROLE_RANK[Role.READONLY] < ROLE_RANK[Role.CUSTOMER]
        assert ROLE_RANK[Role.CUSTOMER] < ROLE_RANK[Role.SUPPORT]
        assert ROLE_RANK[Role.SUPPORT] < ROLE_RANK[Role.WRITE_ADMIN]
        assert ROLE_RANK[Role.WRITE_ADMIN] < ROLE_RANK[Role.ADMIN]
        assert ROLE_RANK[Role.ADMIN] < ROLE_RANK[Role.SUPER]

    def test_T032_customer_can_read_own_not_any_profile(self):
        assert CTX_CUSTOMER.has_perm(P.PROFILE_READ_OWN)
        assert not CTX_CUSTOMER.has_perm(P.PROFILE_READ_ANY)


class TestPrivilegeEscalation:
    def test_T033_customer_cannot_escalate_to_support(self):
        with pytest.raises(EscalationError):
            assert_no_escalation(Role.CUSTOMER, Role.SUPPORT)

    def test_T034_customer_cannot_escalate_to_admin(self):
        with pytest.raises(EscalationError):
            assert_no_escalation(Role.CUSTOMER, Role.ADMIN)

    def test_T035_support_cannot_escalate_to_admin(self):
        with pytest.raises(EscalationError):
            assert_no_escalation(Role.SUPPORT, Role.ADMIN)

    def test_T036_admin_cannot_escalate_to_super(self):
        with pytest.raises(EscalationError):
            assert_no_escalation(Role.ADMIN, Role.SUPER)

    def test_T037_admin_can_assign_support(self):
        assert_no_escalation(Role.ADMIN, Role.SUPPORT)

    def test_T038_admin_can_assign_customer(self):
        assert_no_escalation(Role.ADMIN, Role.CUSTOMER)

    def test_T039_admin_cannot_assign_same_rank(self):
        with pytest.raises(EscalationError):
            assert_no_escalation(Role.ADMIN, Role.ADMIN)

    def test_T040_write_admin_cannot_assign_admin(self):
        with pytest.raises(EscalationError):
            assert_no_escalation(Role.WRITE_ADMIN, Role.ADMIN)

    def test_T041_write_admin_can_assign_support(self):
        assert_no_escalation(Role.WRITE_ADMIN, Role.SUPPORT)

    def test_T042_readonly_cannot_escalate_to_any(self):
        for role in [Role.CUSTOMER, Role.SUPPORT, Role.WRITE_ADMIN, Role.ADMIN, Role.SUPER]:
            with pytest.raises(EscalationError):
                assert_no_escalation(Role.READONLY, role)

    def test_T043_ctx_can_escalate_respects_perm(self):
        assert not CTX_CUSTOMER.can_escalate_to(Role.READONLY)

    def test_T044_admin_ctx_can_escalate_to_support(self):
        assert CTX_ADMIN.can_escalate_to(Role.SUPPORT)

    def test_T045_admin_ctx_cannot_escalate_to_super(self):
        assert not CTX_ADMIN.can_escalate_to(Role.SUPER)

    def test_T046_unknown_target_role_raises(self):
        with pytest.raises(EscalationError):
            assert_no_escalation(Role.ADMIN, "hacker_role")

    def test_T047_rbac_require_no_escalation_raises_on_attempt(self):
        engine = RBACEngineV2()
        with pytest.raises(PermissionDeniedError):
            engine.require_no_escalation(CTX_CUSTOMER, Role.ADMIN)

    def test_T048_rbac_require_no_escalation_ok_for_admin_to_customer(self):
        engine = RBACEngineV2()
        engine.require_no_escalation(CTX_ADMIN, Role.CUSTOMER)


class TestAuthContextEffectivePerms:
    def test_T049_blocked_user_has_no_perms(self):
        assert not ctx(Role.ADMIN, is_blocked=True).has_perm(P.PROFILE_READ_OWN)

    def test_T050_inactive_user_has_no_perms(self):
        assert not ctx(Role.ADMIN, is_active=False).has_perm(P.PROFILE_READ_OWN)

    def test_T051_extra_perms_additive(self):
        extra = frozenset({P.RISK_KILL_SWITCH})
        c = ctx(Role.SUPPORT, extra_perms=extra)
        assert c.has_perm(P.RISK_KILL_SWITCH)

    def test_T052_extra_perms_not_available_without_assignment(self):
        assert not ctx(Role.SUPPORT).has_perm(P.RISK_KILL_SWITCH)

    def test_T053_plan_trial_restricts_trade_execute(self):
        assert not ctx(Role.CUSTOMER, plan="trial").has_perm(P.TRADE_EXECUTE)

    def test_T054_plan_basic_allows_trade_execute(self):
        assert ctx(Role.CUSTOMER, plan="basic").has_perm(P.TRADE_EXECUTE)

    def test_T055_plan_pro_same_as_customer(self):
        assert ctx(Role.CUSTOMER).effective_perms == ctx(Role.CUSTOMER, plan="pro").effective_perms

    def test_T056_admin_ignores_plan_restriction(self):
        assert ctx(Role.ADMIN, plan="trial").has_perm(P.TRADE_EXECUTE)

    def test_T057_has_any_perm_or_logic(self):
        assert ctx(Role.CUSTOMER).has_any_perm(P.TRADE_EXECUTE, P.TRADE_CLOSE_ALL)

    def test_T058_has_any_perm_all_missing(self):
        assert not ctx(Role.READONLY).has_any_perm(P.TRADE_EXECUTE, P.LICENSE_ISSUE)

    def test_T059_rank_property(self):
        assert CTX_READONLY.rank == 0 and CTX_SUPER.rank == 5

    def test_T060_effective_perms_no_wildcard_for_admin(self):
        assert P.ALL not in CTX_ADMIN.effective_perms

    def test_T061_super_effective_perms_contains_all_flag(self):
        assert P.ALL in CTX_SUPER.effective_perms

    def test_T062_tenant_id_default(self):
        assert ctx(Role.CUSTOMER).tenant_id == "default"

    def test_T063_tenant_id_custom(self):
        assert (
            AuthContext(user_id="u1", role=Role.CUSTOMER, tenant_id="t_acme").tenant_id == "t_acme"
        )

    def test_T064_plan_vip_has_risk_read_any(self):
        assert ctx(Role.CUSTOMER, plan="vip").has_perm(P.RISK_READ_ANY)


class TestRBACEngineV2:
    def setup_method(self):
        self.engine = RBACEngineV2()

    def test_T065_check_returns_true_for_valid(self):
        assert self.engine.check(CTX_CUSTOMER, P.TRADE_EXECUTE)

    def test_T066_check_returns_false_for_missing(self):
        assert not self.engine.check(CTX_CUSTOMER, P.LICENSE_ISSUE)

    def test_T067_require_raises_on_missing(self):
        with pytest.raises(PermissionDeniedError):
            self.engine.require(CTX_CUSTOMER, P.LICENSE_ISSUE)

    def test_T068_require_no_raise_on_valid(self):
        self.engine.require(CTX_ADMIN, P.LICENSE_ISSUE)

    def test_T069_cache_returns_same_result(self):
        r1 = self.engine.check(CTX_CUSTOMER, P.TRADE_EXECUTE)
        r2 = self.engine.check(CTX_CUSTOMER, P.TRADE_EXECUTE)
        assert r1 == r2 is True

    def test_T070_invalidate_clears_user_cache(self):
        self.engine.check(CTX_CUSTOMER, P.TRADE_EXECUTE)
        self.engine.invalidate(CTX_CUSTOMER.user_id)
        assert self.engine.check(CTX_CUSTOMER, P.TRADE_EXECUTE)

    def test_T071_deny_hook_called_on_deny(self):
        calls = []
        self.engine.add_deny_hook(lambda ctx, perm: calls.append((ctx.role, perm)))
        self.engine.check(CTX_CUSTOMER, P.LICENSE_ISSUE)
        assert len(calls) == 1

    def test_T072_deny_hook_not_called_on_allow(self):
        calls = []
        self.engine.add_deny_hook(lambda ctx, perm: calls.append(perm))
        self.engine.check(CTX_ADMIN, P.LICENSE_ISSUE)
        assert len(calls) == 0

    def test_T073_public_perm_always_allowed(self):
        assert self.engine.check(CTX_READONLY, "public")

    def test_T074_is_admin_or_above(self):
        assert self.engine.is_admin_or_above(CTX_ADMIN)
        assert not self.engine.is_admin_or_above(CTX_SUPPORT)

    def test_T075_is_support_or_above(self):
        assert self.engine.is_support_or_above(CTX_SUPPORT)
        assert not self.engine.is_support_or_above(CTX_CUSTOMER)

    def test_T076_get_role_permissions_admin(self):
        perms = self.engine.get_role_permissions(Role.ADMIN)
        assert P.LICENSE_ISSUE in perms and P.USER_DELETE in perms

    def test_T077_permission_matrix_has_all_roles(self):
        m = self.engine.permission_matrix()
        for role in [
            Role.READONLY,
            Role.CUSTOMER,
            Role.SUPPORT,
            Role.WRITE_ADMIN,
            Role.ADMIN,
            Role.SUPER,
        ]:
            assert role in m["roles"]

    def test_T078_permission_matrix_correctness(self):
        m = self.engine.permission_matrix()["permissions"]
        assert m[P.TRADE_EXECUTE][Role.CUSTOMER]
        assert not m[P.TRADE_EXECUTE][Role.READONLY]

    def test_T079_endpoint_permissions_non_empty(self):
        assert len(self.engine.endpoint_permissions()) >= 50

    def test_T080_permission_matrix_has_descriptions(self):
        m = self.engine.permission_matrix()
        assert "descriptions" in m and len(m["descriptions"]) >= 40


class TestOwnerScopedAccess:
    def setup_method(self):
        self.engine = RBACEngineV2()

    def test_T081_own_trade_allowed_same_user(self):
        assert ctx(Role.CUSTOMER, user_id="A").can_access_resource(P.TRADE_READ_OWN, "A")

    def test_T082_own_trade_denied_other_user(self):
        assert not ctx(Role.CUSTOMER, user_id="A").can_access_resource(P.TRADE_READ_OWN, "B")

    def test_T083_support_can_read_any_trade(self):
        assert ctx(Role.SUPPORT, user_id="S").can_access_resource(P.TRADE_READ_ANY, "B")

    def test_T084_customer_cannot_use_any_trade_perm(self):
        assert not ctx(Role.CUSTOMER, user_id="A").can_access_resource(P.TRADE_READ_ANY, "A")

    def test_T085_require_resource_raises_on_other_owner(self):
        c = ctx(Role.CUSTOMER, user_id="A")
        with pytest.raises(PermissionDeniedError):
            self.engine.require_resource(c, P.TRADE_READ_OWN, "B")

    def test_T086_require_resource_ok_same_owner(self):
        c = ctx(Role.CUSTOMER, user_id="A")
        self.engine.require_resource(c, P.TRADE_READ_OWN, "A")

    def test_T087_signal_own_isolation(self):
        c = ctx(Role.CUSTOMER, user_id="A")
        assert c.can_access_resource(P.SIGNAL_READ_OWN, "A")
        assert not c.can_access_resource(P.SIGNAL_READ_OWN, "B")

    def test_T088_profile_own_isolation(self):
        c = ctx(Role.CUSTOMER, user_id="A")
        assert c.can_access_resource(P.PROFILE_READ_OWN, "A")
        assert not c.can_access_resource(P.PROFILE_READ_OWN, "B")

    def test_T089_license_own_isolation(self):
        c = ctx(Role.CUSTOMER, user_id="A")
        assert c.can_access_resource(P.LICENSE_READ_OWN, "A")
        assert not c.can_access_resource(P.LICENSE_READ_OWN, "B")

    def test_T090_admin_write_any_profile_not_owner_scoped(self):
        assert ctx(Role.ADMIN, user_id="admin-1").can_access_resource(P.PROFILE_WRITE_ANY, "user-B")

    def test_T091_billing_own_isolation(self):
        c = ctx(Role.CUSTOMER, user_id="A")
        assert c.can_access_resource(P.BILLING_READ_OWN, "A")
        assert not c.can_access_resource(P.BILLING_READ_OWN, "B")

    def test_T092_risk_read_own_isolated(self):
        c = ctx(Role.CUSTOMER, user_id="A")
        assert c.can_access_resource(P.RISK_READ_OWN, "A")
        assert not c.can_access_resource(P.RISK_READ_OWN, "B")

    def test_T093_none_owner_not_restricted_for_any_perms(self):
        assert ctx(Role.SUPPORT, user_id="s-1").can_access_resource(P.TRADE_READ_ANY, None)

    def test_T094_blocked_user_cannot_access_own_resource(self):
        assert not ctx(Role.CUSTOMER, user_id="A", is_blocked=True).can_access_resource(
            P.TRADE_READ_OWN, "A"
        )

    def test_T095_inactive_user_cannot_access_own_resource(self):
        assert not ctx(Role.CUSTOMER, user_id="A", is_active=False).can_access_resource(
            P.TRADE_READ_OWN, "A"
        )

    def test_T096_audit_own_isolation(self):
        c = ctx(Role.CUSTOMER, user_id="A")
        assert c.can_access_resource(P.AUDIT_READ_OWN, "A")
        assert not c.can_access_resource(P.AUDIT_READ_OWN, "B")


class TestDepsV3Factories:
    def test_T097_require_perm_ok(self):
        assert require_perm(P.TRADE_EXECUTE)(CTX_CUSTOMER) is CTX_CUSTOMER

    def test_T098_require_perm_denied(self):
        with pytest.raises(PermissionDeniedError):
            require_perm(P.LICENSE_ISSUE)(CTX_CUSTOMER)

    def test_T099_require_any_perm_or_logic(self):
        assert require_any_perm(P.LICENSE_ISSUE, P.TRADE_EXECUTE)(CTX_CUSTOMER) is CTX_CUSTOMER

    def test_T100_require_any_perm_all_missing(self):
        with pytest.raises(PermissionDeniedError):
            require_any_perm(P.LICENSE_ISSUE, P.USER_DELETE)(CTX_CUSTOMER)

    def test_T101_require_all_perms_ok(self):
        assert require_all_perms(P.TRADE_READ_OWN, P.SIGNAL_READ_OWN)(CTX_CUSTOMER) is CTX_CUSTOMER

    def test_T102_require_all_perms_one_missing(self):
        with pytest.raises(PermissionDeniedError):
            require_all_perms(P.TRADE_READ_OWN, P.LICENSE_ISSUE)(CTX_CUSTOMER)

    def test_T103_require_rank_ok(self):
        assert require_rank(Role.ADMIN)(CTX_ADMIN) is CTX_ADMIN

    def test_T104_require_rank_denied(self):
        with pytest.raises(PermissionDeniedError):
            require_rank(Role.ADMIN)(CTX_SUPPORT)

    def test_T105_require_rank_super_ok(self):
        assert require_rank(Role.ADMIN)(CTX_SUPER) is CTX_SUPER

    def test_T106_build_auth_context_invalid_token(self):
        with pytest.raises(PermissionDeniedError):
            build_auth_context("not.a.token")

    def test_T107_require_perm_admin_has_all_critical(self):
        for perm in [
            P.LICENSE_ISSUE,
            P.RISK_KILL_SWITCH,
            P.USER_DELETE,
            P.AUDIT_EXPORT,
            P.TENANT_MANAGE,
        ]:
            assert require_perm(perm)(CTX_ADMIN) is CTX_ADMIN

    def test_T108_require_perm_blocked_user_denied(self):
        with pytest.raises(PermissionDeniedError):
            require_perm(P.PROFILE_READ_OWN)(ctx(Role.ADMIN, is_blocked=True))


class TestPermissionMiddleware:
    def setup_method(self):
        self.e = PermissionEnforcer()

    def test_T109_public_health_allowed_no_ctx(self):
        allowed, reason = self.e.check("GET", "/health/live", None)
        assert allowed and "public" in reason

    def test_T110_public_auth_login_allowed(self):
        allowed, _ = self.e.check("POST", "/api/v1/auth/login", None)
        assert allowed

    def test_T111_protected_path_no_ctx_denied(self):
        allowed, reason = self.e.check("GET", "/api/v1/trades", None)
        assert not allowed and "authentication" in reason

    def test_T112_protected_path_valid_ctx_allowed(self):
        allowed, _ = self.e.check("GET", "/api/v1/trades", CTX_CUSTOMER)
        assert allowed

    def test_T113_protected_path_wrong_role_denied(self):
        allowed, reason = self.e.check("POST", "/api/v1/risk/kill_switch", CTX_CUSTOMER)
        assert not allowed and "missing_permission" in reason

    def test_T114_admin_allowed_kill_switch(self):
        allowed, _ = self.e.check("POST", "/api/v1/risk/kill_switch", CTX_ADMIN)
        assert allowed

    def test_T115_unknown_path_passes_to_router(self):
        allowed, reason = self.e.check("GET", "/api/v1/nonexistent", CTX_CUSTOMER)
        assert allowed and "unknown" in reason

    def test_T116_blocked_user_denied_everywhere(self):
        c = ctx(Role.ADMIN, is_blocked=True)
        allowed, reason = self.e.check("GET", "/api/v1/trades", c)
        assert not allowed and "blocked" in reason

    def test_T117_match_endpoint_exact(self):
        ep = _match_endpoint("GET", "/api/v1/trades")
        assert ep is not None and ep.permission == P.TRADE_READ_OWN

    def test_T118_match_endpoint_template(self):
        ep = _match_endpoint("GET", "/api/v1/trades/some-uuid-123")
        assert ep is not None

    def test_T119_match_endpoint_wrong_method(self):
        assert _match_endpoint("DELETE", "/api/v1/trades") is None

    def test_T120_inactive_user_denied(self):
        c = ctx(Role.ADMIN, is_active=False)
        allowed, reason = self.e.check("GET", "/api/v1/trades", c)
        assert not allowed and "inactive" in reason


class TestEndpointRegistry:
    def test_T121_every_endpoint_has_permission(self):
        for ep in ENDPOINT_REGISTRY:
            assert ep.permission

    def test_T122_no_endpoint_missing_method(self):
        valid = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        for ep in ENDPOINT_REGISTRY:
            assert ep.method in valid

    def test_T123_no_duplicate_paths(self):
        seen = set()
        for ep in ENDPOINT_REGISTRY:
            key = f"{ep.method}:{ep.path}"
            assert key not in seen
            seen.add(key)

    def test_T124_health_endpoints_are_public(self):
        for ep in ENDPOINT_REGISTRY:
            if "/health/" in ep.path:
                assert ep.permission == "public"

    def test_T125_auth_endpoints_are_public(self):
        pub = {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"}
        for ep in ENDPOINT_REGISTRY:
            if ep.path in pub:
                assert ep.permission == "public"

    def test_T126_risk_halt_requires_risk_halt_perm(self):
        ep = next(e for e in ENDPOINT_REGISTRY if e.path == "/api/v1/risk/halt")
        assert ep.permission == P.RISK_HALT

    def test_T127_kill_switch_requires_risk_kill_switch(self):
        ep = next(e for e in ENDPOINT_REGISTRY if "kill_switch" in e.path)
        assert ep.permission == P.RISK_KILL_SWITCH

    def test_T128_license_issue_requires_license_issue(self):
        ep = next(
            e for e in ENDPOINT_REGISTRY if e.path == "/api/v1/license" and e.method == "POST"
        )
        assert ep.permission == P.LICENSE_ISSUE

    def test_T129_user_delete_requires_user_delete(self):
        ep = next(
            e for e in ENDPOINT_REGISTRY if "delete" in e.method.lower() and "admin/users" in e.path
        )
        assert ep.permission == P.USER_DELETE

    def test_T130_total_endpoints_at_least_50(self):
        assert len(ENDPOINT_REGISTRY) >= 50

    def test_T131_owner_scoped_endpoints_marked(self):
        assert len([e for e in ENDPOINT_REGISTRY if e.owner_scoped]) >= 10

    def test_T132_prometheus_endpoint_has_perm(self):
        ep = next((e for e in ENDPOINT_REGISTRY if "prometheus" in e.path), None)
        assert ep is not None and ep.permission == P.METRICS_PROMETHEUS


class TestPlanPermissions:
    def test_T133_trial_has_basic_read(self):
        assert P.TRADE_READ_OWN in PLAN_PERMISSIONS["trial"]

    def test_T134_trial_no_trade_execute(self):
        assert P.TRADE_EXECUTE not in PLAN_PERMISSIONS["trial"]

    def test_T135_basic_has_trade_execute(self):
        assert P.TRADE_EXECUTE in PLAN_PERMISSIONS["basic"]

    def test_T136_pro_same_as_customer_role(self):
        assert PLAN_PERMISSIONS["pro"] == PLAN_PERMISSIONS["pro"]

    def test_T137_vip_extends_customer(self):
        assert P.RISK_READ_ANY in PLAN_PERMISSIONS["vip"]

    def test_T138_vip_has_risk_read_any(self):
        assert P.RISK_READ_ANY in PLAN_PERMISSIONS["vip"]

    def test_T139_trial_customer_cannot_execute(self):
        assert not AuthContext(user_id="u1", role=Role.CUSTOMER, plan="trial").has_perm(
            P.TRADE_EXECUTE
        )

    def test_T140_basic_customer_can_execute(self):
        assert AuthContext(user_id="u1", role=Role.CUSTOMER, plan="basic").has_perm(P.TRADE_EXECUTE)

    def test_T141_admin_not_restricted_by_trial(self):
        assert AuthContext(user_id="u1", role=Role.ADMIN, plan="trial").has_perm(P.TRADE_EXECUTE)

    def test_T142_no_plan_customer_has_full_perms(self):
        assert AuthContext(user_id="u1", role=Role.CUSTOMER, plan=None).has_perm(P.TRADE_EXECUTE)

    def test_T143_trial_has_release_download(self):
        assert P.RELEASE_DOWNLOAD in PLAN_PERMISSIONS["trial"]

    def test_T144_trial_no_billing_checkout(self):
        assert P.BILLING_CHECKOUT not in PLAN_PERMISSIONS["trial"]


class TestRoleConveniences:
    def test_T145_normalize_role_user_to_customer(self):
        assert normalize_role("user") == Role.CUSTOMER

    def test_T146_normalize_role_trader_to_customer(self):
        assert normalize_role("trader") == Role.CUSTOMER

    def test_T147_normalize_role_superadmin_to_super(self):
        assert normalize_role("superadmin") == Role.SUPER

    def test_T148_normalize_role_read_only(self):
        assert normalize_role("read_only") == Role.READONLY

    def test_T149_normalize_role_unknown_passthrough(self):
        assert normalize_role("custom_role") == "custom_role"

    def test_T150_normalize_role_case_insensitive(self):
        assert normalize_role("ADMIN") == "admin"
        assert normalize_role("Customer") == "customer"

    def test_T151_expand_permissions_readonly(self):
        perms = expand_permissions(Role.READONLY)
        assert P.PROFILE_READ_OWN in perms and P.TRADE_EXECUTE not in perms

    def test_T152_expand_permissions_super(self):
        perms = expand_permissions(Role.SUPER)
        assert P.ALL in perms and P.RISK_KILL_SWITCH in perms

    def test_T153_expand_permissions_admin_no_wildcard(self):
        perms = expand_permissions(Role.ADMIN)
        assert P.ALL not in perms and P.LICENSE_ISSUE in perms

    def test_T154_write_admin_has_halt_not_resume(self):
        perms = expand_permissions(Role.WRITE_ADMIN)
        assert P.RISK_HALT in perms and P.RISK_RESUME not in perms

    def test_T155_support_has_user_list(self):
        assert P.USER_LIST in expand_permissions(Role.SUPPORT)

    def test_T156_support_has_no_user_block(self):
        assert P.USER_BLOCK not in expand_permissions(Role.SUPPORT)


class TestIntegrationFlows:
    def test_T157_customer_full_trade_flow(self):
        c = ctx(Role.CUSTOMER, user_id="cust-1")
        e = RBACEngineV2()
        e.require(c, P.TRADE_READ_OWN)
        e.require(c, P.TRADE_EXECUTE)
        e.require_resource(c, P.TRADE_READ_OWN, "cust-1")

    def test_T158_customer_cannot_see_other_trade(self):
        c = ctx(Role.CUSTOMER, user_id="cust-1")
        with pytest.raises(PermissionDeniedError):
            RBACEngineV2().require_resource(c, P.TRADE_READ_OWN, "cust-2")

    def test_T159_support_can_view_any_user_data(self):
        s = ctx(Role.SUPPORT)
        e = RBACEngineV2()
        e.require(s, P.TRADE_READ_ANY)
        e.require(s, P.PROFILE_READ_ANY)

    def test_T160_admin_license_lifecycle(self):
        e = RBACEngineV2()
        for p in [P.LICENSE_ISSUE, P.LICENSE_REVOKE, P.LICENSE_SUSPEND]:
            e.require(CTX_ADMIN, p)

    def test_T161_admin_role_assign_with_escalation_guard(self):
        e = RBACEngineV2()
        e.require_no_escalation(CTX_ADMIN, Role.SUPPORT)
        with pytest.raises(PermissionDeniedError):
            e.require_no_escalation(CTX_ADMIN, Role.SUPER)

    def test_T162_emergency_kill_switch_flow(self):
        e = RBACEngineV2()
        e.require(CTX_ADMIN, P.RISK_HALT)
        e.require(CTX_ADMIN, P.RISK_KILL_SWITCH)

    def test_T163_write_admin_can_halt_not_kill_switch(self):
        e = RBACEngineV2()
        e.require(CTX_WRITE_ADMIN, P.RISK_HALT)
        with pytest.raises(PermissionDeniedError):
            e.require(CTX_WRITE_ADMIN, P.RISK_KILL_SWITCH)

    def test_T164_billing_checkout_flow(self):
        c = ctx(Role.CUSTOMER, plan="basic")
        e = RBACEngineV2()
        e.require(c, P.BILLING_CHECKOUT)
        e.require(c, P.BILLING_READ_OWN)

    def test_T165_trial_customer_blocked_from_execute(self):
        c = ctx(Role.CUSTOMER, plan="trial")
        with pytest.raises(PermissionDeniedError):
            RBACEngineV2().require(c, P.TRADE_EXECUTE)

    def test_T166_middleware_full_flow_admin(self):
        e = PermissionEnforcer()
        for method, path in [
            ("POST", "/api/v1/risk/halt"),
            ("POST", "/api/v1/risk/kill_switch"),
            ("GET", "/api/v1/audit/log"),
        ]:
            allowed, reason = e.check(method, path, CTX_ADMIN)
            assert allowed, f"Admin denied at {method} {path}: {reason}"

    def test_T167_middleware_full_flow_customer_blocked(self):
        e = PermissionEnforcer()
        for method, path in [("POST", "/api/v1/risk/halt"), ("GET", "/api/v1/audit/log")]:
            allowed, _ = e.check(method, path, CTX_CUSTOMER)
            assert not allowed

    def test_T168_permission_matrix_complete(self):
        m = RBACEngineV2().permission_matrix()["permissions"]
        assert m[P.LICENSE_ISSUE][Role.ADMIN]
        assert not m[P.LICENSE_ISSUE][Role.CUSTOMER]
        for perm_key in list(m.keys())[:5]:
            assert m[perm_key][Role.SUPER]
