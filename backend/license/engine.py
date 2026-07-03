"""
License Engine -- HMAC-SHA256 key validation with anti-replay heartbeat.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
_SECRET = b"MT5_TRADING_LICENSE_SECRET_2024"


def _sign(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(_SECRET, body, hashlib.sha256).hexdigest()


class LicenseEngine:
    """Validate and manage trading licenses."""

    def __init__(self, secret: bytes = _SECRET) -> None:
        self._secret = secret
        self._seen: dict[str, float] = {}

    def generate(self, user_id: str, plan: str = "pro", expires_days: int = 365) -> str:
        """Generate a signed license key."""
        payload = {
            "user": user_id,
            "plan": plan,
            "iat": int(time.time()),
            "exp": int(time.time()) + expires_days * 86400,
            "nonce": hashlib.sha256(f"{user_id}{time.time()}".encode()).hexdigest()[:16],
        }
        sig = _sign(payload)
        raw = json.dumps({**payload, "sig": sig})
        return base64.urlsafe_b64encode(raw.encode()).decode()

    def validate(self, key: str) -> dict:
        """Validate a license key."""
        try:
            raw = base64.urlsafe_b64decode(key.encode()).decode()
            payload = json.loads(raw)
            sig = payload.pop("sig", "")
            if not hmac.compare_digest(sig, _sign(payload)):
                return {"valid": False, "reason": "invalid_signature"}
            if payload["exp"] < int(time.time()):
                return {"valid": False, "reason": "expired"}
            nonce = payload.get("nonce", "")
            if nonce in self._seen:
                return {"valid": False, "reason": "replay_detected"}
            self._seen[nonce] = float(time.time())
            return {
                "valid": True,
                "user": payload["user"],
                "plan": payload["plan"],
                "expires_at": datetime.fromtimestamp(
                    payload["exp"], tz=timezone.utc
                ).isoformat(),
            }
        except Exception as exc:
            logger.exception("License validation error: %s", exc)
            return {"valid": False, "reason": "parse_error"}
