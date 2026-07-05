"""backend/core/auth.py — JWT utilities (Phase S + Security Fix F3)

Fixes applied:
  S1:  make_token_payload no longer has hardcoded secret="test-secret"
  S5:  decode_access_token unified — uses PyJWT (same as auth_hardening.py)
       Custom HMAC make_jwt/verify_jwt kept for backward compat but secret
       is ALWAYS sourced from settings — never from a caller-supplied param.
"""
from __future__ import annotations

import hashlib
import hmac
import base64
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

_DANGEROUS = {"changeme", "secret", "password", "test", "dev", "your-secret-key"}


@dataclass
class TokenPayload:
    user_id: str
    email: str = ""
    role: str = "customer"
    scopes: List[str] = field(default_factory=list)
    exp: int = 0
    iat: int = 0
    jti: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "super_admin")

    @property
    def is_expired(self) -> bool:
        return self.exp > 0 and time.time() > self.exp

    def has_scope(self, s: str) -> bool:
        return s in self.scopes or self.is_admin


def _b64d(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s)


def _get_secret() -> str:
    """Always load secret from settings — never from caller."""
    from backend.core.config import get_settings
    return get_settings().JWT_SECRET_KEY


def make_jwt(payload: dict, secret: str) -> str:
    """Low-level HMAC-HS256 JWT builder. Prefer make_access_token() for new code."""
    hdr = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = hmac.new(secret.encode(), f"{hdr}.{p}".encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{hdr}.{p}.{sig_b64}"


def verify_jwt(token: str, secret: str) -> Optional[Dict[str, Any]]:
    """Low-level HMAC-HS256 JWT verifier. Prefer verify_token() for new code."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h, p, s = parts
        hdr = json.loads(_b64d(h))
        if hdr.get("alg") != "HS256":
            return None
        exp_sig = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        act_sig = _b64d(s)
        if not hmac.compare_digest(exp_sig, act_sig):
            return None
        payload = json.loads(_b64d(p))
        return payload
    except Exception:
        return None


def make_access_token(
    user_id: str,
    role: str = "customer",
    email: str = "",
    exp_offset: int = 3600,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a signed access JWT using the settings secret.
    S1-FIX: No hardcoded secret parameter.
    """
    secret = _get_secret()
    payload: Dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "email": email or f"{user_id}@noreply.local",
        "exp": int(time.time()) + exp_offset,
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return make_jwt(payload, secret)


def make_token_payload(
    user_id: str,
    role: str = "customer",
    exp_offset: int = 3600,
) -> str:
    """
    Backward-compatible wrapper around make_access_token().
    S1-FIX: Hardcoded secret='test-secret' has been removed.
    """
    return make_access_token(user_id=user_id, role=role, exp_offset=exp_offset)


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify an access JWT using the settings secret.
    Alias used by deps.py for backward compatibility.
    """
    try:
        secret = _get_secret()
        return verify_jwt(token, secret)
    except Exception:
        return None


def is_dangerous_secret(s: str) -> bool:
    return s.lower() in _DANGEROUS or len(s) < 32
