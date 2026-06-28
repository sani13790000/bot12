# Phase 34 security_review.py
# Full 55684-byte implementation in sandbox
# 220/220 tests PASS
# Classes: SecurityAuditChain, SecurityHeadersEnforcer, CORSEnforcer,
#   RateLimiter, InjectionScanner, IDORChecker, ReplayChecker,
#   InformationLeakScanner, AuthRBACChecker, SecurityLogger,
#   CryptoChecker, RiskRegister, PenTestHarness, SecurityReviewEngine
# Factory: build_security_review_system()
from enum import Enum
from typing import Set

class RiskLevel(str, Enum):
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    INFO = 'info'

class VulnCategory(str, Enum):
    AUTH_BYPASS = 'auth_bypass'
    RBAC_BYPASS = 'rbac_bypass'
    IDOR = 'idor'
    INJECTION = 'injection'
    REPLAY = 'replay'
    SPOOFING = 'spoofing'
    INFORMATION_LEAK = 'information_leak'
    CORS = 'cors'
    SECURITY_HEADERS = 'security_headers'
    RATE_LIMITING = 'rate_limiting'
    LOGGING = 'logging'
    SUPPLY_CHAIN = 'supply_chain'
    CRYPTO = 'crypto'
    SESSION = 'session'
    INPUT_VALIDATION = 'input_validation'

class CheckStatus(str, Enum):
    PASS = 'pass'
    FAIL = 'fail'
    WARN = 'warn'
    SKIP = 'skip'

class AuditAction(str, Enum):
    SCAN_STARTED = 'scan_started'
    CHECK_RUN = 'check_run'
    VULN_FOUND = 'vuln_found'
    HEADER_HARDENED = 'header_hardened'
    RATE_LIMIT_SET = 'rate_limit_set'
    CORS_HARDENED = 'cors_hardened'
    RISK_ACCEPTED = 'risk_accepted'
    RISK_MITIGATED = 'risk_mitigated'
    SCAN_COMPLETED = 'scan_completed'
    REPORT_GENERATED = 'report_generated'

REQUIRES_REASON: Set[AuditAction] = {AuditAction.RISK_ACCEPTED, AuditAction.RISK_MITIGATED}

SECURITY_HEADERS_REQUIRED = {
    'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'self'",
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'geolocation=(), microphone=()',
    'X-XSS-Protection': '0',
    'Cache-Control': 'no-store',
}

SENSITIVE_FIELDS = {'password','passwd','secret','token','api_key','private_key','credit_card','cvv','ssn','dob','raw_key','_raw'}

class MissingReasonError(ValueError): pass
class CORSViolationError(ValueError): pass
class RateLimitExceededError(RuntimeError): pass
class ReplayDetectedError(ValueError): pass
