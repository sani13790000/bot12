from __future__ import annotations
import asyncio, hashlib, hmac, json, logging, os, re, time, uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

_LOG = logging.getLogger(__name__)

_TEST_SECRET = "integration-test-secret-key-phase19-secure-32chars"

import base64

def _b64u_enc(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64u_dec(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s)

def make_jwt(payload: dict, secret: str) -> str:
    hdr = _b64u_enc(b'{"alg":"HS256","typ":"JWT"}')
    pld = _b64u_enc(json.dumps(payload).encode())
    sig = hmac.new(secret.encode(), f"{hdr}.{pld}".encode(), hashlib.sha256).digest()
    return f"{hdr}.{pld}.{_b64u_enc(sig)}"

def verify_jwt(token: str, secret: str) -> Optional[Dict]:
    try:
        h, p, s = token.split(".")
        hdr = json.loads(_b64u_dec(h))
        if hdr.get("alg") != "HS256":
            return None
        expected = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64u_dec(s)):
            return None
        payload = json.loads(_b64u_dec(p))
        if payload.get("exp", 0) > 0 and time.time() > payload["exp"]:
            return None
        return payload
    except Exception:
        return None

class LicenseState:
    PENDING   = "pending"
    ACTIVE    = "active"
    EXPIRED   = "expired"
    REVOKED   = "revoked"
    SUSPENDED = "suspended"

@dataclass
class License:
    license_id: str
    user_id: str
    plan: str
    status: str = LicenseState.PENDING
    device_ids: List[str] = field(default_factory=list)
    max_devices: int = 1
    expires_at: float = 0.0
    heartbeat_at: float = 0.0
    key_hash: str = ""

    def activate(self, expires_in: float = 86400.0) -> None:
        self.status = LicenseState.ACTIVE
        self.expires_at = time.time() + expires_in

    def is_active(self) -> bool:
        return (self.status == LicenseState.ACTIVE
                and (self.expires_at == 0 or time.time() < self.expires_at))

    def revoke(self, reason: str = "manual") -> None:
        self.status = LicenseState.REVOKED

    def suspend(self) -> None:
        self.status = LicenseState.SUSPENDED

    def record_heartbeat(self, device_id: str) -> bool:
        if not self.is_active():
            return False
        if device_id not in self.device_ids:
            if len(self.device_ids) >= self.max_devices:
                return False
            self.device_ids.append(device_id)
        self.heartbeat_at = time.time()
        return True

    def heartbeat_age(self) -> float:
        if self.heartbeat_at == 0:
            return float("inf")
        return time.time() - self.heartbeat_at

class SubStatus:
    TRIAL    = "trial"
    ACTIVE   = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    REVOKED  = "revoked"

_VALID_PLANS = {"trial", "basic", "pro", "vip", "annual"}

@dataclass
class Subscription:
    sub_id: str
    user_id: str
    plan: str
    status: str = SubStatus.TRIAL
    invoice_ids: List[str] = field(default_factory=list)
    dunning_count: int = 0

    @property
    def is_active(self) -> bool:
        return self.status in (SubStatus.TRIAL, SubStatus.ACTIVE)

    @property
    def is_terminal(self) -> bool:
        return self.status in (SubStatus.CANCELED, SubStatus.REVOKED)

