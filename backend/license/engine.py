"""
backend/license/engine.py
Galaxy Vast AI - License, Subscription and Device Enforcement (Phase 6)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class LicenseStatus(str, Enum):
    PENDING   = "PENDING"
    ACTIVE    = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPIRED   = "EXPIRED"
    REVOKED   = "REVOKED"


class SubscriptionTier(str, Enum):
    FREE       = "FREE"
    STARTER    = "STARTER"
    PRO        = "PRO"
    ENTERPRISE = "ENTERPRISE"


@dataclass
class LicenseRecord:
    license_id:     str
    key_hash:       str
    status:         LicenseStatus
    tier:           SubscriptionTier
    user_id:        str
    device_limit:   int       = 3
    device_count:   int       = 0
    features:       List[str] = field(default_factory=list)
    expires_at:     float     = 0.0
    created_at:     float     = field(default_factory=time.time)
    last_heartbeat: float     = 0.0


@dataclass
class HeartbeatRequest:
    license_id: str
    device_id:  str
    nonce:      str
    timestamp:  float
    signature:  str


@dataclass
class HeartbeatResponse:
    ok:         bool
    status:     str
    tier:       str
    features:   List[str]
    expires_at: float
    nonce:      str
    signature:  str


class LicenseEngine:
    """Central license enforcement engine - fail-closed on all errors."""

    _NONCE_TTL = 300  # seconds

    def __init__(self, secret_key: str, supabase_client=None) -> None:
        self._secret = secret_key.encode()
        self._db     = supabase_client
        self._nonces: Dict[str, float]       = {}
        self._cache:  Dict[str, LicenseRecord] = {}
        self._log    = logging.getLogger(self.__class__.__name__)

    def hash_key(self, raw_key: str) -> str:
        return hmac.new(self._secret, raw_key.encode(), hashlib.sha256).hexdigest()

    def verify_heartbeat(self, req: HeartbeatRequest) -> HeartbeatResponse:
        deny = HeartbeatResponse(ok=False, status="REVOKED", tier="FREE", features=[], expires_at=0.0, nonce=str(uuid.uuid4()), signature="")
        now  = time.time()
        if abs(now - req.timestamp) > self._NONCE_TTL:
            return deny
        self._evict_stale_nonces(now)
        if req.nonce in self._nonces:
            return deny
        self._nonces[req.nonce] = now
        expected = self._sign(f"{req.license_id}:{req.device_id}:{req.nonce}:{req.timestamp:.0f}")
        if not hmac.compare_digest(expected, req.signature):
            return deny
        record = self._get_license(req.license_id)
        if record is None or record.status != LicenseStatus.ACTIVE:
            return deny
        if record.expires_at and now > record.expires_at:
            record.status = LicenseStatus.EXPIRED
            self._update_status(req.license_id, LicenseStatus.EXPIRED)
            return deny
        resp_nonce            = str(uuid.uuid4())
        record.last_heartbeat = now
        return HeartbeatResponse(
            ok=True, status=record.status.value, tier=record.tier.value,
            features=record.features, expires_at=record.expires_at, nonce=resp_nonce,
            signature=self._sign(f"{req.license_id}:{resp_nonce}:{record.status.value}")
        )

    def register_device(self, license_id: str, device_id: str) -> bool:
        record = self._get_license(license_id)
        if record is None or record.status != LicenseStatus.ACTIVE:
            return False
        if record.device_count >= record.device_limit:
            return False
        record.device_count += 1
        self._persist_device(license_id, device_id)
        return True

    def revoke_license(self, license_id: str, admin_id: str, reason: str = "") -> bool:
        record = self._get_license(license_id)
        if record is None:
            return False
        record.status = LicenseStatus.REVOKED
        self._update_status(license_id, LicenseStatus.REVOKED)
        self._log.info("LICENSE REVOKED | id=%s | admin=%s | reason=%s", license_id, admin_id, reason)
        return True

    def check_feature(self, license_id: str, feature: str) -> bool:
        record = self._get_license(license_id)
        if record is None or record.status != LicenseStatus.ACTIVE:
            return False
        return feature in record.features

    def _sign(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    def _evict_stale_nonces(self, now: float) -> None:
        for n in [k for k, t in self._nonces.items() if now - t > self._NONCE_TTL]:
            del self._nonces[n]

    def _get_license(self, license_id: str) -> Optional[LicenseRecord]:
        if license_id in self._cache:
            return self._cache[license_id]
        if self._db:
            try:
                row = self._db.table("licenses").select("*").eq("license_id", license_id).single().execute()
                if row.data:
                    rec = LicenseRecord(**row.data)
                    self._cache[license_id] = rec
                    return rec
            except Exception as exc:
                self._log.error("DB error fetching license %s: %s", license_id, exc)
        return None

    def _update_status(self, license_id: str, status: LicenseStatus) -> None:
        if self._db:
            try:
                self._db.table("licenses").update({"status": status.value}).eq("license_id", license_id).execute()
            except Exception as exc:
                self._log.error("DB update error %s: %s", license_id, exc)

    def _persist_device(self, license_id: str, device_id: str) -> None:
        if self._db:
            try:
                self._db.table("license_devices").insert({"license_id": license_id, "device_id": device_id, "registered_at": time.time()}).execute()
            except Exception as exc:
                self._log.error("DB device persist error %s: %s", license_id, exc)
