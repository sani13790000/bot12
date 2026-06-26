"""Phase 21 — Tamper-Evident Audit Logging — FINAL"""
from __future__ import annotations
import csv, hashlib, hmac as _hmac_lib, io, json, threading, time, uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

class Severity(str, Enum):
    INFO="INFO"; WARNING="WARNING"; CRMTICAL="CRITICAL"

class AuditEvent(str, Enum):
    AUTH_LOGIN_OK="auth.login.ok"; AUTH_LOGIN_FAIL="auth.login.fail"
    AUTH_LOGIN_LOCKOUT="auth.login.lockout"; AUTH_LOGOUT="auth.logout"
    AUTH_REGISTER="auth.register"; AUTH_TOKEN_REFRESH="auth.token.refresh"
    AUTH_TOKEN_REVOKE="auth.token.revoke"; AUTH_TOKEN_REUSE="auth.token.reuse_detected"
    RBAC_PERMISSION_DENIED="rbac.permission_denied"; RBAC_ROLE_CHANGED="rbac.role_changed"
    RBAC_ESCALATION_ATTEMPT="rbac.escalation_attempt"; RBAC_USER_BLOCKED="rbac.user_blocked"
    RBAC_USER_UNBLOCKED="rbac.user_unblocked"; RBAC_USER_DELETED="rbac.user_deleted"
    LICENSE_ISSUED="license.issued"; LICENSE_ACTIVATED="license.activated"
    LICENSE_EXPIRED="license.expired"; LICENSE_REVOKED="license.revoked"
    LICENSE_SUSPENDED="license.suspended"; LICENSE_REACTIVATED="license.reactivated"
    LICENSE_DEVICE_ADD="license.device.add"; LICENSE_DEVICE_REMOVE="license.device.remove"
    BILLING_CHECKOUT="billing.checkout"; BILLING_PAYMENT_OK="billing.payment.ok"
    BILLING_PAYMENT_FAIL="billing.payment.fail"; BILLING_REFUMD="billing.refund"
    BILLING_PLAN_CHANGED="billing.plan.changed"; BILLING_SUB_CANCEL="billing.subscription.cancel"
    BILLING_WEBHOOK_OK="billing.webhook.ok"; BILLING_WEBHOOK_FAIL="billing.webhook.fail"
    TRADE_OPEN="trade.open"; TRADE_CLOSE="trade.close"; TRADE_CANCEL="trade.cancel"
    TRADE_DUPLICATE_BLOCKED="trade.duplicate_blocked"; SIGNAL_EMIT="signal.emit"
    SIGNAL_DEDUP_BLOCKED="signal.dedup_blocked"; SIGNAL_EXPIRE="signal.expire"
    RECON_MISMATCH="reconciliation.mismatch"; RISK_DRAWDOWN_ALERT=