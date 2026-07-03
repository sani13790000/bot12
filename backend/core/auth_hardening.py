"""
backend/core/auth_hardening.py
Phase S - Auth & Token Hardening
S-9:  hmac.new() correct Python 3 API
S-10: TokenRevocationList
S-11: check_scope() role enforcement
S-12: RefreshTokenStore single-use rotation
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import time
import uuid
from base64 import b64decode, b64encode
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, Optional, Set

logger = logging.getLogger("core.auth_hardening")


def _b64url_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return b64decode(s)


def _b64url_encode(b: bytes) -> str:
    return b64encode(b).rstrip(b"=").replace(b"+", b"-").replace(b"/", b"_").decode()


def verify_hs256_jwt(token: str, secret: str) -> Optional[Dict]:
    """Verify HS256 JWT and return payload dict on success."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(
            secret.encode(), signing_input, hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        exp = payload.get("exp")
        if exp and time.time() > exp:
            return None
        return payload
    except Exception as e:
        logger.debug("JWT verify failed: %s", e)
        return None


class TokenRevocationList:
    """S-10: In-memory token revocation list with TTL."""

    def __init__(self, max_size: int = 10_000) -> None:
        self._store: OrderedDict[str, float] = OrderedDict()
        self._max = max_size

    def revoke(self, jti: str, exp: float) -> None:
        if len(self._store) >= self._max:
            self._store.popitem(last=False)
        self._store[jti] = exp

    def is_revoked(self, jti: str) -> bool:
        exp = self._store.get(jti)
        if exp is None:
            return False
        if time.time() > exp:
            del self._store[jti]
            return False
        return True

    def purge_expired(self) -> int:
        now = time.time()
        expired = [k for k, v in self._store.items() if v < now]
        for k in expired:
            del self._store[k]
        return len(expired)


class RefreshTokenStore:
    """S-12: Single-use refresh token rotation."""

    def __init__(self) -> None:
        self._tokens: Dict[str, Dict] = {}

    def issue(self, user_id: str, ttl_s: float = 86400.0) -> str:
        token = str(uuid.uuid4())
        self._tokens[token] = {"user_id": user_id, "exp": time.time() + ttl_s}
        return token

    def consume(self, token: str) -> Optional[str]:
        record = self._tokens.pop(token, None)
        if record is None:
            return None
        if time.time() > record["exp"]:
            return None
        return record["user_id"]

    def revoke(self, token: str) -> None:
        self._tokens.pop(token, None)


def check_scope(token_payload: Dict, required_scope: str) -> bool:
    """S-11: Verify token has required scope/role."""
    scopes: Set[str] = set(token_payload.get("scopes", []))
    role: str = token_payload.get("role", "")
    return required_scope in scopes or role == required_scope


token_revocation_list = TokenRevocationList()
refresh_token_store = RefreshTokenStore()
