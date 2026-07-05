"""backend/license/engine.py v2 - Phase C Hardened

SEC-C1: LICENSE_SECRET loaded from Settings (validated), not raw os.environ
SEC-C2: Missing secret in production -> fail-closed (deny all, not random)
SEC-C3: stats() exposes secret_configured flag for /health/ready
SEC-C4: Replay window configurable from Settings.LICENSE_REPLAY_WINDOW_SECONDS
SEC-C5: validate() timing-safe via hmac.compare_digest (unchanged)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)

VALID_PLANS = ("FREE", "BASIC", "PRO", "ENTERPRISE")
_DEFAULT_REPLAY_WINDOW = 3_600


def _get_secret() -> bytes:
    """SEC-C1: Load from Settings. SEC-C2: fail-closed in production."""
    try:
        from backend.core.config import get_settings
        s = get_settings()
        raw = getattr(s, "LICENSE_SECRET", "") or ""
    except Exception:
        raw = os.environ.get("LICENSE_SECRET", "")

    if not raw:
        try:
            from backend.core.config import is_production
            if is_production():
                logger.error(
                    "[LicenseEngine] LICENSE_SECRET missing in production. "
                    "All license validations will FAIL (fail-closed)."
                )
                return b""  # empty -> HMAC always mismatches -> deny
        except Exception:
            pass
        logger.warning(
            "[LicenseEngine] LICENSE_SECRET not set - generating ephemeral secret. "
            "Licenses issued now will NOT survive restart."
        )
        return secrets.token_bytes(32)

    return raw.encode("utf-8")


@dataclass
class _HeartbeatRecord:
    last_seen: float
    machine_id: str
    request_count: int = 0


class LicenseEngine:
    """HMAC-SHA256 offline license engine. Phase C: fail-closed, config-driven."""

    def __init__(
        self,
        secret: Optional[bytes] = None,
        replay_window: int = _DEFAULT_REPLAY_WINDOW,
    ) -> None:
        self._secret: bytes = secret if secret is not None else _get_secret()
        try:
            from backend.core.config import get_settings
            s = get_settings()
            self._replay_window: int = int(
                getattr(s, "LICENSE_REPLAY_WINDOW_SECONDS", replay_window)
            )
        except Exception:
            self._replay_window = replay_window
        self._heartbeats: Dict[str, _HeartbeatRecord] = {}

    def issue(self, user_id: str, plan: str, ttl_seconds: int = 365 * 24 * 3600) -> str:
        if plan not in VALID_PLANS:
            raise ValueError(f"Invalid plan: {plan!r}. Must be one of {VALID_PLANS}")
        if not user_id:
            raise ValueError("user_id cannot be empty")
        if not self._secret:
            raise PermissionError("LICENSE_SECRET not configured - cannot issue license.")
        expiry = int(time.time()) + ttl_seconds
        payload = f"{user_id}:{plan}:{expiry}"
        key = f"{payload}.{self._sign(payload)}"
        logger.info("License issued | user=%s plan=%s expiry=%d", user_id, plan, expiry)
        return key

    def validate(self, license_key: str, user_id: str) -> Optional[str]:
        """SEC-C2: empty secret->None. SEC-C5: timing-safe compare."""
        if not self._secret:
            logger.error("[LicenseEngine] Cannot validate - LICENSE_SECRET missing.")
            return None
        try:
            payload, received_sig = license_key.rsplit(".", 1)
        except ValueError:
            logger.warning("Malformed license key format")
            return None
        if not hmac.compare_digest(self._sign(payload), received_sig):
            logger.warning("License HMAC mismatch | user=%s", user_id)
            return None
        try:
            uid, plan, expiry_str = payload.split(":")
            expiry = int(expiry_str)
        except ValueError:
            logger.warning("License payload parse error")
            return None
        if uid != user_id:
            logger.warning("License user_id mismatch | expected=%s got=%s", uid, user_id)
            return None
        if time.time() > expiry:
            logger.info("License expired | user=%s", user_id)
            return None
        if plan not in VALID_PLANS:
            logger.warning("Invalid plan in license: %s", plan)
            return None
        return plan

    def heartbeat(self, user_id: str, machine_id: str) -> bool:
        now = time.time()
        record = self._heartbeats.get(user_id)
        if record is not None:
            same_window = (now - record.last_seen) < self._replay_window
            diff_machine = record.machine_id != machine_id
            if same_window and diff_machine:
                logger.warning(
                    "Concurrent license use | user=%s expected=%s got=%s",
                    user_id, record.machine_id, machine_id,
                )
                return False
        self._heartbeats[user_id] = _HeartbeatRecord(
            last_seen=now,
            machine_id=machine_id,
            request_count=(record.request_count + 1) if record else 1,
        )
        return True

    def revoke(self, user_id: str) -> None:
        self._heartbeats.pop(user_id, None)
        logger.info("License revoked | user=%s", user_id)

    def stats(self) -> dict:
        """SEC-C3: Expose secret_configured for health endpoint."""
        return {
            "active_users": len(self._heartbeats),
            "secret_configured": bool(self._secret),
            "records": [
                {"user_id": uid, "machine_id": r.machine_id,
                 "last_seen": r.last_seen, "request_count": r.request_count}
                for uid, r in self._heartbeats.items()
            ],
        }

    def _sign(self, payload: str) -> str:
        return hmac.new(
            self._secret, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()


license_engine = LicenseEngine()
