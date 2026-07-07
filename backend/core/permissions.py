"""
backend/core/permissions.py — Phase 20: Fine-Grained Permission Model
======================================================================
P20-PERM-1: Single source of truth — every permission defined here
P20-PERM-2: Namespace: resource:action[:scope]
P20-PERM-3: Role matrix — 6 roles x N permissions
P20-PERM-4: Privilege escalation impossible — rank enforcement
P20-PERM-5: Wildcard expansion auditable
P20-PERM-6: Extra/custom perms per user (additive only)
P20-PERM-7: Permission groups (bundles) for SaaS plan mapping
P20-PERM-8: Every permission has a description for /permissions/matrix
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set


class P(str, Enum):
    """P20-PERM-1: All permissions — single source of truth."""
    PROFILE_READ_OWN       = "profile:read:own"
    PROFILE_READ_ANY       = "profile:read:any"
    PROFILE_WRITE_OWN      = "profile:write:own"
    PROFILE_WRITE_ANY      = "profile:write:any"
    PROFILE_DELETE_ANY     = "profile:delete:any"
    LICENSE_READ_OWN       = "license:read:own"
    LICENSE_READ_ANY       = "license:read:any"
    LICENSE_ISSUE          = "license:issue"
    LICENSE_REVOKE         = "license:revoke"
    LICENSE_SUSPEND        = "license:suspend"
    LICENSE_TRANSFER       = "license:transfer"
    TRADE_READ_OWN         = "trade:read:own"
    TRADE_READ_ANY         = "trade:read:any"
    TRADE_EXECUTE          = "trade:execute"
    TRADE_CANCEL_OWN       = "trade:cancel:own"
    TRADE_CANCEL_ANY       = "trade:cancel:any"
    TRADE_CLOSE_ALL        = "trade:close_all"
    SIGNAL_READ_OWN        = "signal:read:own"
    SIGNAL_READ_ANY        = "signal:read:any"
    SIGNAL_CREATE          = "signal:create"
    SIGNAL_CANCEL_OWN      = "signal:cancel:own"
    SIGNAL_CANCEL_ANY      = "signal:cancel:any"
    BILLING_READ_OWN       = "billing:read:own"
    BILLING_READ_ANY       = "billing:read:any"
    BILLING_CHECKOUT       = "billing:checkout"
    BILLING_REFUND         = "billing:refund"
    BILLING_MANAGE_PLANS   = "billing:manage_plans"
    BILLING_WEBHOOK_INGEST = "billing:webhook_ingest"
    RISK_READ_OWN          = "risk:read:own"
    RISK_READ_ANY          = "risk:read:any"
    RISK_HALT              = "risk:halt"
    RISK_RESUME            = "risk:resume"
    RISK_KILL_SWITCH       = "risk:kill_switch"
    AUDIT_READ_OWN         = "audit:read:own"
    AUDIT_READ_ANY         = "audit:read:any"
    AUDIT_EXPORT           = "audit:export"
    USER_LIST              = "user:list"
    USER_BLOCK             = "user:block"
    USER_UNBLOCK           = "user:unblock"
    USER_DELETE            = "user:delete"
    USER_ROLE_ASSIGN       = "user:role_assign"
    SETTINGS_READ          = "settings:read"
    SETTINGS_WRITE         = "settings:write"
    METRICS_READ           = "metrics:read"
    METRICS_PROMETHEUS     = "metrics:prometheus"
    ALERT_MANAGE           = "alert:manage"
    TRACE_READ             = "trace:read"
    TENANT_READ_OWN        = "tenant:read:own"
    TENANT_READ_ANY        = "tenant:read:any"
    TENANT_MANAGE          = "tenant:manage"
    TENANT_CROSS_ACCESS    = "tenant:cross_access"
    RELEASE_DOWNLOAD       = "release:download"
    RELEASE_PUBLISH        = "release:publish"
    RELEASE_REVOKE         = "release:revoke"
    ALL                    = "*"


PERM_DESCRIPTIONS: Dict[str, str] = {
    P.PROFILE_READ_OWN:       "Read own profile",
    P.PROFILE_READ_ANY:       "Read any user's profile (support+)",
    P.PROFILE_WRITE_OWN:      "Update own profile settings",
    P.PROFILE_WRITE_ANY:      "Update any user's profile (admin)",
    P.PROFILE_DELETE_ANY:     "GDPR delete any user (admin)",
    P.LICENSE_READ_OWN:       "View own license and device list",
    P.LICENSE_READ_ANY:       "View any license (support+)",
    P.LICENSE_ISSUE:          "Issue new licenses (admin)",
    P.LICENSE_REVOKE:         "Revoke a license (admin)",
    P.LICENSE_SUSPEND:        "Suspend a license temporarily (admin)",
    P.LICENSE_TRANSFER:       "Transfer license to another device (admin)",
    P.TRADE_READ_OWN:         "View own trade history",
    P.TRADE_READ_ANY:         "View any user's trades (support+)",
    P.TRADE_EXECUTE:          "Place trades via EA (licensed users)",
    P.TRADE_CANCEL_OWN:       "Cancel own pending trade",
    P.TRADE_CANCEL_ANY:       "Cancel any trade (admin)",
    P.TRADE_CLOSE_ALL:        "Emergency close all open positions (admin)",
    P.SIGNAL_READ_OWN:        "View own signals",
    P.SIGNAL_READ_ANY:        "View all signals (support+)",
    P.SIGNAL_CREATE:          "Create trading signals",
    P.SIGNAL_CANCEL_OWN:      "Cancel own signal",
    P.SIGNAL_CANCEL_ANY:      "Cancel any signal (admin)",
    P.BILLING_READ_OWN:       "View own invoices and subscription",
    P.BILLING_READ_ANY:       "View any billing record (admin)",
    P.BILLING_CHECKOUT:       "Initiate a subscription checkout",
    P.BILLING_REFUND:         "Issue a refund (admin)",
    P.BILLING_MANAGE_PLANS:   "CRUD billing plans (admin)",
    P.BILLING_WEBHOOK_INGEST: "Ingest provider webhook (service account)",
    P.RISK_READ_OWN:          "View own risk parameters",
    P.RISK_READ_ANY:          "View system-wide risk (support+)",
    P.RISK_HALT:              "Halt trading engine (admin)",
    P.RISK_RESUME:            "Resume trading engine (admin)",
    P.RISK_KILL_SWITCH:       "Activate emergency kill switch (admin)",
    P.AUDIT_READ_OWN:         "View own audit events",
    P.AUDIT_READ_ANY:         "View full audit log (support+)",
    P.AUDIT_EXPORT:           "Export audit log CSV (admin)",
    P.USER_LIST:              "List all users (support+)",
    P.USER_BLOCK:             "Block a user account (admin)",
    P.USER_UNBLOCK:           "Unblock a user account (admin)",
    P.USER_DELETE:            "Permanently delete user (admin)",
    P.USER_ROLE_ASSIGN:       "Assign roles — target rank < actor rank (admin)",
    P.SETTINGS_READ:          "Read system settings",
    P.SETTINGS_WRITE:         "Write system settings (admin)",
    P.METRICS_READ:           "Read admin metrics dashboard",
    P.METRICS_PROMETHEUS:     "Scrape /metrics Prometheus endpoint",
    P.ALERT_MANAGE:           "Manage alert rules and thresholds",
    P.TRACE_READ:             "Read admin trace events",
    P.TENANT_READ_OWN:        "Read own tenant metadata",
    P.TENANT_READ_ANY:        "Read any tenant (admin)",
    P.TENANT_MANAGE:          "Suspend/activate tenants (admin)",
    P.TENANT_CROSS_ACCESS:    "Cross-tenant data access with audit (admin)",
    P.RELEASE_DOWNLOAD:       "Download EA artifacts (licensed)",
    P.RELEASE_PUBLISH:        "Publish new release artifacts (admin)",
    P.RELEASE_REVOKE:         "Revoke a released artifact (admin)",
    P.ALL:                    "Unrestricted access (super_admin only)",
}


class Role(str, Enum):
    READONLY    = "readonly"
    CUSTOMER    = "customer"
    SUPPORT     = "support"
    WRITE_ADMIN = "write_admin"
    ADMIN       = "admin"
    SUPER       = "super_admin"


ROLE_RANK: Dict[str, int] = {
    Role.READONLY:    0,
    Role.CUSTOMER:    1,
    Role.SUPPORT:     2,
    Role.WRITE_ADMIN: 3,
    Role.ADMIN:       4,
    Role.SUPER:       5,
}

ROLE_ALIASES: Dict[str, str] = {
    "user":        Role.CUSTOMER,
    "trader":      Role.CUSTOMER,
    "read_only":   Role.READONLY,
    "superadmin":  Role.SUPER,
    "super":       Role.SUPER,
    "write-admin": Role.WRITE_ADMIN,
}


def normalize_role(raw: str) -> str:
    r = (raw or "").lower().strip()
    return ROLE_ALIASES.get(r, r)


ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    Role.READONLY: frozenset({
        P.PROFILE_READ_OWN, P.LICENSE_READ_OWN, P.TRADE_READ_OWN,
        P.SIGNAL_READ_OWN, P.BILLING_READ_OWN, P.RISK_READ_OWN,
        P.AUDIT_READ_OWN, P.TENANT_READ_OWN, P.RELEASE_DOWNLOAD,
    }),
    Role.CUSTOMER: frozenset({
        P.PROFILE_READ_OWN, P.PROFILE_WRITE_OWN,
        P.LICENSE_READ_OWN,
        P.TRADE_READ_OWN, P.TRADE_EXECUTE, P.TRADE_CANCEL_OWN,
        P.SIGNAL_READ_OWN, P.SIGNAL_CREATE, P.SIGNAL_CANCEL_OWN,
        P.BILLING_READ_OWN, P.BILLING_CHECKOUT,
        P.RISK_READ_OWN, P.AUDIT_READ_OWN,
        P.TENANT_READ_OWN, P.RELEASE_DOWNLOAD,
    }),
    Role.SUPPORT: frozenset({
        P.PROFILE_READ_OWN, P.PROFILE_WRITE_OWN, P.PROFILE_READ_ANY,
        P.LICENSE_READ_OWN, P.LICENSE_READ_ANY,
        P.TRADE_READ_OWN, P.TRADE_CANCEL_OWN, P.TRADE_READ_ANY,
        P.SIGNAL_READ_OWN, P.SIGNAL_CANCEL_OWN, P.SIGNAL_READ_ANY,
        P.BILLING_READ_OWN,
        P.RISK_READ_OWN, P.RISK_READ_ANY,
        P.AUDIT_READ_OWN, P.AUDIT_READ_ANY,
        P.USER_LIST,
        P.TENANT_READ_OWN, P.TENANT_READ_ANY,
        P.METRICS_READ, P.TRACE_READ,
        P.RELEASE_DOWNLOAD,
    }),
    Role.WRITE_ADMIN: frozenset({
        P.PROFILE_READ_OWN, P.PROFILE_WRITE_OWN, P.PROFILE_READ_ANY,
        P.LICENSE_READ_OWN, P.LICENSE_READ_ANY, P.LICENSE_SUSPEND, P.LICENSE_TRANSFER,
        P.TRADE_READ_OWN, P.TRADE_READ_ANY, P.TRADE_CANCEL_OWN, P.TRADE_CANCEL_ANY,
        P.SIGNAL_READ_OWN, P.SIGNAL_READ_ANY, P.SIGNAL_CANCEL_OWN, P.SIGNAL_CANCEL_ANY,
        P.BILLING_READ_OWN, P.BILLING_READ_ANY,
        P.RISK_READ_OWN, P.RISK_READ_ANY, P.RISK_HALT,
        P.AUDIT_READ_OWN, P.AUDIT_READ_ANY,
        P.USER_LIST,
        P.TENANT_READ_OWN, P.TENANT_READ_ANY,
        P.METRICS_READ, P.TRACE_READ,
        P.RELEASE_DOWNLOAD,
    }),
    Role.ADMIN: frozenset({
        P.PROFILE_READ_OWN, P.PROFILE_WRITE_OWN, P.PROFILE_READ_ANY,
        P.PROFILE_WRITE_ANY, P.PROFILE_DELETE_ANY,
        P.LICENSE_READ_OWN, P.LICENSE_READ_ANY, P.LICENSE_ISSUE,
        P.LICENSE_REVOKE, P.LICENSE_SUSPEND, P.LICENSE_TRANSFER,
        P.TRADE_READ_OWN, P.TRADE_READ_ANY, P.TRADE_EXECUTE,
        P.TRADE_CANCEL_OWN, P.TRADE_CANCEL_ANY, P.TRADE_CLOSE_ALL,
        P.SIGNAL_READ_OWN, P.SIGNAL_READ_ANY, P.SIGNAL_CREATE,
        P.SIGNAL_CANCEL_OWN, P.SIGNAL_CANCEL_ANY,
        P.BILLING_READ_OWN, P.BILLING_READ_ANY, P.BILLING_CHECKOUT,
        P.BILLING_REFUND, P.BILLING_MANAGE_PLANS, P.BILLING_WEBHOOK_INGEST,
        P.RISK_READ_OWN, P.RISK_READ_ANY, P.RISK_HALT,
        P.RISK_RESUME, P.RISK_KILL_SWITCH,
        P.AUDIT_READ_OWN, P.AUDIT_READ_ANY, P.AUDIT_EXPORT,
        P.USER_LIST, P.USER_BLOCK, P.USER_UNBLOCK,
        P.USER_DELETE, P.USER_ROLE_ASSIGN,
        P.SETTINGS_READ, P.SETTINGS_WRITE,
        P.METRICS_READ, P.METRICS_PROMETHEUS,
        P.ALERT_MANAGE, P.TRACE_READ,
        P.TENANT_READ_OWN, P.TENANT_READ_ANY,
        P.TENANT_MANAGE, P.TENANT_CROSS_ACCESS,
        P.RELEASE_DOWNLOAD, P.RELEASE_PUBLISH, P.RELEASE_REVOKE,
    }),
    Role.SUPER: frozenset({P.ALL}),
}


PLAN_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "trial": frozenset({
        P.TRADE_READ_OWN, P.SIGNAL_READ_OWN,
        P.LICENSE_READ_OWN, P.BILLING_READ_OWN,
        P.PROFILE_READ_OWN, P.PROFILE_WRITE_OWN,
        P.RELEASE_DOWNLOAD, P.AUDIT_READ_OWN,
        P.RISK_READ_OWN, P.TENANT_READ_OWN,
    }),
    "basic": frozenset({
        P.TRADE_READ_OWN, P.TRADE_EXECUTE, P.TRADE_CANCEL_OWN,
        P.SIGNAL_READ_OWN, P.SIGNAL_CREATE, P.SIGNAL_CANCEL_OWN,
        P.LICENSE_READ_OWN, P.BILLING_READ_OWN, P.BILLING_CHECKOUT,
        P.PROFILE_READ_OWN, P.PROFILE_WRITE_OWN,
        P.RISK_READ_OWN, P.RELEASE_DOWNLOAD,
        P.AUDIT_READ_OWN, P.TENANT_READ_OWN,
    }),
    "pro":  frozenset(ROLE_PERMISSIONS[Role.CUSTOMER] if False else {
        P.PROFILE_READ_OWN, P.PROFILE_WRITE_OWN,
        P.LICENSE_READ_OWN,
        P.TRADE_READ_OWN, P.TRADE_EXECUTE, P.TRADE_CANCEL_OWN,
        P.SIGNAL_READ_OWN, P.SIGNAL_CREATE, P.SIGNAL_CANCEL_OWN,
        P.BILLING_READ_OWN, P.BILLING_CHECKOUT,
        P.RISK_READ_OWN, P.AUDIT_READ_OWN,
        P.TENANT_READ_OWN, P.RELEASE_DOWNLOAD,
    }),
    "vip": frozenset({
        P.PROFILE_READ_OWN, P.PROFILE_WRITE_OWN,
        P.LICENSE_READ_OWN,
        P.TRADE_READ_OWN, P.TRADE_EXECUTE, P.TRADE_CANCEL_OWN,
        P.SIGNAL_READ_OWN, P.SIGNAL_CREATE, P.SIGNAL_CANCEL_OWN,
        P.BILLING_READ_OWN, P.BILLING_CHECKOUT,
        P.RISK_READ_OWN, P.RISK_READ_ANY,
        P.AUDIT_READ_OWN,
        P.TENANT_READ_OWN, P.RELEASE_DOWNLOAD,
    }),
}


def expand_permissions(role: str) -> FrozenSet[str]:
    """P20-PERM-5: Return full effective set (wildcard expanded)."""
    perms = ROLE_PERMISSIONS.get(role, frozenset())
    if P.ALL in perms:
        all_perms: Set[str] = set()
        for ps in ROLE_PERMISSIONS.values():
            all_perms.update(x for x in ps if x != P.ALL)
        all_perms.update(p.value for p in P if p != P.ALL)
        all_perms.add(P.ALL)
        return frozenset(all_perms)
    return perms


@dataclass
class EndpointSpec:
    method:       str
    path:         str
    permission:   str
    description:  str
    owner_scoped: bool = False


ENDPOINT_REGISTRY: List[EndpointSpec] = [
    EndpointSpec("POST", "/api/v1/auth/login",           "public",              "Login"),
    EndpointSpec("POST", "/api/v1/auth/register",        "public",              "Register"),
    EndpointSpec("POST", "/api/v1/auth/refresh",         "public",              "Refresh token"),
    EndpointSpec("POST", "/api/v1/auth/logout",          P.PROFILE_READ_OWN,    "Logout"),
    EndpointSpec("GET",  "/api/v1/auth/me",              P.PROFILE_READ_OWN,    "Get current user"),
    EndpointSpec("GET",  "/api/v1/profile",              P.PROFILE_READ_OWN,    "Read own profile",       True),
    EndpointSpec("PUT",  "/api/v1/profile",              P.PROFILE_WRITE_OWN,   "Update own profile",     True),
    EndpointSpec("GET",  "/api/v1/profile/{user_id}",    P.PROFILE_READ_ANY,    "Read any profile"),
    EndpointSpec("PUT",  "/api/v1/profile/{user_id}",    P.PROFILE_WRITE_ANY,   "Update any profile"),
    EndpointSpec("DELETE","/api/v1/profile/{user_id}",   P.PROFILE_DELETE_ANY,  "GDPR delete user"),
    EndpointSpec("GET",  "/api/v1/license",              P.LICENSE_READ_OWN,    "Read own license",       True),
    EndpointSpec("GET",  "/api/v1/license/{lic_id}",     P.LICENSE_READ_ANY,    "Read any license"),
    EndpointSpec("POST", "/api/v1/license",              P.LICENSE_ISSUE,       "Issue license"),
    EndpointSpec("DELETE","/api/v1/license/{lic_id}",    P.LICENSE_REVOKE,      "Revoke license"),
    EndpointSpec("POST", "/api/v1/license/{lic_id}/suspend",  P.LICENSE_SUSPEND,  "Suspend license"),
    EndpointSpec("POST", "/api/v1/license/{lic_id}/transfer", P.LICENSE_TRANSFER, "Transfer license"),
    EndpointSpec("GET",  "/api/v1/trades",               P.TRADE_READ_OWN,      "List own trades",        True),
    EndpointSpec("GET",  "/api/v1/trades/{trade_id}",    P.TRADE_READ_OWN,      "Get trade detail",       True),
    EndpointSpec("GET",  "/api/v1/trades/any",           P.TRADE_READ_ANY,      "List any trades"),
    EndpointSpec("POST", "/api/v1/trades/execute",       P.TRADE_EXECUTE,       "Execute trade"),
    EndpointSpec("POST", "/api/v1/trades/{trade_id}/cancel", P.TRADE_CANCEL_OWN, "Cancel own trade",      True),
    EndpointSpec("POST", "/api/v1/trades/close_all",     P.TRADE_CLOSE_ALL,     "Close all positions"),
    EndpointSpec("GET",  "/api/v1/signals",              P.SIGNAL_READ_OWN,     "List own signals",       True),
    EndpointSpec("GET",  "/api/v1/signals/{sig_id}",     P.SIGNAL_READ_OWN,     "Get signal detail",      True),
    EndpointSpec("GET",  "/api/v1/signals/any",          P.SIGNAL_READ_ANY,     "List all signals"),
    EndpointSpec("POST", "/api/v1/signals",              P.SIGNAL_CREATE,       "Create signal"),
    EndpointSpec("POST", "/api/v1/signals/{sig_id}/cancel", P.SIGNAL_CANCEL_OWN, "Cancel own signal",     True),
    EndpointSpec("GET",  "/api/v1/billing/invoices",     P.BILLING_READ_OWN,    "List own invoices",      True),
    EndpointSpec("POST", "/api/v1/billing/checkout",     P.BILLING_CHECKOUT,    "Start checkout"),
    EndpointSpec("GET",  "/api/v1/billing/any",          P.BILLING_READ_ANY,    "List any billing"),
    EndpointSpec("POST", "/api/v1/billing/refund",       P.BILLING_REFUND,      "Issue refund"),
    EndpointSpec("POST", "/api/v1/billing/webhook",      P.BILLING_WEBHOOK_INGEST, "Ingest webhook"),
    EndpointSpec("GET",  "/api/v1/billing/plans",        P.BILLING_MANAGE_PLANS,"Manage plans"),
    EndpointSpec("GET",  "/api/v1/risk/status",          P.RISK_READ_OWN,       "Read own risk status"),
    EndpointSpec("GET",  "/api/v1/risk/report",          P.RISK_READ_ANY,       "System risk report"),
    EndpointSpec("POST", "/api/v1/risk/halt",            P.RISK_HALT,           "Halt trading"),
    EndpointSpec("POST", "/api/v1/risk/resume",          P.RISK_RESUME,         "Resume trading"),
    EndpointSpec("POST", "/api/v1/risk/kill_switch",     P.RISK_KILL_SWITCH,    "Kill switch"),
    EndpointSpec("GET",  "/api/v1/audit/own",            P.AUDIT_READ_OWN,      "View own audit log"),
    EndpointSpec("GET",  "/api/v1/audit/log",            P.AUDIT_READ_ANY,      "View full audit log"),
    EndpointSpec("GET",  "/api/v1/audit/export.csv",     P.AUDIT_EXPORT,        "Export audit CSV"),
    EndpointSpec("GET",  "/api/v1/admin/users",          P.USER_LIST,           "List users"),
    EndpointSpec("GET",  "/api/v1/admin/users/{uid}",    P.PROFILE_READ_ANY,    "Get user"),
    EndpointSpec("PATCH","/api/v1/admin/users/{uid}/role", P.USER_ROLE_ASSIGN,  "Change role"),
    EndpointSpec("POST", "/api/v1/admin/users/{uid}/block",   P.USER_BLOCK,     "Block user"),
    EndpointSpec("POST", "/api/v1/admin/users/{uid}/unblock", P.USER_UNBLOCK,   "Unblock user"),
    EndpointSpec("DELETE","/api/v1/admin/users/{uid}",   P.USER_DELETE,         "Delete user GDPR"),
    EndpointSpec("GET",  "/api/v1/settings",             P.SETTINGS_READ,       "Read system settings"),
    EndpointSpec("PUT",  "/api/v1/settings",             P.SETTINGS_WRITE,      "Write system settings"),
    EndpointSpec("GET",  "/admin/metrics",               P.METRICS_READ,        "Admin metrics dashboard"),
    EndpointSpec("GET",  "/admin/metrics/prometheus",    P.METRICS_PROMETHEUS,  "Prometheus scrape"),
    EndpointSpec("GET",  "/admin/alerts",                P.METRICS_READ,        "Alert history"),
    EndpointSpec("POST", "/admin/alert/manage",          P.ALERT_MANAGE,        "Manage alert rules"),
    EndpointSpec("GET",  "/admin/trace",                 P.TRACE_READ,          "Admin trace events"),
    EndpointSpec("GET",  "/api/v1/tenant",               P.TENANT_READ_OWN,     "Read own tenant"),
    EndpointSpec("GET",  "/api/v1/tenant/{tid}",         P.TENANT_READ_ANY,     "Read any tenant"),
    EndpointSpec("POST", "/api/v1/tenant/{tid}/suspend", P.TENANT_MANAGE,       "Suspend tenant"),
    EndpointSpec("GET",  "/api/v1/tenant/cross",         P.TENANT_CROSS_ACCESS, "Cross-tenant data"),
    EndpointSpec("GET",  "/api/v1/release/download",     P.RELEASE_DOWNLOAD,    "Download EA artifact"),
    EndpointSpec("POST", "/api/v1/release/publish",      P.RELEASE_PUBLISH,     "Publish artifact"),
    EndpointSpec("DELETE","/api/v1/release/{vid}",       P.RELEASE_REVOKE,      "Revoke artifact"),
    EndpointSpec("GET",  "/health/live",                 "public",              "Liveness probe"),
    EndpointSpec("GET",  "/health/ready",                "public",              "Readiness probe"),
    EndpointSpec("GET",  "/api/v1/permissions/matrix",   P.PROFILE_READ_OWN,    "View permission matrix"),
    EndpointSpec("GET",  "/api/v1/permissions/my",       P.PROFILE_READ_OWN,    "View own permissions"),
]


class EscalationError(Exception):
    """Raised when privilege escalation attempt detected."""


def assert_no_escalation(actor_role: str, target_role: str) -> None:
    """P20-PERM-4: actor can only assign roles strictly below their own rank."""
    actor_rank  = ROLE_RANK.get(normalize_role(actor_role), -1)
    target_rank = ROLE_RANK.get(normalize_role(target_role), -1)
    if target_rank < 0:
        raise EscalationError(f"Unknown target role: '{target_role}'")
    if actor_rank <= target_rank:
        raise EscalationError(
            f"Privilege escalation blocked: actor '{actor_role}' (rank={actor_rank}) "
            f"cannot assign '{target_role}' (rank={target_rank})"
        )


@dataclass
class AuthContext:
    user_id:     str
    role:        str
    tenant_id:   str  = "default"
    is_active:   bool = True
    is_blocked:  bool = False
    extra_perms: FrozenSet[str] = field(default_factory=frozenset)
    plan:        Optional[str]  = None

    @property
    def rank(self) -> int:
        return ROLE_RANK.get(self.role, 0)

    @property
    def effective_perms(self) -> FrozenSet[str]:
        """P20-PERM-6: role perms + extra (additive only)."""
        base = expand_permissions(self.role)
        if self.plan and self.plan in PLAN_PERMISSIONS and self.role == Role.CUSTOMER:
            plan_perms = PLAN_PERMISSIONS[self.plan]
            if self.plan in ("trial", "basic"):
                base = base & plan_perms
            elif self.plan == "vip":
                base = base | plan_perms
        return base | self.extra_perms

    def has_perm(self, perm: str) -> bool:
        if not self.is_active or self.is_blocked:
            return False
        ep = self.effective_perms
        return P.ALL in ep or perm in ep

    def has_any_perm(self, *perms: str) -> bool:
        return any(self.has_perm(p) for p in perms)

    def can_access_resource(self, perm: str, owner_id: Optional[str]) -> bool:
        if not self.has_perm(perm):
            return False
        if ":own" in perm and owner_id is not None:
            return str(owner_id) == str(self.user_id)
        return True

    def can_escalate_to(self, target_role: str) -> bool:
        try:
            assert_no_escalation(self.role, target_role)
            return self.has_perm(P.USER_ROLE_ASSIGN)
        except EscalationError:
            return False


import logging
from typing import Any, Callable

from .ttl_cache import TTLPermissionCache

_log = logging.getLogger("core.rbac_v2")
_CACHE_TTL = 60
_CACHE_MAX = 4096


class PermissionDeniedError(Exception):
    """Convert to HTTP 403."""


class RBACEngineV2:
    """P20: Fine-grained permission engine."""

    def __init__(self) -> None:
        self._cache = TTLPermissionCache(max_size=_CACHE_MAX, ttl=_CACHE_TTL)
        self._deny_hooks: List[Callable] = []

    def check(self, ctx: AuthContext, perm: str) -> bool:
        if perm == "public":
            return True
        key = f"{ctx.user_id}:{ctx.role}:{perm}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = ctx.has_perm(perm)
        self._cache.set(key, result)
        if not result:
            _log.warning("RBAC deny: user=%s role=%s perm=%s", ctx.user_id[:8], ctx.role, perm)
            for h in self._deny_hooks:
                try:
                    h(ctx, perm)
                except Exception:
                    pass
        return result

    def check_resource(self, ctx: AuthContext, perm: str, owner_id: Optional[str]) -> bool:
        result = ctx.can_access_resource(perm, owner_id)
        if not result:
            _log.warning("RBAC owner-deny: user=%s role=%s perm=%s", ctx.user_id[:8], ctx.role, perm)
        return result

    def require(self, ctx: AuthContext, perm: str) -> None:
        if not self.check(ctx, perm):
            raise PermissionDeniedError(f"Role '{ctx.role}' lacks '{perm}'")

    def require_resource(self, ctx: AuthContext, perm: str, owner_id: Optional[str]) -> None:
        if not self.check_resource(ctx, perm, owner_id):
            raise PermissionDeniedError(
                f"Resource access denied: user={ctx.user_id[:8]} owner={str(owner_id)[:8] if owner_id else '?'}"
            )

    def require_no_escalation(self, actor: AuthContext, target_role: str) -> None:
        try:
            assert_no_escalation(actor.role, target_role)
        except EscalationError as exc:
            raise PermissionDeniedError(str(exc)) from exc
        self.require(actor, P.USER_ROLE_ASSIGN)

    def is_admin_or_above(self, ctx: AuthContext) -> bool:
        return ctx.rank >= ROLE_RANK[Role.ADMIN]

    def is_support_or_above(self, ctx: AuthContext) -> bool:
        return ctx.rank >= ROLE_RANK[Role.SUPPORT]

    def get_role_permissions(self, role: str) -> List[str]:
        return sorted(expand_permissions(role))

    def invalidate(self, user_id: str) -> None:
        self._cache.invalidate_user(user_id)

    def add_deny_hook(self, fn: Callable) -> None:
        self._deny_hooks.append(fn)

    def permission_matrix(self) -> Dict[str, Any]:
        roles = [Role.READONLY, Role.CUSTOMER, Role.SUPPORT,
                 Role.WRITE_ADMIN, Role.ADMIN, Role.SUPER]
        perms = [p.value for p in P if p != P.ALL]
        matrix: Dict[str, Dict[str, bool]] = {}
        for perm in sorted(perms):
            matrix[perm] = {}
            for role in roles:
                ctx = AuthContext(user_id="matrix", role=role)
                matrix[perm][role] = self.check(ctx, perm)
        return {
            "roles": roles,
            "permissions": matrix,
            "descriptions": {p: PERM_DESCRIPTIONS.get(p, "") for p in sorted(perms)},
            "endpoint_count": len(ENDPOINT_REGISTRY),
        }

    def endpoint_permissions(self) -> List[Dict[str, Any]]:
        return [
            {
                "method":       ep.method,
                "path":         ep.path,
                "permission":   ep.permission,
                "description":  ep.description,
                "owner_scoped": ep.owner_scoped,
            }
            for ep in ENDPOINT_REGISTRY
        ]


rbac_v2 = RBACEngineV2()