class BillingEngine:
    def __init__(self) -> None:
        self._subs: Dict[str, Subscription] = {}
        self._invoices: Dict[str, dict] = {}
        self._audit: List[dict] = []

    def checkout(self, user_id: str, plan: str) -> Subscription:
        if plan not in _VALID_PLANS:
            raise ValueError(f"Unknown plan: {plan}")
        for s in self._subs.values():
            if s.user_id == user_id and s.is_active:
                raise ValueError("User already has active subscription")
        sub = Subscription(
            sub_id=f"sub_{uuid.uuid4().hex[:8]}",
            user_id=user_id, plan=plan,
            status=SubStatus.TRIAL if plan == "trial" else SubStatus.ACTIVE,
        )
        self._subs[sub.sub_id] = sub
        self._audit.append({"event": "checkout", "user_id": user_id, "plan": plan,
                             "sub_id": sub.sub_id, "ts": time.time()})
        return sub

    def process_webhook(self, provider: str, provider_ref: str,
                        event: str, sub_id: str) -> dict:
        key = f"{provider}:{provider_ref}"
        if key in self._invoices:
            return {"status": "duplicate", "invoice": self._invoices[key]}
        invoice = {"invoice_id": f"inv_{uuid.uuid4().hex[:8]}",
                   "provider": provider, "provider_ref": provider_ref,
                   "event": event, "sub_id": sub_id, "ts": time.time()}
        self._invoices[key] = invoice
        sub = self._subs.get(sub_id)
        if sub and event == "payment_succeeded":
            sub.status = SubStatus.ACTIVE
            sub.invoice_ids.append(invoice["invoice_id"])
        elif sub and event == "payment_failed":
            sub.dunning_count += 1
            if sub.dunning_count >= 3:
                sub.status = SubStatus.PAST_DUE
        return {"status": "processed", "invoice": invoice}

    def cancel(self, sub_id: str) -> None:
        sub = self._subs.get(sub_id)
        if sub:
            sub.status = SubStatus.CANCELED
            self._audit.append({"event": "cancel", "sub_id": sub_id, "ts": time.time()})

    def get_audit(self) -> List[dict]:
        return list(self._audit)

@dataclass
class Signal:
    signal_id: str
    user_id: str
    symbol: str
    direction: str
    generated_at: float = field(default_factory=time.time)
    expires_in: float = 300.0

    def is_expired(self) -> bool:
        return time.time() > self.generated_at + self.expires_in

