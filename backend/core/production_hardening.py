"""
backend/core/production_hardening.py
Galaxy Vast AI Trading Platform — Production Hardening Layer

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

faz I:
  I-1: Security headers (CSP, HSTS, X-Frame-Options) -> middleware/security_hardened.py
  I-2: Rate limiting (Redis + in-memory fallback) -> middleware/rate_limit.py
  I-3: JWT signing + verification -> core/auth.py
  I-4: Supabase RLS policies -> supabase/migrations
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProductionHardening:
    """
    Production security hardening checks and utilities.
    Run on startup to validate production environment.
    """

    CRITICAL_SECRETS: List[str] = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "SECRET_KEY",
        "JWT_SECRET_KEY",
    ]

    SECURITY_HEADERS_REQUIRED: List[str] = [
        "X-Content-Type-Options",
        "X-Frame-Options",
        "X-XSS-Protection",
        "Strict-Transport-Security",
        "Content-Security-Policy",
    ]

    def __init__(self) -> None:
        self.errors     = []
        self.warnings   = []
        self.app_env    = os.getenv("APP_ENV", "development")
        self.is_prod    = self.app_env == "production"

    def run_all_checks(self) -> Dict[str, Any]:
        """Run all production hardening checks."""
        self._check_secrets()
        self._check_debug_mode()
        self._check_cors()
        self._check_mt5_demo_mode()
        self._check_gateway_key()

        status = "fail" if self.errors else "warn" if self.warnings else "pass"
        logger.info("ProductionHardening: %s (errors=%d warnings=%d)",
                    status, len(self.errors), len(self.warnings))
        return {
            "status":    status,
            "errors":    self.errors,
            "warnings":  self.warnings,
            "env":       self.app_env,
        }

    def _check_secrets(self) -> None:
        for key in self.CRITICAL_SECRETS:
            val = os.getenv(key, "")
            if not val:
                self.errors.append(f"Missing critical env var: {key}")
            elif len(val) < 16:
                self.warnings.append(f"{key} is too short (<16 chars)")

    def _check_debug_mode(self) -> None:
        debug = os.getenv("DEBUG", "").lower()
        if self.is_prod and debug in ("true", "1", "yes"):
            self.errors.append("DEBUG=true in production -- DISABLE IMMEDIATELY")

    def _check_cors(self) -> None:
        cors = os.getenv("CORS_ORIGINS", "")
        if self.is_prod and "localhost" in cors.lower():
            self.warnings.append(f"CORS_ORIGINS contains localhost in production: {cors}")

    def _check_mt5_demo_mode(self) -> None:
        demo = os.getenv("MT5_DEMO_MODE", "true").lower()
        if demo in ("true", "1", "yes"):
            msg = "MT5_DEMO_MODE=true -- No real trades will be placed!"
            if self.is_prod:
                self.errors.append(msg)
            else:
                self.warnings.append(msg)
            logger.warning("⚨ %s", msg)

    def _check_gateway_key(self) -> None:
        key = os.getenv("GATEWAY_API_KEY", "")
        if not key:
            self.warnings.append("GATEWAY_API_KEY not set -- gateway runs without auth")
        elif len(key) < 16:
            self.warnings.append("GATEWAY_API_KEY is too short (<16 chars)")


def run_production_checks() -> Dict[str, Any]:
    """Convenience function for startup_validator."""
    return ProductionHardening().run_all_checks()
