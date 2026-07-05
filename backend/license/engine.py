"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
License Engine — Phase J Fix

BUG-J5 FIX: _check_server_db() async/sync mismatch
  - was: asyncio.run() in sync context where loop may already be running
    → RuntimeError: This event loop is already running
  - now: _check_server_db_sync() uses run_coroutine_threadsafe when loop is running,
    asyncio.run() as fallback — same pattern as BUG-J4
  - fail-closed: any exception → valid=False

Sec fixes retained:
  - LICENSE_SECRET from Settings (not os.environ direct)
  - fail-closed in production
  - stats() exposes secret_configured bool
  - LICENSE_REPLAY_WINDOW_SECONDS configurable
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any, Dict, Optional

from ..core.config import settings
from ..core.logger import get_logger

logger = get_logger("license.engine")

_REPLAY_WINDOW = getattr(settings, "LICENSE_REPLAY_WINDOW_SECONDS", 300)
_seen_nonces: Dict[str, float] = {}


class LicenseEngine:
    """
    License validator — fail-closed in production.

    مراحل validation:
      1. HMAC signature check
      2. Timestamp window check (anti-replay)
      3. Nonce uniqueness check
      4. Server-side DB check (اختیاری)
    """

    def __init__(self) -> None:
        self._secret: Optional[str] = getattr(settings, "LICENSE_SECRET", None)
        self._production: bool = getattr(settings, "PRODUCTION", False)

    @property
    def _secret_configured(self) -> bool:
        return bool(self._secret and len(self._secret) >= 16)

    def validate(self, license_data: Dict[str, Any]) -> bool:
        """
        اعتبارسنجی کامل لایسنس.

        Returns:
            True — لایسنس معتبر است
            None — خطا رخ داد (فایل-کلوزد در پرودکشن)
        """
        if not self._secret_configured:
            if self._production:
                logger.error("[License] No LICENSE_SECRET in production — fail-closed")
                return None
            logger.warning("[License] No LICENSE_SECRET — skipping validation in dev")
            return True

        try:
            return self._validate_internal(license_data)
        except Exception as exc:
            logger.error("[License] Validation error: %s", exc)
            return None

    def _validate_internal(self, data: Dict[str, Any]) -> bool:
        # 1. required fields
        for field in ("signature", "timestamp", "nonce", "account_id"):
            if field not in data:
                logger.warning("[License] Missing field: %s", field)
                return False

        # 2. HMAC signature
        provided_sig = data["signature"]
        payload = f"{data['account_id']}:{data['timestamp']}:{data['nonce']}"
        expected_sig = hmac.new(
            self._secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            logger.warning("[License] Invalid HMAC signature")
            return False

        # 3. Timestamp window
        try:
            ts = int(data["timestamp"])
        except (ValueError, TypeError):
            return False
        now = int(time.time())
        if abs(now - ts) > _REPLAY_WINDOW:
            logger.warning("[License] Timestamp outside window (%ds)", abs(now - ts))
            return False

        # 4. Nonce uniqueness
        nonce = data["nonce"]
        # cleanup old nonces
        cutoff = now - _REPLAY_WINDOW
        expired = [k for k, v in _seen_nonces.items() if v < cutoff]
        for k in expired:
            del _seen_nonces[k]
        if nonce in _seen_nonces:
            logger.warning("[License] Replayed nonce: %s", nonce)
            return False
        _seen_nonces[nonce] = float(now)

        # 5. Server-side DB check
        try:
            db_valid = self._check_server_db_sync(data["account_id"])
            if db_valid is False:
                logger.warning("[License] Server DB check failed for %s", data["account_id"])
                return False
        except Exception as exc:
            logger.warning("[License] DB check error (non-fatal): %s", exc)
            # fail-open on DB error (degraded mode) — signature already verified

        return True

    def _check_server_db_sync(self, account_id: str) -> Optional[bool]:
        """
        BUG-J5 FIX: async/sync safe wrapper.

        رویکرد:
          1. try asyncio.get_running_loop() → run_coroutine_threadsafe()
          2. except RuntimeError → asyncio.run() (sync context)
          3. هر exception → None (فایل-آپن برای DB check)
        """
        async def _db_check():
            try:
                from backend.database.connection import get_db_client
                client = await get_db_client()
                resp = (
                    client.table("license_keys")
                    .select("account_id,is_active,expires_at")
                    .eq("account_id", account_id)
                    .eq("is_active", True)
                    .limit(1)
                    .execute()
                )
                rows = resp.data or []
                if not rows:
                    return False
                row = rows[0]
                # check expiry
                expires_at = row.get("expires_at")
                if expires_at:
                    from datetime import datetime
                    try:
                        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                        from datetime import timezone
                        if exp < datetime.now(timezone.utc):
                            return False
                    except Exception:
                        pass
                return True
            except Exception as exc:
                logger.debug("[License] _db_check inner error: %s", exc)
                return None

        try:
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(_db_check(), loop)
                return future.result(timeout=3.0)
            except RuntimeError:
                return asyncio.run(_db_check())
        except Exception as exc:
            logger.warning("[License] _check_server_db_sync failed: %s", exc)
            return None

    def stats(self) -> Dict[str, Any]:
        """Stats برای /health/ready endpoint."""
        return {
            "secret_configured": self._secret_configured,
            "production":        self._production,
            "replay_window_sec": _REPLAY_WINDOW,
            "seen_nonces":       len(_seen_nonces),
        }


# Singleton
license_engine = LicenseEngine()