class SignalService:
    _DEDUP_WINDOW = 60.0

    def __init__(self) -> None:
        self._seen: Dict[str, float] = {}
        self._signals: List[Signal] = []

    def _dedup_key(self, user_id: str, symbol: str, direction: str) -> str:
        minute = int(time.time() // self._DEDUP_WINDOW)
        return f"{user_id}:{symbol}:{direction}:{minute}"

    def emit(self, user_id: str, symbol: str, direction: str,
             expires_in: float = 300.0) -> Optional[Signal]:
        direction = direction.upper()
        if direction not in ("BUY", "SELL"):
            raise ValueError(f"Invalid direction: {direction}")
        key = self._dedup_key(user_id, symbol, direction)
        if key in self._seen:
            return None
        sig = Signal(signal_id=f"sig_{uuid.uuid4().hex[:8]}",
                     user_id=user_id, symbol=symbol, direction=direction,
                     expires_in=expires_in)
        self._seen[key] = time.time()
        self._signals.append(sig)
        return sig

    def get_signals(self, user_id: str) -> List[Signal]:
        return [s for s in self._signals
                if s.user_id == user_id and not s.is_expired()]

@dataclass
class Trade:
    trade_id: str
    user_id: str
    symbol: str
    direction: str
    lot_size: float
    mt5_ticket: Optional[int] = None
    idempotency_key: str = ""
    status: str = "open"
    opened_at: float = field(default_factory=time.time)

class TradeRegistry:
    def __init__(self) -> None:
        self._trades: Dict[str, Trade] = {}
        self._idem: Dict[str, str] = {}
        self._tickets: Dict[Tuple, str] = {}

    def insert(self, user_id: str, symbol: str, direction: str,
               lot_size: float, idempotency_key: str,
               mt5_ticket: Optional[int] = None) -> Trade:
        if idempotency_key in self._idem:
            return self._trades[self._idem[idempotency_key]]
        if mt5_ticket is not None:
            tkey = (user_id, mt5_ticket)
            if tkey in self._tickets:
                raise ValueError(f"Duplicate MT5 ticket {mt5_ticket} for user {user_id}")
        trade = Trade(
            trade_id=f"trd_{uuid.uuid4().hex[:8]}",
            user_id=user_id, symbol=symbol, direction=direction,
            lot_size=lot_size, mt5_ticket=mt5_ticket,
            idempotency_key=idempotency_key,
        )
        self._trades[trade.trade_id] = trade
        self._idem[idempotency_key] = trade.trade_id
        if mt5_ticket is not None:
            self._tickets[(user_id, mt5_ticket)] = trade.trade_id
        return trade

    def get(self, trade_id: str) -> Optional[Trade]:
        return self._trades.get(trade_id)

class KillSwitchActivatedError(Exception):
    pass

class KillSwitch:
    def __init__(self, max_drawdown_pct: float = 10.0,
                 equity_floor_usd: float = 1000.0) -> None:
        self._active = False
        self._reason = ""
        self._actor  = ""
        self._callbacks: List[Callable] = []
        self._max_drawdown = max_drawdown_pct
        self._equity_floor = equity_floor_usd
        self._peak_equity  = 0.0
        self._reset_token  = ""

    def activate(self, reason: str, actor: str = "system") -> None:
        self._active = True
        self._reason = reason
        self._actor  = actor
        for cb in self._callbacks:
            try:
                cb(reason, actor)
            except Exception as exc:
                _LOG.warning('kill switch callback error: %s', exc)

    def check(self) -> None:
        if self._active:
            raise KillSwitchActivatedError(self._reason)

    def update_equity(self, equity: float) -> bool:
        if equity > self._peak_equity:
            self._peak_equity = equity
        if equity < self._equity_floor:
            self.activate(f"equity_floor {equity:.2f} < {self._equity_floor:.2f}")
            return True
        if self._peak_equity > 0:
            drawdown = (self._peak_equity - equity) / self._peak_equity * 100
            if drawdown >= self._max_drawdown:
                self.activate(f"drawdown {drawdown:.1f}% >= {self._max_drawdown}%")
                return True
        return False

    def reset(self, token: str) -> bool:
        if token != self._reset_token and self._reset_token:
            return False
        self._active = False
        self._reason = ""
        return True

    def set_reset_token(self, token: str) -> None:
        self._reset_token = token

    def add_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str:
        return self._reason

@dataclass
class Position:
    symbol: str
    qty: float
    side: str

class ReconciliationEngine:
    def __init__(self) -> None:
        self._mismatches: List[dict] = []

    def reconcile(self, local: List[Position],
                  broker: List[Position]) -> List[dict]:
        local_map  = {p.symbol: p for p in local}
        broker_map = {p.symbol: p for p in broker}
        symbols    = set(local_map) | set(broker_map)
        mismatches = []
        for sym in symbols:
            lp = local_map.get(sym)
            bp = broker_map.get(sym)
            if lp is None:
                mismatches.append({"symbol": sym, "type": "ghost",
                                   "broker_qty": bp.qty, "local_qty": 0.0})
            elif bp is None:
                mismatches.append({"symbol": sym, "type": "missing",
                                   "broker_qty": 0.0, "local_qty": lp.qty})
            elif abs(lp.qty - bp.qty) > 0.001 or lp.side != bp.side:
                mismatches.append({"symbol": sym, "type": "mismatch",
                                   "broker_qty": bp.qty, "local_qty": lp.qty,
                                   "broker_side": bp.side, "local_side": lp.side})
        self._mismatches.extend(mismatches)
        return mismatches

    def history(self) -> List[dict]:
        return list(self._mismatches)

_ROLE_PERMS: Dict[str, set] = {
    "customer":    {"read:own", "write:own"},
    "support":     {"read:own", "write:own", "read:any"},
    "write_admin": {"read:own", "write:own", "read:any", "write:any"},
    "admin":       {"read:own", "write:own", "read:any", "write:any",
                    "admin:action", "revoke:license"},
    "super_admin": {"read:own", "write:own", "read:any", "write:any",
                    "admin:action", "revoke:license", "super:action"},
}

@dataclass
class AuthContext:
    user_id: str
    role: str = "customer"
    is_active: bool = True
    is_blocked: bool = False
    extra_perms: List[str] = field(default_factory=list)

    def has_perm(self, perm: str) -> bool:
        if self.is_blocked or not self.is_active:
            return False
        perms = _ROLE_PERMS.get(self.role, set()) | set(self.extra_perms)
        return perm in perms

    def assert_perm(self, perm: str) -> None:
        if not self.has_perm(perm):
            raise PermissionError(f"Missing permission: {perm}")

    def assert_owns(self, resource_owner_id: str) -> None:
        if self.user_id == resource_owner_id:
            return
        if self.has_perm("read:any"):
            return
        raise PermissionError("Access denied: not resource owner")

@dataclass
class ReadinessResult:
    passed: bool
    checks: Dict[str, bool]
    failures: List[str]

class ProductionReadinessGate:
    def __init__(self, config: Dict[str, Any]) -> None:
        self._cfg = config

    def run(self) -> ReadinessResult:
        checks: Dict[str, bool] = {}
        failures: List[str] = []

        def chk(name: str, ok: bool, msg: str = "") -> None:
            checks[name] = ok
            if not ok:
                failures.append(msg or name)

        jwt = self._cfg.get("JWT_SECRET_KEY", "")
        chk("jwt_secret_length", len(jwt) >= 32,
            f"JWT_SECRET_KEY too short ({len(jwt)} < 32)")
        chk("jwt_secret_not_weak",
            jwt.lower() not in {"changeme","secret","password","test","dev",""},
            "JWT_SECRET_KEY is a well-known weak value")

        origins = self._cfg.get("ALLOWED_ORIGINS", "*")
        env = self._cfg.get("ENVIRONMENT", "development")
        if env in ("production", "staging"):
            chk("cors_no_wildcard", origins != "*",
                "ALLOWED_ORIGINS=* in production/staging is forbidden")

        chk("force_https",
            self._cfg.get("FORCE_HTTPS", False) or env == "development",
            "FORCE_HTTPS must be True in production")

        mk = self._cfg.get("SECRETS_MASTER_KEY", "")
        chk("master_key_present", len(mk) >= 32,
            f"SECRETS_MASTER_KEY missing or too short ({len(mk)})")

        fk = self._cfg.get("FIELD_ENCRYPTION_KEY", "")
        chk("field_enc_key_present", len(fk) >= 32,
            f"FIELD_ENCRYPTION_KEY missing or too short ({len(fk)})")

        if env == "production":
            chk("debug_off", not self._cfg.get("DEBUG", False),
                "DEBUG must be False in production")

        if env == "production":
            chk("hsts_enabled", self._cfg.get("HSTS_ENABLED", False),
                "HSTS_ENABLED must be True in production")

        return ReadinessResult(
            passed=all(checks.values()),
            checks=checks,
            failures=failures,
        )

class E2EFlowSimulator:
    def __init__(self) -> None:
        self.billing    = BillingEngine()
        self.signals    = SignalService()
        self.trades     = TradeRegistry()
        self.kill_sw    = KillSwitch(max_drawdown_pct=10.0, equity_floor_usd=500.0)
        self.reconcile  = ReconciliationEngine()
        self._licenses: Dict[str, License] = {}
        self._events: List[dict] = []

    def _log(self, event: str, **kw) -> None:
        self._events.append({"event": event, "ts": time.time(), **kw})

    def issue_token(self, user_id: str, role: str = "customer",
                    exp_offset: int = 3600) -> str:
        payload = {"sub": user_id, "role": role,
                   "exp": int(time.time()) + exp_offset,
                   "iat": int(time.time()), "jti": str(uuid.uuid4())}
        return make_jwt(payload, _TEST_SECRET)

    def verify_token(self, token: str) -> Optional[Dict]:
        return verify_jwt(token, _TEST_SECRET)

    def checkout(self, user_id: str, plan: str = "pro") -> Subscription:
        sub = self.billing.checkout(user_id, plan)
        self._log("checkout", user_id=user_id, plan=plan, sub_id=sub.sub_id)
        return sub

    def webhook(self, provider: str, provider_ref: str,
                event: str, sub_id: str) -> dict:
        result = self.billing.process_webhook(provider, provider_ref, event, sub_id)
        self._log("webhook", provider=provider, webhook_event=event, result=result["status"])
        return result

    def create_license(self, user_id: str, plan: str = "pro",
                       max_devices: int = 1) -> License:
        import hashlib
        lic = License(
            license_id=f"lic_{uuid.uuid4().hex[:8]}",
            user_id=user_id, plan=plan, max_devices=max_devices,
        )
        key = f"{user_id}-{lic.license_id}"
        lic.key_hash = hashlib.sha256(key.encode()).hexdigest()
        self._licenses[lic.license_id] = lic
        self._log("license_created", user_id=user_id, license_id=lic.license_id)
        return lic

    def activate_license(self, license_id: str, expires_in: float = 86400.0) -> License:
        lic = self._licenses[license_id]
        lic.activate(expires_in)
        self._log("license_activated", license_id=license_id)
        return lic

    def heartbeat(self, license_id: str, device_id: str) -> bool:
        lic = self._licenses.get(license_id)
        if not lic:
            return False
        ok = lic.record_heartbeat(device_id)
        self._log("heartbeat", license_id=license_id, device_id=device_id, ok=ok)
        return ok

    def emit_signal(self, user_id: str, symbol: str,
                    direction: str) -> Optional[Signal]:
        try:
            self.kill_sw.check()
        except KillSwitchActivatedError:
            self._log("signal_blocked", user_id=user_id, reason="kill_switch")
            return None
        sig = self.signals.emit(user_id, symbol, direction)
        if sig:
            self._log("signal_emitted", user_id=user_id,
                      signal_id=sig.signal_id, symbol=symbol)
        else:
            self._log("signal_duplicate", user_id=user_id, symbol=symbol)
        return sig

    def insert_trade(self, user_id: str, symbol: str, direction: str,
                     lot_size: float, idempotency_key: str,
                     mt5_ticket: Optional[int] = None) -> Trade:
        self.kill_sw.check()
        trade = self.trades.insert(user_id, symbol, direction,
                                   lot_size, idempotency_key, mt5_ticket)
        self._log("trade_inserted", user_id=user_id, trade_id=trade.trade_id)
        return trade

    def update_equity(self, equity: float) -> bool:
        triggered = self.kill_sw.update_equity(equity)
        if triggered:
            self._log("kill_switch_auto", equity=equity, reason=self.kill_sw.reason)
        return triggered

    def run_reconciliation(self, local: List[Position],
                           broker: List[Position]) -> List[dict]:
        mismatches = self.reconcile.reconcile(local, broker)
        self._log("reconciliation", mismatches=len(mismatches))
        return mismatches

    def events(self) -> List[dict]:
        return list(self._events)

    def event_types(self) -> List[str]:
        return [e["event"] for e in self._events]

def assert_true(val: Any) -> None:
    if not val:
        raise AssertionError(f"Expected truthy, got {val!r}")

@dataclass
class SmokeResult:
    name: str
    passed: bool
    latency_ms: float
    error: str = ""

class SmokeTestSuite:
    def __init__(self, simulator: Optional[E2EFlowSimulator] = None) -> None:
        self._sim = simulator or E2EFlowSimulator()
        self._results: List[SmokeResult] = []

    def _run(self, name: str, fn: Callable) -> SmokeResult:
        t0 = time.perf_counter()
        try:
            fn()
            ms = (time.perf_counter() - t0) * 1000
            r = SmokeResult(name=name, passed=True, latency_ms=ms)
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000
            r = SmokeResult(name=name, passed=False, latency_ms=ms, error=str(exc))
        self._results.append(r)
        return r

    def run_all(self) -> List[SmokeResult]:
        uid = f"smoke_{uuid.uuid4().hex[:6]}"

        self._run("jwt_issue_verify", lambda: (
            lambda tok: (
                assert_true(tok is not None),
                assert_true(self._sim.verify_token(tok) is not None),
            )
        )(self._sim.issue_token(uid)))

        self._run("checkout_pro", lambda: (
            lambda sub: assert_true(sub.is_active)
        )(self._sim.checkout(uid, "pro")))

        sub_id = next(s.sub_id for s in self._sim.billing._subs.values()
                      if s.user_id == uid)
        self._run("webhook_idempotency", lambda: (
            lambda r1, r2: (
                assert_true(r1["status"] == "processed"),
                assert_true(r2["status"] == "duplicate"),
            )
        )(
            self._sim.webhook("stripe", f"pi_{uid}", "payment_succeeded", sub_id),
            self._sim.webhook("stripe", f"pi_{uid}", "payment_succeeded", sub_id),
        ))

        lic = self._sim.create_license(uid, "pro")
        self._sim.activate_license(lic.license_id)
        self._run("license_heartbeat", lambda: assert_true(
            self._sim.heartbeat(lic.license_id, "dev_001")
        ))

        self._run("signal_emit_and_dedup", lambda: (
            lambda s1, s2: (
                assert_true(s1 is not None),
                assert_true(s2 is None),
            )
        )(
            self._sim.emit_signal(uid, "EURUSD", "BUY"),
            self._sim.emit_signal(uid, "EURUSD", "BUY"),
        ))

        idem = f"idem_{uuid.uuid4().hex}"
        self._run("trade_idempotency", lambda: (
            lambda t1, t2: assert_true(t1.trade_id == t2.trade_id)
        )(
            self._sim.insert_trade(uid, "EURUSD", "BUY", 0.1, idem),
            self._sim.insert_trade(uid, "EURUSD", "BUY", 0.1, idem),
        ))

        self._run("reconciliation", lambda: (
            lambda mm: assert_true(len(mm) > 0)
        )(self._sim.run_reconciliation(
            [Position("EURUSD", 0.1, "long")],
            [Position("EURUSD", 0.2, "long")],
        )))

        return self._results

    def summary(self) -> dict:
        passed = sum(1 for r in self._results if r.passed)
        return {
            "total": len(self._results),
            "passed": passed,
            "failed": len(self._results) - passed,
            "pass_rate": passed / max(len(self._results), 1),
            "avg_latency_ms": (sum(r.latency_ms for r in self._results)
                               / max(len(self._results), 1)),
        }

class RegressionGuard:
    @staticmethod
    def check_phase11_secret_store() -> bool:
        try:
            import sys
            sys.path.insert(0, "/home/definable/phase11")
            from backend.core.secret_store import SecretStore
            store = SecretStore(master_key="A" * 32)
            store.put("test_key", "test_value")
            assert store.get("test_key") == "test_value"
            return True
        except Exception:
            return False

    @staticmethod
    def check_phase12_error_codes() -> bool:
        try:
            import sys
            sys.path.insert(0, "/home/definable/phase12")
            from backend.core.error_codes import ErrorCode, APIError
            assert hasattr(ErrorCode, "AUTH_INVALID")
            return True
        except Exception:
            return False

    @staticmethod
    def check_phase13_db_migration() -> bool:
        path = ("/home/definable/phase13_db/migrations/"
                "20260626_027_phase13_saas_schema.sql")
        try:
            with open(path) as f:
                content = f.read()
            assert "license_devices" in content
            assert "audit_log" in content
            assert "refresh_tokens" in content
            return True
        except Exception:
            return False

    @staticmethod
    def check_phase14_release() -> bool:
        try:
            import sys
            sys.path.insert(0, "/home/definable/phase14")
            from scripts.build_release import ReleaseManifest
            m = ReleaseManifest(version="19.0", environment="test",
                                checksums={}, artifact_path="test.zip",
                                build_ts=time.time(), git_sha="abc123")
            m.sign("phase14-test-secret-key-minimum32chars!!")
            assert m.verify("phase14-test-secret-key-minimum32chars!!")
            return True
        except Exception:
            return False

    @staticmethod
    def check_phase15_metrics() -> bool:
        try:
            import sys
            sys.path.insert(0, "/home/definable/phase15_obs")
            from backend.observability.metrics_v15 import MetricsRegistry
            reg = MetricsRegistry()
            reg.license_failure("test_reason", "u1")
            snap = reg.admin_snapshot()
            assert "saas_kpis" in snap
            return True
        except Exception:
            return False

    @staticmethod
    def check_phase16_kill_switch() -> bool:
        ks = KillSwitch(max_drawdown_pct=10.0, equity_floor_usd=500.0)
        ks.update_equity(1000.0)
        ks.update_equity(850.0)
        return ks.is_active

    @staticmethod
    def check_phase18_docs() -> bool:
        base = "/home/definable/phase18/docs"
        required = ["README.md", "DEPLOYMENT.md", "SECURITY.md",
                    "MQL5_INSTALLATION.md", "SAAS_RELEASE_GUIDE.md",
                    "ADMIN_MANUAL.md"]
        for name in required:
            path = os.path.join(base, name)
            if not os.path.exists(path):
                return False
            if os.path.getsize(path) < 1000:
                return False
        return True

    def run_all(self) -> Dict[str, bool]:
        return {
            "phase11_secret_store":   self.check_phase11_secret_store(),
            "phase12_error_codes":    self.check_phase12_error_codes(),
            "phase13_db_migration":   self.check_phase13_db_migration(),
            "phase14_release":        self.check_phase14_release(),
            "phase15_metrics":        self.check_phase15_metrics(),
            "phase16_kill_switch":    self.check_phase16_kill_switch(),
            "phase18_docs":           self.check_phase18_docs(),
        }
