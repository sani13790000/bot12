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
    """S-9: Correct HS256 JWT verification."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != "HS256":
            logger.warning("[Auth] JWT alg mismatch: %s", header.get("alg"))
            return None
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected, actual):
            return None
        return json.loads(_b64url_decode(payload_b64))
    except Exception as exc:
        logger.debug("[Auth] JWT verify error: %s", exc)
        return None


def create_hs256_jwt(payload: Dict, secret: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body   = _b64url_encode(json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url_encode(sig)}"


class TokenRevocationList:
    """S-10: LRU-capped revocation set."""
    _MAX_ENTRIES = 50_000

    def __init__(self) -> None:
        self._store: OrderedDict[str, float] = OrderedDict()

    def revoke(self, jti: str, exp: float) -> None:
        if len(self._store) >= self._MAX_ENTRIES:
            self._store.popitem(last=False)
        self._store[jti] = exp
        logger.info("[Auth] Token revoked: jti=%s", jti[:8])

    def is_revoked(self, jti: str) -> bool:
        return jti in self._store

    def purge_expired(self) -> int:
        now = time.time()
        expired = [jti for jti, exp in self._store.items() if exp < now]
        for jti in expired:
            del self._store[jti]
        return len(expired)

    def __len__(self) -> int:
        return len(self._store)


_ADMIN_PATHS: Set[str] = {"/api/v1/users", "/api/v1/admin", "/api/v1/license"}
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def check_scope(path: str, method: str, role: str, scopes: list) -> bool:
    """S-11: Role + scope enforcement."""
    if role == "admin":
        return True
    for ap in _ADMIN_PATHS:
        if path.startswith(ap):
            logger.warning("[Auth] Non-admin access to admin path: %s", path)
            return False
    if method in _WRITE_METHODS and "write" not in scopes:
        _self = ("/api/v1/auth/refresh", "/api/v1/auth/logout", "/api/v1/trades", "/api/v1/signals")
        if not any(path.startswith(p) for p in _self):
            return False
    return True


@dataclass
class RefreshTokenRecord:
    token_hash: str
    user_id: str
    issued_at: float
    expires_at: float
    used: bool = False
    replaced_by: Optional[str] = None


class RefreshTokenStore:
    """S-12: Single-use refresh tokens with rotation + replay detection."""

    def __init__(self) -> None:
        self._store: Dict[str, RefreshTokenRecord] = {}
        self._user_families: Dict[str, Set[str]] = {}

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def issue(self, user_id: str, ttl_days: int = 30) -> str:
        token = str(uuid.uuid4())
        th = self._hash(token)
        now = time.time()
        self._store[th] = RefreshTokenRecord(
            token_hash=th, user_id=user_id,
            issued_at=now, expires_at=now + ttl_days * 86400,
        )
        self._user_families.setdefault(user_id, set()).add(th)
        return token

    def rotate(self, old_token: str) -> Optional[str]:
        th = self._hash(old_token)
        record = self._store.get(th)
        if not record:
            logger.warning("[Auth] Unknown refresh token")
            return None
        if time.time() > record.expires_at:
            del self._store[th]
            logger.warning("[Auth] Expired refresh token")
            return None
        if record.used:
            self._revoke_family(record.user_id)
            logger.critical("[Auth] Refresh token reuse detected for user %s", record.user_id)
            return None
        record.used = True
        new_token = self.issue(record.user_id)
        record.replaced_by = self._hash(new_token)
        return new_token

    def _revoke_family(self, user_id: str) -> None:
        for th in self._user_families.get(user_id, set()):
            self._store.pop(th, None)
        self._user_families.pop(user_id, None)

    def revoke_user(self, user_id: str) -> None:
        self._revoke_family(user_id)


token_revocation_list = TokenRevocationList()
refresh_token_store   = RefreshTokenStore()
