"""backend/core/auth.py — Phase 16 JWT utilities."""
from __future__ import annotations
import hashlib, hmac, base64, json, time, uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

_DANGEROUS = {"changeme","secret","password","test","dev","your-secret-key"}

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
    def is_admin(self): return self.role in ("admin","super_admin")
    @property
    def is_expired(self): return self.exp > 0 and time.time() > self.exp
    def has_scope(self, s): return s in self.scopes or self.is_admin

def _b64d(s: str) -> bytes:
    s = s.replace("-","+").replace("_","/")
    pad = 4 - len(s)%4
    if pad != 4: s += "="*pad
    return base64.b64decode(s)

def make_jwt(payload: dict, secret: str) -> str:
    hdr = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    p   = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = hmac.new(secret.encode(), f"{hdr}.{p}".encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{hdr}.{p}.{sig_b64}"

def verify_jwt(token: str, secret: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        h,p,s = parts
        hdr = json.loads(_b64d(h))
        if hdr.get("alg") != "HS256": return None
        exp_sig = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        act_sig = _b64d(s)
        if not hmac.compare_digest(exp_sig, act_sig): return None
        payload = json.loads(_b64d(p))
        return payload
    except Exception:
        return None

def make_token_payload(user_id: str, role: str = "customer",
                       exp_offset: int = 3600, secret: str = "test-secret") -> str:
    payload = {"sub": user_id, "role": role, "email": f"{user_id}@test.com",
               "exp": int(time.time()) + exp_offset, "iat": int(time.time()),
               "jti": str(uuid.uuid4())}
    return make_jwt(payload, secret)

def is_dangerous_secret(s: str) -> bool:
    return s.lower() in _DANGEROUS or len(s) < 32
