from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.tenant import (
    CrossTenantAccessError,
    assert_tenant_access,
)


class TenantScopedStore:
    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _bucket(self, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            if tenant_id not in self._data:
                self._data[tenant_id] = {}
            return self._data[tenant_id]

    def _assert_access(
        self, resource_tenant_id, actor_tenant_id, actor_role, actor_id, label="record"
    ):
        assert_tenant_access(
            resource_tenant_id=resource_tenant_id,
            actor_tenant_id=actor_tenant_id,
            actor_role=actor_role,
            actor_id=actor_id,
            resource_label=label,
        )

    def put(self, key, value, tenant_id):
        self._bucket(tenant_id)[key] = value

    def get(self, key, tenant_id, actor_tenant_id, actor_role, actor_id):
        self._assert_access(tenant_id, actor_tenant_id, actor_role, actor_id)
        return self._bucket(tenant_id).get(key)

    def list_all(self, tenant_id, actor_tenant_id, actor_role, actor_id):
        self._assert_access(tenant_id, actor_tenant_id, actor_role, actor_id)
        return list(self._bucket(tenant_id).values())

    def delete(self, key, tenant_id, actor_tenant_id, actor_role, actor_id):
        self._assert_access(tenant_id, actor_tenant_id, actor_role, actor_id)
        bucket = self._bucket(tenant_id)
        existed = key in bucket
        bucket.pop(key, None)
        return existed

    def reset(self):
        with self._lock:
            self._data.clear()

    def tenant_count(self, tenant_id):
        return len(self._bucket(tenant_id))

    def all_tenant_ids(self):
        with self._lock:
            return list(self._data.keys())


@dataclass
class LicenseRecord:
    license_id: str
    tenant_id: str
    user_id: str
    key_hash: str
    status: str = "pending"
    device_ids: List[str] = field(default_factory=list)
    max_devices: int = 1
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def is_active(self):
        return self.status == "active" and not self.is_expired


class TenantLicenseStore(TenantScopedStore):
    def issue(self, tenant_id, user_id, key_hash, max_devices=1, ttl_seconds=None):
        lic = LicenseRecord(
            license_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            key_hash=key_hash,
            status="active",
            max_devices=max_devices,
            expires_at=time.time() + ttl_seconds if ttl_seconds else None,
        )
        self.put(lic.license_id, lic, tenant_id)
        return lic

    def get_license(self, license_id, tenant_id, actor_tenant_id, actor_role, actor_id):
        return self.get(license_id, tenant_id, actor_tenant_id, actor_role, actor_id)

    def revoke(self, license_id, tenant_id):
        bucket = self._bucket(tenant_id)
        lic = bucket.get(license_id)
        if not lic:
            return False
        lic.status = "revoked"
        return True

    def add_device(self, license_id, tenant_id, device_id):
        bucket = self._bucket(tenant_id)
        lic = bucket.get(license_id)
        if not lic or not lic.is_active:
            return False
        if device_id in lic.device_ids:
            return True
        if len(lic.device_ids) >= lic.max_devices:
            return False
        lic.device_ids.append(device_id)
        return True


@dataclass
class SignalRecord:
    signal_id: str
    tenant_id: str
    user_id: str
    symbol: str
    direction: str
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class TenantSignalStore(TenantScopedStore):
    def emit(self, tenant_id, user_id, symbol, direction, ttl_seconds=3600.0):
        bucket = self._bucket(tenant_id)
        now = time.time()
        for rec in bucket.values():
            if (
                isinstance(rec, SignalRecord)
                and rec.user_id == user_id
                and rec.symbol == symbol
                and rec.direction == direction
                and (now - rec.created_at) < 60.0
            ):
                return None
        sig = SignalRecord(
            signal_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            symbol=symbol,
            direction=direction,
            expires_at=now + ttl_seconds,
        )
        self.put(sig.signal_id, sig, tenant_id)
        return sig

    def list_signals(self, tenant_id, actor_tenant_id, actor_role, actor_id):
        records = self.list_all(tenant_id, actor_tenant_id, actor_role, actor_id)
        return [r for r in records if isinstance(r, SignalRecord)]


@dataclass
class BotInstance:
    bot_id: str
    tenant_id: str
    user_id: str
    symbol: str
    status: str = "running"
    started_at: float = field(default_factory=time.time)


class TenantBotStore(TenantScopedStore):
    def register(self, tenant_id, user_id, symbol, max_bots=1):
        bucket = self._bucket(tenant_id)
        running = sum(
            1
            for b in bucket.values()
            if isinstance(b, BotInstance) and b.user_id == user_id and b.status == "running"
        )
        if running >= max_bots:
            return None
        bot = BotInstance(
            bot_id=str(uuid.uuid4()), tenant_id=tenant_id, user_id=user_id, symbol=symbol
        )
        self.put(bot.bot_id, bot, tenant_id)
        return bot

    def stop(self, bot_id, tenant_id):
        bucket = self._bucket(tenant_id)
        bot = bucket.get(bot_id)
        if not bot:
            return False
        bot.status = "stopped"
        return True

    def list_bots(self, tenant_id, actor_tenant_id, actor_role, actor_id):
        records = self.list_all(tenant_id, actor_tenant_id, actor_role, actor_id)
        return [r for r in records if isinstance(r, BotInstance)]


@dataclass
class LogEntry:
    log_id: str
    tenant_id: str
    level: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class TenantLogStore(TenantScopedStore):
    MAX_PER_TENANT = 10_000

    def append(self, tenant_id, level, message, **ctx):
        entry = LogEntry(
            log_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            level=level,
            message=message,
            context=dict(ctx),
        )
        bucket = self._bucket(tenant_id)
        if len(bucket) >= self.MAX_PER_TENANT:
            oldest_key = next(iter(bucket))
            del bucket[oldest_key]
        bucket[entry.log_id] = entry
        return entry

    def get_logs(self, tenant_id, actor_tenant_id, actor_role, actor_id, limit=100):
        records = self.list_all(tenant_id, actor_tenant_id, actor_role, actor_id)
        logs = [r for r in records if isinstance(r, LogEntry)]
        return sorted(logs, key=lambda x: x.created_at, reverse=True)[:limit]


@dataclass
class AuditEntry:
    audit_id: str
    tenant_id: str
    actor_id: str
    actor_role: str
    action: str
    resource: str
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class TenantAuditStore(TenantScopedStore):
    def record(self, tenant_id, actor_id, actor_role, action, resource, **meta):
        entry = AuditEntry(
            audit_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            resource=resource,
            meta=dict(meta),
        )
        self._bucket(tenant_id)[entry.audit_id] = entry
        return entry

    def get_for_tenant(self, tenant_id, actor_tenant_id, actor_role, actor_id):
        records = self.list_all(tenant_id, actor_tenant_id, actor_role, actor_id)
        entries = [r for r in records if isinstance(r, AuditEntry)]
        return sorted(entries, key=lambda x: x.created_at, reverse=True)

    def admin_global_view(self, admin_role):
        if admin_role not in {"admin", "super_admin"}:
            raise CrossTenantAccessError("admin_global_view requires admin role")
        all_entries = []
        with self._lock:
            for bucket in self._data.values():
                for v in bucket.values():
                    if isinstance(v, AuditEntry):
                        all_entries.append(v)
        return sorted(all_entries, key=lambda x: x.created_at, reverse=True)


_license_store = TenantLicenseStore()
_signal_store = TenantSignalStore()
_bot_store = TenantBotStore()
_log_store = TenantLogStore()
_audit_store = TenantAuditStore()


def get_license_store():
    return _license_store


def get_signal_store():
    return _signal_store


def get_bot_store():
    return _bot_store


def get_log_store():
    return _log_store


def get_audit_store():
    return _audit_store
