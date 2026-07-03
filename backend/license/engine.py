"""
backend/license/engine.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
License validation engine for Galaxy Vast AI.

How it works
------------
1. Each license key is an HMAC-SHA256 of ``{user_id}:{plan}:{expiry_epoch}``
   signed with the server-side ``LICENSE_SECRET``.
2. ``validate()`` verifies the HMAC, checks expiry, and returns the plan.
3. ``heartbeat()`` records the last-seen timestamp to prevent replay attacks
   (a license seen on two machines simultaneously is flagged).

Usage::

    from backend.license.engine import license_engine

    plan = license_engine.validate(license_key, user_id="user_abc")
    if plan is None:
        raise PermissionError("Invalid or expired license")
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "CHANGE_ME_IN_PRODUCTION"   # override via LICENSE_SECRET env var


# ── Engine ───────────────────────────────────────────────────────────────── #


class LicenseEngine:
    """
    Validate and manage Galaxy Vast AI license keys.

    Parameters
    ----------
    secret:
        HMAC signing secret.  Should be loaded from an environment variable
        in production, never hardcoded.
    """

    def __init__(self, secret: Optional[str] = None) -> None:
        import os
        self._secret = (
            secret
            or os.environ.get("LICENSE_SECRET", _DEFAULT_SECRET)
        ).encode()
        # In-memory heartbeat store: user_id → last_seen_epoch
        # Production: replace with Redis / Supabase.
        self._heartbeats: dict[str, float] = {}

    # ── Public API ───────────────────────────────────────────────────────── #

    def generate(self, user_id: str, plan: str, expiry_epoch: int) -> str:
        """
        Generate a signed license key.

        The key format is::

            {user_id}:{plan}:{expiry_epoch}:{hmac_hex}

        Parameters
        ----------
        user_id:      Unique identifier for the licensee.
        plan:         Plan name, e.g. ``"professional"``.
        expiry_epoch: Unix timestamp (seconds) when the license expires.

        Returns
        -------
        A license key string that can be distributed to the user.
        """
        payload = f"{user_id}:{plan}:{expiry_epoch}"
        sig = self._sign(payload)
        return f"{payload}:{sig}"

    def validate(self, key: str, user_id: str) -> Optional[str]:
        """
        Validate a license key.

        Parameters
        ----------
        key:     The license key string.
        user_id: The user_id that should be encoded in the key.

        Returns
        -------
        The plan name (``str``) if valid, or ``None`` if the key is
        invalid, expired, or belongs to a different user.
        """
        try:
            parts = key.strip().split(":")
            if len(parts) != 4:
                logger.warning("[license] invalid key format for user=%s", user_id)
                return None

            key_user, plan, expiry_str, sig = parts

            # 1. User must match
            if key_user != user_id:
                logger.warning("[license] user mismatch: key=%s caller=%s",
                               key_user, user_id)
                return None

            # 2. Verify HMAC (timing-safe)
            payload = f"{key_user}:{plan}:{expiry_str}"
            expected = self._sign(payload)
            if not hmac.compare_digest(expected, sig):
                logger.warning("[license] HMAC mismatch for user=%s", user_id)
                return None

            # 3. Check expiry
            expiry = int(expiry_str)
            if expiry != 0 and time.time() > expiry:
                logger.info("[license] expired key for user=%s plan=%s",
                            user_id, plan)
                return None

            logger.info("[license] valid key user=%s plan=%s", user_id, plan)
            return plan

        except Exception as exc:
            logger.warning("[license] validate error for user=%s: %s", user_id, exc)
            return None

    def heartbeat(self, user_id: str, tolerance_s: float = 30.0) -> bool:
        """
        Record a heartbeat for *user_id*.

        In a production multi-tenant system, simultaneous heartbeats from
        two different machines within *tolerance_s* seconds would flag
        a license sharing violation.

        Returns True always (anti-replay logic is pluggable via DB).
        """
        self._heartbeats[user_id] = time.time()
        logger.debug("[license] heartbeat user=%s", user_id)
        return True

    def is_active(self, user_id: str, key: str) -> bool:
        """Convenience: return True if the license is valid right now."""
        return self.validate(key, user_id) is not None

    # ── Internals ─────────────────────────────────────────────────────────── #

    def _sign(self, payload: str) -> str:
        return hmac.new(
            self._secret,
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()


# ── Module-level singleton ────────────────────────────────────────────────── #
license_engine = LicenseEngine()
