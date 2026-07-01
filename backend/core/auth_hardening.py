"""
backend/core/auth_hardening.py
Phase S - Auth & Token Hardening
S-9:  hmac.new() correct Python 3 API
S-10: TokenRevocationList
S-11: check_scope() role enforcement
S-12: RefreshTokenStore singleton
"""
from __future__ import annotations
import hashlib
import hmac
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)
__all__ = ["AuthHardening", "TokenRevocationList", "RefreshTokenStore", "check_scope"]


class TokenRevocationList:
    """S-10: In-memory token revocation list with TTL cleanup."""

    def __init__(self) -> None:
        self._revoked: Dict[str, float] = {}  # token_id -> revoked_at

    def revoke(self, token_id: str) -> None:
        self._revoked[token_id] = time.time()
        logger.info("Token revoked: %s", token_id[:12])

    def is_revoked(self, token_id: str) -> bool:
        return token_id in self._revoked

    def purge_expired(self, max_age_seconds: int = 86400) -> int:
        cutoff = time.time() - max_age_seconds
        before = len(self._revoked)
        self._revoked = {k: v for k, v in self._revoked.items() if v > cutoff}
        return before - len(self._revoked)

    def __len__(self) -> int:
        return len(self._revoked)


class RefreshTokenStore:
    """S-12: Singleton refresh token store."""
    _instance: Optional["RefreshTokenStore"] = None

    def __new__(cls) -> "RefreshTokenStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._store: Dict[str, Dict] = {}
        return cls._instance

    def create(self, user_id: str, ttl: int = 604800) -> str:
        token = secrets.token_urlsafe(48)
        self._store[token] = {
            "user_id": user_id,
            "created_at": time.time(),
            "expires_at": time.time() + ttl,
        }
        return token

    def validate(self, token: str) -> Optional[str]:
        rec = self._store.get(token)
        if not rec:
            return None
        if time.time() > rec["expires_at"]:
            del self._store[token]
            return None
        return rec["user_id"]

    def revoke(self, token: str) -> None:
        self._store.pop(token, None)


class AuthHardening:
    """S-9: HMAC signing helpers."""

    @staticmethod
    def sign(payload: bytes, secret: bytes) -> str:
        # S-9: use hmac.new (correct Python 3 API)
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    @staticmethod
    def verify(payload: bytes, signature: str, secret: bytes) -> bool:
        expected = AuthHardening.sign(payload, secret)
        return hmac.compare_digest(expected, signature)


def check_scope(required_scope: str, user_scopes: List[str]) -> bool:
    """S-11: Role/scope enforcement."""
    return required_scope in user_scopes or "admin" in user_scopes


# Singletons
_revocation_list = TokenRevocationList()
_refresh_store   = RefreshTokenStore()

def get_revocation_list() -> TokenRevocationList:
    return _revocation_list

def get_refresh_store() -> RefreshTokenStore:
    return _refresh_store
