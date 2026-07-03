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
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

log = logging.getLogger(__name__)

_REVOCATION_STORE: Set[str] = set()


class TokenRevocationList:
    """In-memory token revocation (production uses Redis/DB)."""

    def __init__(self) -> None:
        self._revoked: Set[str] = set()

    def revoke(self, jti: str) -> None:
        self._revoked.add(jti)
        log.info("token_revoked jti=%s", jti)

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked

    def purge_expired(self) -> None:
        """Purge expired tokens from the store."""
        # In production, use TTL-aware store
        pass


_revocation_list = TokenRevocationList()


@dataclass
class RefreshToken:
    token: str
    user_id: str
    device_id: str
    created_at: float = field(default_factory=time.time)
    used: bool = False


class RefreshTokenStore:
    """Single-use refresh token rotation (S-12)."""

    def __init__(self) -> None:
        self._tokens: Dict[str, RefreshToken] = {}

    def create(self, user_id: str, device_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = RefreshToken(token=token, user_id=user_id, device_id=device_id)
        return token

    def consume(self, token: str) -> Optional[RefreshToken]:
        rt = self._tokens.get(token)
        if rt and not rt.used:
            rt.used = True
            return rt
        return None

    def revoke_all(self, user_id: str) -> int:
        count = 0
        for t, rt in list(self._tokens.items()):
            if rt.user_id == user_id:
                rt.used = True
                count += 1
        return count


_refresh_store = RefreshTokenStore()


def check_scope(required: str, token_scopes: str) -> bool:
    """S-11: Check if required scope is in token scopes."""
    scopes = set(token_scopes.split())
    return required in scopes


def compute_token_fingerprint(token: str) -> str:
    """S-9: HMAC fingerprint using correct Python 3 API."""
    key = secrets.token_bytes(32)
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def get_revocation_list() -> TokenRevocationList:
    return _revocation_list


def get_refresh_store() -> RefreshTokenStore:
    return _refresh_store
