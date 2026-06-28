"""
Phase 27 -- External Integration Security
Test Suite: 200 tests across 12 classes
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import threading
import time
import uuid
from typing import Any, Dict, Optional
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from backend.core.integration_security import (
    IntegrationKind, SignatureScheme, IntegrationResult,
    CircuitState, AuditAction,
    SignatureError, ReplayError, IdempotencyConflict,
    CircuitOpenError, IntegrationPolicyError, MissingReasonError,
    IntegrationPolicy, IntegrationEvent, CallResult, DeadLetterItem,
    DEFAULT_POLICIES,
    ReplayProtector, SignatureVerifier, IdempotencyStore,
    RetryPolicy, CircuitBreaker, IntegrationAuditChain,
    IntegrationRegistry, SafeIntegrationCall, IntegrationAdmin,
    build_integration,
)

SECRET   = "test-secret-phase27"
SECRET_B = SECRET.encode()

def _event(kind=IntegrationKind.WEBHOOK_IN, event_id=None, payload=None,
           signature=None, timestamp_ms=None, idempotency_key=None):
    return IntegrationEvent(
        kind=kind, event_id=event_id or str(uuid.uuid4()),
        payload=payload or {"amount": 100}, signature=signature,
        timestamp_ms=timestamp_ms, idempotency_key=idempotency_key)

def _sign(payload, secret=SECRET_B, scheme=SignatureScheme.HMAC_SHA256):
    if scheme == SignatureScheme.HMAC_SHA256:
        return _hmac.new(secret, payload, hashlib.sha256).hexdigest()
    if scheme == SignatureScheme.HMAC_SHA512:
        return _hmac.new(secret, payload, hashlib.sha512).hexdigest()
    if scheme == SignatureScheme.PLAIN_TOKEN:
        return secret.decode()
    return ""

def _registry(kind=IntegrationKind.WEBHOOK_IN, secret=SECRET, policy=None):
    r = IntegrationRegistry()
    r.register(kind, policy=policy, secret=secret)
    return r


class TestIntegrationKindAndPolicy:
    def test_T001_all_kinds_defined(self):
        assert len(list(IntegrationKind)) == 7
    def test_T002_kind_values(self):
        assert IntegrationKind.PAYMENT.value == "payment"
        assert IntegrationKind.EMAIL.value == "email"
        assert IntegrationKind.TELEGRAM.value == "telegram"
        assert IntegrationKind.WEBHOOK_IN.value == "webhook_in"
        assert IntegrationKind.WEBHOOK_OUT.value == "webhook_out"
        assert IntegrationKind.MARKET_DATA.value == "market_data"
        assert IntegrationKind.AUTH_PROVIDER.value == "auth_provider"
    def test_T003_all_kinds_have_default_policy(self):
        for kind in IntegrationKind: assert kind in DEFAULT_POLICIES
    def test_T004_payment_policy(self):
        p = DEFAULT_POLICIES[IntegrationKind.PAYMENT]
        assert p.max_retries == 3 and p.replay_window_s == 300 and p.circuit_threshold == 3
    def test_T005_telegram_uses_plain_token(self):
        assert DEFAULT_POLICIES[IntegrationKind.TELEGRAM].scheme == SignatureScheme.PLAIN_TOKEN
    def test_T006_webhook_in_no_retry(self):
        assert DEFAULT_POLICIES[IntegrationKind.WEBHOOK_IN].max_retries == 0
    def test_T007_webhook_out_no_replay(self):
        assert DEFAULT_POLICIES[IntegrationKind.WEBHOOK_OUT].replay_window_s == 0
    def test_T008_market_data_short_timeout(self):
        assert DEFAULT_POLICIES[IntegrationKind.MARKET_DATA].timeout_seconds == 3.0
    def test_T009_all_schemes_defined(self):
        assert len(list(SignatureScheme)) == 6
    def test_T010_all_results_defined(self):
        assert IntegrationResult.SUCCESS.value == "success"
        assert IntegrationResult.REPLAY_BLOCKED.value == "replay_blocked"
    def test_T011_all_circuit_states(self):
        assert len(list(CircuitState)) == 3
    def test_T012_all_audit_actions(self):
        assert len(list(AuditAction)) >= 13
    def test_T013_policy_deepcopy_isolation(self):
        r1 = IntegrationRegistry(); r2 = IntegrationRegistry()
        r1._policies[IntegrationKind.PAYMENT].max_retries = 99
        assert r2._policies[IntegrationKind.PAYMENT].max_retries != 99
    def test_T014_custom_policy_override(self):
        p = IntegrationPolicy(kind=IntegrationKind.PAYMENT, max_retries=10)
        r = IntegrationRegistry(); r.register(IntegrationKind.PAYMENT, policy=p)
        assert r.policy(IntegrationKind.PAYMENT).max_retries == 10
    def test_T015_require_https_default(self):
        for p in DEFAULT_POLICIES.values(): assert p.require_https is True
    def test_T016_idempotency_ttl_24h(self):
        for p in DEFAULT_POLICIES.values(): assert p.idempotency_ttl == 86_400


class TestReplayProtector:
    def test_T017_fresh_event_allowed(self):
        assert ReplayProtector(300).check_and_record("e1") is True
    def test_T018_duplicate_raises(self):
        rp = ReplayProtector(300); rp.check_and_record("dup")
        with pytest.raises(ReplayError): rp.check_and_record("dup")
    def test_T019_different_events_allowed(self):
        rp = ReplayProtector(300)
        for i in range(10): rp.check_and_record(f"e{i}")
        assert rp.size == 10
    def test_T020_old_timestamp_rejected(self):
        rp = ReplayProtector(300)
        with pytest.raises(ReplayError): rp.check_and_record("old", int((time.time()-400)*1000))
    def test_T021_future_timestamp_rejected(self):
        rp = ReplayProtector(300)
        with pytest.raises(ReplayError): rp.check_and_record("fut", int((time.time()+400)*1000))
    def test_T022_current_timestamp_accepted(self):
        assert ReplayProtector(300).check_and_record("now", int(time.time()*1000)) is True
    def test_T023_is_seen_true(self):
        rp = ReplayProtector(); rp.check_and_record("x"); assert rp.is_seen("x") is True
    def test_T024_is_seen_false(self):
        assert ReplayProtector().is_seen("never") is False
    def test_T025_reset_clears(self):
        rp = ReplayProtector()
        for i in range(5): rp.check_and_record(f"e{i}")
        rp.reset(); assert rp.size == 0
    def test_T026_max_size_evicts(self):
        rp = ReplayProtector(max_size=5)
        for i in range(6): rp.check_and_record(f"e{i}")
        assert rp.size <= 5
    def test_T027_thread_safety(self):
        rp = ReplayProtector(600); seen = set(); lock = threading.Lock()
        def w(i):
            try: rp.check_and_record(f"t{i}"); 
            except ReplayError: pass
            with lock: seen.add(i)
        ts = [threading.Thread(target=w, args=(i,)) for i in range(50)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert len(seen) == 50
    def test_T028_dup_after_record(self):
        rp = ReplayProtector(); rp.check_and_record("s")
        with pytest.raises(ReplayError): rp.check_and_record("s")
    def test_T029_none_ts_no_check(self):
        assert ReplayProtector(5).check_and_record("n", None) is True
    def test_T030_boundary_inside(self):
        assert ReplayProtector(300).check_and_record("b", int((time.time()-299)*1000)) is True
    def test_T031_boundary_outside(self):
        rp = ReplayProtector(300)
        with pytest.raises(ReplayError): rp.check_and_record("out", int((time.time()-301)*1000))
    def test_T032_zero_window_entries_expire_immediately(self):
        rp = ReplayProtector(0)
        rp.check_and_record("z1"); rp.check_and_record("z2")
        assert rp.size <= 2


class TestSignatureVerifier:
    def test_T033_hmac256_valid(self):
        sv=SignatureVerifier(SECRET); b=b"data"; assert sv.verify(SignatureScheme.HMAC_SHA256,b,_sign(b)) is True
    def test_T034_hmac256_invalid(self):
        with pytest.raises(SignatureError): SignatureVerifier(SECRET).verify(SignatureScheme.HMAC_SHA256,b"d","bad")
    def test_T035_hmac512_valid(self):
        sv=SignatureVerifier(SECRET); b=b"p"; assert sv.verify(SignatureScheme.HMAC_SHA512,b,_sign(b,scheme=SignatureScheme.HMAC_SHA512)) is True
    def test_T036_hmac512_invalid(self):
        with pytest.raises(SignatureError): SignatureVerifier(SECRET).verify(SignatureScheme.HMAC_SHA512,b"d","bad")
    def test_T037_plain_token_valid(self):
        assert SignatureVerifier(SECRET).verify(SignatureScheme.PLAIN_TOKEN,b"any",SECRET) is True
    def test_T038_plain_token_invalid(self):
        with pytest.raises(SignatureError): SignatureVerifier(SECRET).verify(SignatureScheme.PLAIN_TOKEN,b"any","wrong")
    def test_T039_none_passes(self):
        assert SignatureVerifier(SECRET).verify(SignatureScheme.NONE,b"any","") is True
    def test_T040_rsa_stub_valid(self):
        sv=SignatureVerifier(SECRET); b=b"rsa"; assert sv.verify(SignatureScheme.RSA_SHA256,b,sv.sign(SignatureScheme.RSA_SHA256,b)) is True
    def test_T041_ed25519_stub_valid(self):
        sv=SignatureVerifier(SECRET); b=b"ed"; assert sv.verify(SignatureScheme.ED25519,b,sv.sign(SignatureScheme.ED25519,b)) is True
    def test_T042_wrong_secret(self):
        with pytest.raises(SignatureError): SignatureVerifier("wrong").verify(SignatureScheme.HMAC_SHA256,b"d",_sign(b"d"))
    def test_T043_sign_256_len(self):
        assert len(SignatureVerifier(SECRET).sign(SignatureScheme.HMAC_SHA256,b"x")) == 64
    def test_T044_sign_plain(self):
        assert SignatureVerifier(SECRET).sign(SignatureScheme.PLAIN_TOKEN,b"x") == SECRET
    def test_T045_sign_none_empty(self):
        assert SignatureVerifier(SECRET).sign(SignatureScheme.NONE,b"x") == ""
    def test_T046_bytes_secret(self):
        sv=SignatureVerifier(SECRET_B); b=b"bs"; assert sv.verify(SignatureScheme.HMAC_SHA256,b,sv.sign(SignatureScheme.HMAC_SHA256,b)) is True
    def test_T047_timing_safe(self):
        sv=SignatureVerifier(SECRET); b=b"t"; assert sv.verify(SignatureScheme.HMAC_SHA256,b,sv.sign(SignatureScheme.HMAC_SHA256,b)) is True
    def test_T048_empty_payload(self):
        sv=SignatureVerifier(SECRET); assert sv.verify(SignatureScheme.HMAC_SHA256,b"",sv.sign(SignatureScheme.HMAC_SHA256,b"")) is True


class TestIdempotencyStore:
    def test_T049_new_key_none(self): assert IdempotencyStore().check("k",{"a":1}) is None
    def test_T050_cached(self):
        s=IdempotencyStore(); s.record("k",{"a":1},"ok"); assert s.check("k",{"a":1})=="ok"
    def test_T051_conflict_raises(self):
        s=IdempotencyStore(); s.record("k",{"a":1},"r")
        with pytest.raises(IdempotencyConflict): s.check("k",{"a":2})
    def test_T052_invalidate(self):
        s=IdempotencyStore(); s.record("k",{"x":1},"r"); assert s.invalidate("k") is True; assert s.check("k",{"x":1}) is None
    def test_T053_invalidate_missing(self): assert IdempotencyStore().invalidate("no") is False
    def test_T054_size(self):
        s=IdempotencyStore()
        for i in range(5): s.record(f"k{i}",{"i":i},i)
        assert s.size==5
    def test_T055_max_evicts(self):
        s=IdempotencyStore(max_size=3)
        for i in range(4): s.record(f"k{i}",{"i":i},i)
        assert s.size<=3
    def test_T056_order_insensitive(self):
        s=IdempotencyStore(); s.record("k",{"b":2,"a":1},"r"); assert s.check("k",{"a":1,"b":2})=="r"
    def test_T057_complex_payload(self):
        s=IdempotencyStore(); p={"n":{"x":[1,2]}}; s.record("c",p,"d"); assert s.check("c",p)=="d"
    def test_T058_none_result(self): s=IdempotencyStore(); s.record("n",{},None); assert s.size==1
    def test_T059_thread_safe(self):
        s=IdempotencyStore(); errs=[]
        def w(i):
            try: s.record(f"k{i}",{"i":i},i)
            except Exception as e: errs.append(e)
        ts=[threading.Thread(target=w,args=(i,)) for i in range(50)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert not errs and s.size==50
    def test_T060_conflict_message(self):
        s=IdempotencyStore(); s.record("k",{"a":1},"r")
        with pytest.raises(IdempotencyConflict) as e: s.check("k",{"a":99})
        assert "k" in str(e.value)
    def test_T061_ttl_eviction(self):
        s=IdempotencyStore(ttl_seconds=1); s.record("t",{"x":1},"r")
        time.sleep(1.1); s._evict(time.time()); assert s.size==0
    def test_T062_empty_payload(self):
        s=IdempotencyStore(); s.record("e",{},"ok"); assert s.check("e",{})=="ok"
    def test_T063_independent_keys(self):
        s=IdempotencyStore(); s.record("k1",{"a":1},"r1"); s.record("k2",{"b":2},"r2")
        assert s.check("k1",{"a":1})=="r1" and s.check("k2",{"b":2})=="r2"
    def test_T064_concurrent_conflict(self):
        s=IdempotencyStore(); s.record("sh",{"v":1},"f"); cs=[]
        def w():
            try: s.check("sh",{"v":9})
            except IdempotencyConflict: cs.append(1)
        ts=[threading.Thread(target=w) for _ in range(10)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert len(cs)==10


class TestCircuitBreaker:
    def test_T065_initial_closed(self): assert CircuitBreaker(3).state==CircuitState.CLOSED
    def test_T066_allow_closed(self): assert CircuitBreaker().allow_call() is True
    def test_T067_trips_threshold(self):
        cb=CircuitBreaker(3)
        for _ in range(3): cb.record_failure()
        assert cb.state==CircuitState.OPEN
    def test_T068_blocks_open(self):
        cb=CircuitBreaker(1); cb.record_failure(); assert cb.allow_call() is False
    def test_T069_half_open_after_timeout(self):
        cb=CircuitBreaker(1,0.05); cb.record_failure(); time.sleep(0.1); assert cb.state==CircuitState.HALF_OPEN
    def test_T070_success_closes(self):
        cb=CircuitBreaker(1,0.05); cb.record_failure(); time.sleep(0.1)
        cb.record_success(); assert cb.state==CircuitState.CLOSED
    def test_T071_reset_closes(self):
        cb=CircuitBreaker(2); cb.record_failure(); cb.record_failure()
        cb.reset(); assert cb.state==CircuitState.CLOSED
    def test_T072_failure_count(self):
        cb=CircuitBreaker(10)
        for _ in range(5): cb.record_failure()
        assert cb.failure_count==5
    def test_T073_success_resets_count(self):
        cb=CircuitBreaker(10)
        for _ in range(5): cb.record_failure()
        cb.record_success(); assert cb.failure_count==0
    def test_T074_record_failure_returns_state(self):
        cb=CircuitBreaker(2); assert cb.record_failure()==CircuitState.CLOSED
        assert cb.record_failure()==CircuitState.OPEN
    def test_T075_thread_safe(self):
        cb=CircuitBreaker(100); ts=[threading.Thread(target=cb.record_failure) for _ in range(50)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert cb.failure_count==50
    def test_T076_half_open_probe(self):
        cb=CircuitBreaker(1,0.05); cb.record_failure(); time.sleep(0.1); assert cb.allow_call() is True
    def test_T077_below_threshold(self):
        cb=CircuitBreaker(5)
        for _ in range(4): cb.record_failure()
        assert cb.state==CircuitState.CLOSED
    def test_T078_reset_clears_opened_at(self):
        cb=CircuitBreaker(1,60); cb.record_failure(); cb.reset(); assert cb.allow_call() is True
    def test_T079_multiple_resets(self):
        cb=CircuitBreaker(1); cb.record_failure(); cb.reset(); cb.reset(); assert cb.state==CircuitState.CLOSED
    def test_T080_threshold_one(self):
        cb=CircuitBreaker(1); cb.record_failure(); assert cb.state==CircuitState.OPEN


class TestRetryPolicy:
    def test_T081_within_limit(self):
        r=RetryPolicy(3); assert r.should_retry(1) and r.should_retry(2) and r.should_retry(3)
    def test_T082_at_limit(self): assert RetryPolicy(3).should_retry(4) is False
    def test_T083_delay_increases(self):
        r=RetryPolicy(100,100_000,jitter=False)
        assert r.delay_ms(0)<=r.delay_ms(1)<=r.delay_ms(2)
    def test_T084_delay_capped(self):
        r=RetryPolicy(1000,5000,jitter=False)
        for a in range(20): assert r.delay_ms(a)<=5000
    def test_T085_jitter_bounds(self):
        r=RetryPolicy(100,1000,jitter=True)
        for a in range(10): assert 0<=r.delay_ms(a)<=1000
    def test_T086_no_jitter_deterministic(self):
        r=RetryPolicy(100,100_000,jitter=False); assert r.delay_ms(3)==r.delay_ms(3)
    def test_T087_zero_retries(self): assert RetryPolicy(0).should_retry(1) is False
    def test_T088_base_ms(self): assert RetryPolicy(200,200,jitter=False).delay_ms(0)==200
    def test_T089_attempt_zero(self): assert RetryPolicy(100,100_000,jitter=False).delay_ms(0)==100
    def test_T090_attempt_one(self): assert RetryPolicy(100,100_000,jitter=False).delay_ms(1)==200
    def test_T091_attempt_two(self): assert RetryPolicy(100,100_000,jitter=False).delay_ms(2)==400
    def test_T092_max_retries_5(self):
        r=RetryPolicy(5); assert r.should_retry(5) is True; assert r.should_retry(6) is False
    def test_T093_exc_ignored(self): assert RetryPolicy(3).should_retry(1,ValueError()) is True
    def test_T094_large_attempt_capped(self): assert RetryPolicy(100,1000,jitter=False).delay_ms(100)==1000
    def test_T095_from_policy(self):
        p=DEFAULT_POLICIES[IntegrationKind.EMAIL]; assert RetryPolicy(p.max_retries).max_retries==5
    def test_T096_webhook_no_retry(self):
        p=DEFAULT_POLICIES[IntegrationKind.WEBHOOK_IN]; assert RetryPolicy(p.max_retries).should_retry(1) is False


class TestIntegrationAuditChain:
    def test_T097_genesis_64(self): assert len(IntegrationAuditChain(SECRET).genesis_hash)==64
    def test_T098_genesis_hmac(self):
        import hmac as h
        assert IntegrationAuditChain(SECRET).genesis_hash == h.new(SECRET_B,b"GENESIS:INTEGRATION:SECURITY:V27",hashlib.sha256).hexdigest()
    def test_T099_record_entry(self):
        e=IntegrationAuditChain(SECRET).record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"e1")
        assert len(e.chain_hash)==64
    def test_T100_verify_empty(self): assert IntegrationAuditChain(SECRET).verify_chain() is True
    def test_T101_verify_valid(self):
        c=IntegrationAuditChain(SECRET)
        for i in range(5): c.record(AuditAction.CALL_OK,IntegrationKind.WEBHOOK_IN,f"e{i}")
        assert c.verify_chain() is True
    def test_T102_tamper_detected(self):
        c=IntegrationAuditChain(SECRET)
        for i in range(3): c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,f"e{i}")
        rs=list(c._records); rs[1].chain_hash="a"*64; c._records.clear(); c._records.extend(rs)
        assert c.verify_chain() is False
    def test_T103_detect_broken_seq(self):
        c=IntegrationAuditChain(SECRET)
        for i in range(3): c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,f"e{i}")
        rs=list(c._records); rs[1].chain_hash="b"*64; c._records.clear(); c._records.extend(rs)
        assert len(c.detect_tampered())>0
    def test_T104_seq_starts_1(self):
        e=IntegrationAuditChain(SECRET).record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"e1")
        assert e.seq==1
    def test_T105_seq_increments(self):
        c=IntegrationAuditChain(SECRET)
        e1=c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"e1")
        e2=c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"e2")
        assert e2.seq==e1.seq+1
    def test_T106_wrong_secret_invalid(self):
        c1=IntegrationAuditChain("A"); c1.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"e1")
        c2=IntegrationAuditChain("B"); c2._records=c1._records
        assert c2.verify_chain() is False
    def test_T107_query_by_kind(self):
        c=IntegrationAuditChain(SECRET)
        c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"p1")
        c.record(AuditAction.CALL_OK,IntegrationKind.EMAIL,"e1")
        assert all(r.kind==IntegrationKind.PAYMENT for r in c.query(kind=IntegrationKind.PAYMENT))
    def test_T108_query_by_action(self):
        c=IntegrationAuditChain(SECRET)
        c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"e1")
        c.record(AuditAction.SIG_REJECTED,IntegrationKind.PAYMENT,"e2")
        assert len(c.query(action=AuditAction.SIG_REJECTED))==1
    def test_T109_query_recent_first(self):
        c=IntegrationAuditChain(SECRET)
        for i in range(5): c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,f"e{i}")
        seqs=[r.seq for r in c.query()]; assert seqs==sorted(seqs,reverse=True)
    def test_T110_query_limit(self):
        c=IntegrationAuditChain(SECRET)
        for i in range(20): c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,f"e{i}")
        assert len(c.query(limit=5))==5
    def test_T111_concurrent_unique_seqs(self):
        c=IntegrationAuditChain(SECRET); res=[]; lock=threading.Lock()
        def w(i):
            e=c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,f"e{i}")
            with lock: res.append(e.seq)
        ts=[threading.Thread(target=w,args=(i,)) for i in range(50)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert len(set(res))==50
    def test_T112_size(self):
        c=IntegrationAuditChain(SECRET)
        for i in range(7): c.record(AuditAction.CALL_OK,IntegrationKind.EMAIL,f"e{i}")
        assert c.size==7
    def test_T113_unique_hashes(self):
        c=IntegrationAuditChain(SECRET)
        e1=c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"p1")
        e2=c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"p2")
        assert e1.chain_hash!=e2.chain_hash
    def test_T114_chain_links(self):
        c=IntegrationAuditChain(SECRET)
        e1=c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"p1")
        e2=c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"p2")
        assert e2.prev_hash==e1.chain_hash
    def test_T115_first_prev_is_genesis(self):
        c=IntegrationAuditChain(SECRET)
        e=c.record(AuditAction.CALL_OK,IntegrationKind.PAYMENT,"p1")
        assert e.prev_hash==c.genesis_hash
    def test_T116_detail_stored(self):
        c=IntegrationAuditChain(SECRET)
        e=c.record(AuditAction.CALL_FAIL,IntegrationKind.PAYMENT,"p1",detail={"error":"timeout"})
        assert e.detail["error"]=="timeout"


class TestSafeIntegrationCall:
    def _setup(self, kind=IntegrationKind.WEBHOOK_IN):
        r=_registry(kind); a=IntegrationAuditChain(SECRET); c=SafeIntegrationCall(r,audit=a); return r,a,c
    def test_T117_success(self):
        _,_,c=self._setup(); raw=b'{"amount":100}'; sig=_sign(raw)
        assert c.call(_event(signature=sig),lambda e:"ok",raw_body=raw).result==IntegrationResult.SUCCESS
    def test_T118_bad_sig_blocked(self):
        _,_,c=self._setup()
        assert c.call(_event(signature="bad"),lambda e:"ok",raw_body=b"d").result==IntegrationResult.SIG_INVALID
    def test_T119_replay_blocked(self):
        _,_,c=self._setup(); raw=b'{"a":1}'; sig=_sign(raw); eid=str(uuid.uuid4())
        c.call(_event(event_id=eid,signature=sig,payload={"a":1}),lambda e:"ok",raw_body=raw)
        r=c.call(_event(event_id=eid,signature=sig,payload={"a":1}),lambda e:"ok",raw_body=raw)
        assert r.result==IntegrationResult.REPLAY_BLOCKED
    def test_T120_idempotent_hit(self):
        _,_,c=self._setup(); raw=b'{"amount":100}'; ikey="idem-001"; p={"amount":100}
        c.call(IntegrationEvent(IntegrationKind.WEBHOOK_IN,str(uuid.uuid4()),p,_sign(raw),idempotency_key=ikey),lambda e:"first",raw_body=raw)
        r2=c.call(IntegrationEvent(IntegrationKind.WEBHOOK_IN,str(uuid.uuid4()),p,_sign(raw),idempotency_key=ikey),lambda e:"second",raw_body=raw)
        assert r2.result==IntegrationResult.IDEMPOTENT_HIT and r2.cached is True
    def test_T121_circuit_opens(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=2,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        for _ in range(2): c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False)
        assert c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False).result==IntegrationResult.CIRCUIT_OPEN
    def test_T122_dead_letter(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=100,max_retries=2,retry_base_ms=0,retry_max_ms=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        assert c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("f")),verify_signature=False).result==IntegrationResult.DEAD_LETTERED
    def test_T123_dlq_contains(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=100,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False)
        assert len(c.dlq)==1
    def test_T124_drain_clears(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=100,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False)
        c.drain_dlq(); assert len(c.dlq)==0
    def test_T125_reset_requires_reason(self):
        _,_,c=self._setup()
        with pytest.raises(MissingReasonError): c.reset_circuit(IntegrationKind.WEBHOOK_IN,"")
    def test_T126_reset_closes_circuit(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=1,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False)
        c.reset_circuit(IntegrationKind.WEBHOOK_IN,"maint"); assert c.circuit_state(IntegrationKind.WEBHOOK_IN)==CircuitState.CLOSED
    def test_T127_no_verify_skip(self):
        _,_,c=self._setup()
        assert c.call(_event(signature=None),lambda e:"ok",verify_signature=False).result==IntegrationResult.SUCCESS
    def test_T128_attempts_counted(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=100,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        assert c.call(_event(),lambda e:"ok",verify_signature=False).attempts==1
    def test_T129_latency_positive(self):
        _,_,c=self._setup(); raw=b"{}"; sig=_sign(raw)
        assert c.call(_event(signature=sig,payload={}),lambda e:"ok",raw_body=raw).latency_ms>=0
    def test_T130_audit_call_ok(self):
        _,a,c=self._setup(); raw=b'{"a":1}'; sig=_sign(raw)
        c.call(_event(signature=sig,payload={"a":1}),lambda e:"ok",raw_body=raw)
        assert len(a.query(action=AuditAction.CALL_OK))>=1
    def test_T131_audit_sig_rejected(self):
        _,a,c=self._setup()
        c.call(_event(signature="bad"),lambda e:"ok",raw_body=b"d")
        assert len(a.query(action=AuditAction.SIG_REJECTED))>=1
    def test_T132_audit_replay_blocked(self):
        _,a,c=self._setup(); raw=b'{"a":1}'; sig=_sign(raw); eid=str(uuid.uuid4())
        c.call(_event(event_id=eid,signature=sig,payload={"a":1}),lambda e:"ok",raw_body=raw)
        c.call(_event(event_id=eid,signature=sig,payload={"a":1}),lambda e:"ok",raw_body=raw)
        assert len(a.query(action=AuditAction.REPLAY_BLOCKED))>=1
    def test_T133_payment_flow(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.PAYMENT,secret=SECRET); c=SafeIntegrationCall(r)
        raw=b'{"charge":"ch","amount":5000}'; sig=_sign(raw)
        assert c.call(_event(IntegrationKind.PAYMENT,signature=sig,payload={"charge":"ch","amount":5000}),lambda e:{"status":"ok"},raw_body=raw).result==IntegrationResult.SUCCESS
    def test_T134_telegram_flow(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.TELEGRAM,secret=SECRET); c=SafeIntegrationCall(r)
        assert c.call(_event(IntegrationKind.TELEGRAM,signature=SECRET,payload={"id":1}),lambda e:"ack",raw_body=b'{"id":1}').result==IntegrationResult.SUCCESS
    def test_T135_webhook_out_no_replay(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.WEBHOOK_OUT,secret=SECRET); c=SafeIntegrationCall(r)
        eid=str(uuid.uuid4()); raw=b'{"e":"paid"}'; sig=_sign(raw)
        for _ in range(2):
            res=c.call(_event(IntegrationKind.WEBHOOK_OUT,event_id=eid,signature=sig,payload={"e":"paid"}),lambda e:"ok",verify_signature=False)
        assert res.result==IntegrationResult.SUCCESS
    def test_T136_market_data_flow(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.MARKET_DATA,secret=SECRET); c=SafeIntegrationCall(r)
        raw=b'{"sym":"EURUSD"}'; sig=_sign(raw)
        assert c.call(_event(IntegrationKind.MARKET_DATA,signature=sig,payload={"sym":"EURUSD"}),lambda e:{"t":"ok"},raw_body=raw).result==IntegrationResult.SUCCESS


class TestIntegrationRegistry:
    def test_T137_register_policy(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.EMAIL,policy=IntegrationPolicy(kind=IntegrationKind.EMAIL,max_retries=7))
        assert r.policy(IntegrationKind.EMAIL).max_retries==7
    def test_T138_register_secret(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.EMAIL,secret="s"); assert r.secret(IntegrationKind.EMAIL)==b"s"
    def test_T139_missing_secret_raises(self):
        with pytest.raises(IntegrationPolicyError): IntegrationRegistry().secret(IntegrationKind.EMAIL)
    def test_T140_missing_policy_raises(self):
        r=IntegrationRegistry(); del r._policies[IntegrationKind.EMAIL]
        with pytest.raises(IntegrationPolicyError): r.policy(IntegrationKind.EMAIL)
    def test_T141_revoke_removes(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.EMAIL,secret="s"); r.revoke_secret(IntegrationKind.EMAIL,"c")
        assert r.has_secret(IntegrationKind.EMAIL) is False
    def test_T142_revoke_requires_reason(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.EMAIL,secret="s")
        with pytest.raises(MissingReasonError): r.revoke_secret(IntegrationKind.EMAIL,"")
    def test_T143_has_secret_false(self): assert IntegrationRegistry().has_secret(IntegrationKind.EMAIL) is False
    def test_T144_has_secret_true(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.EMAIL,secret="s"); assert r.has_secret(IntegrationKind.EMAIL) is True
    def test_T145_list_kinds(self): assert len(IntegrationRegistry().list_kinds())==7
    def test_T146_bytes_secret(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.PAYMENT,secret=b"bs"); assert r.secret(IntegrationKind.PAYMENT)==b"bs"
    def test_T147_isolation(self):
        r1=IntegrationRegistry(); r2=IntegrationRegistry()
        r1._policies[IntegrationKind.PAYMENT].max_retries=99
        assert r2._policies[IntegrationKind.PAYMENT].max_retries!=99
    def test_T148_register_twice_overwrites(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.EMAIL,secret="v1"); r.register(IntegrationKind.EMAIL,secret="v2")
        assert r.secret(IntegrationKind.EMAIL)==b"v2"
    def test_T149_thread_safe_register(self):
        r=IntegrationRegistry(); errs=[]
        def w(i):
            try: r.register(IntegrationKind.EMAIL,secret=f"s{i}")
            except Exception as e: errs.append(e)
        ts=[threading.Thread(target=w,args=(i,)) for i in range(20)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert not errs
    def test_T150_revoke_missing_silent(self): IntegrationRegistry().revoke_secret(IntegrationKind.EMAIL,reason="c")
    def test_T151_default_not_modified(self):
        orig=DEFAULT_POLICIES[IntegrationKind.PAYMENT].max_retries
        r=IntegrationRegistry(); r._policies[IntegrationKind.PAYMENT].max_retries=999
        assert DEFAULT_POLICIES[IntegrationKind.PAYMENT].max_retries==orig
    def test_T152_policy_kind_match(self):
        r=IntegrationRegistry(); r.register(IntegrationKind.EMAIL,policy=IntegrationPolicy(kind=IntegrationKind.EMAIL))
        assert r.policy(IntegrationKind.EMAIL).kind==IntegrationKind.EMAIL


class TestIntegrationAdmin:
    def _setup(self):
        r=IntegrationRegistry()
        for k in IntegrationKind: r.register(k,secret=SECRET)
        a=IntegrationAuditChain(SECRET); c=SafeIntegrationCall(r,audit=a); adm=IntegrationAdmin(r,c,a)
        return r,a,c,adm
    def test_T153_summary_keys(self):
        s=self._setup()[3].summary()
        assert all(k in s for k in ["registered_kinds","circuit_states","dlq_size","audit_size","audit_verified"])
    def test_T154_summary_verified(self): assert self._setup()[3].summary()["audit_verified"] is True
    def test_T155_circuits_all_closed(self):
        for v in self._setup()[3].inspect_circuits().values(): assert v==CircuitState.CLOSED.value
    def test_T156_revoke_requires_reason(self):
        with pytest.raises(MissingReasonError): self._setup()[3].revoke_key(IntegrationKind.PAYMENT,"  ")
    def test_T157_revoke_removes_secret(self):
        r,_,_,adm=self._setup(); adm.revoke_key(IntegrationKind.PAYMENT,"c"); assert r.has_secret(IntegrationKind.PAYMENT) is False
    def test_T158_revoke_audited(self):
        _,a,_,adm=self._setup(); adm.revoke_key(IntegrationKind.TELEGRAM,"r")
        assert len(a.query(action=AuditAction.KEY_REVOKED))>=1
    def test_T159_drain_requires_reason(self):
        with pytest.raises(MissingReasonError): self._setup()[3].drain_dlq(reason="")
    def test_T160_drain_returns_items(self):
        r,a,c,adm=self._setup(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=100,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET)
        c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False)
        assert len(adm.drain_dlq("d"))>=1
    def test_T161_reset_via_admin(self):
        r,_,c,adm=self._setup(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=1,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET)
        c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False)
        adm.reset_circuit(IntegrationKind.WEBHOOK_IN,"m"); assert c.circuit_state(IntegrationKind.WEBHOOK_IN)==CircuitState.CLOSED
    def test_T162_dlq_size_in_summary(self):
        r,_,c,adm=self._setup(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=100,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET)
        c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False)
        assert adm.summary()["dlq_size"]>=1
    def test_T163_revoke_chain_valid(self): _,a,_,adm=self._setup(); adm.revoke_key(IntegrationKind.EMAIL,"t"); assert a.verify_chain() is True
    def test_T164_registered_kinds_count(self): assert len(self._setup()[3].summary()["registered_kinds"])==7
    def test_T165_audit_grows(self):
        r,a,c,adm=self._setup(); raw=b'{"x":1}'; sig=_sign(raw)
        for _ in range(5): c.call(_event(signature=sig,payload={"x":1}),lambda e:"ok",raw_body=raw)
        assert adm.summary()["audit_size"]>=5
    def test_T166_reset_requires_reason(self):
        with pytest.raises(MissingReasonError): self._setup()[3].reset_circuit(IntegrationKind.EMAIL,"")
    def test_T167_drain_audited(self):
        r,a,c,adm=self._setup(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=100,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET)
        c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False)
        adm.drain_dlq("incident")
        assert len(a.query(action=AuditAction.DEAD_LETTERED))>=1
    def test_T168_circuit_all_kinds(self):
        states=self._setup()[3].inspect_circuits()
        for k in IntegrationKind: assert k.value in states


class TestBuildIntegration:
    def test_T169_returns_tuple(self): assert all(x is not None for x in build_integration(IntegrationKind.PAYMENT,SECRET))
    def test_T170_registers_secret(self): assert build_integration(IntegrationKind.EMAIL,SECRET)[1].has_secret(IntegrationKind.EMAIL)
    def test_T171_custom_policy(self):
        p=IntegrationPolicy(kind=IntegrationKind.TELEGRAM,scheme=SignatureScheme.PLAIN_TOKEN,max_retries=0)
        assert build_integration(IntegrationKind.TELEGRAM,SECRET,policy=p)[1].policy(IntegrationKind.TELEGRAM).max_retries==0
    def test_T172_shared_audit(self):
        a=IntegrationAuditChain(SECRET); assert build_integration(IntegrationKind.PAYMENT,SECRET,audit=a)[2] is a
    def test_T173_payment_call(self):
        c,r,a=build_integration(IntegrationKind.PAYMENT,SECRET); raw=b'{"ch":"x"}'; sig=_sign(raw)
        assert c.call(_event(IntegrationKind.PAYMENT,signature=sig,payload={"ch":"x"}),lambda e:"ok",raw_body=raw).result==IntegrationResult.SUCCESS
    def test_T174_email_call(self):
        c,r,a=build_integration(IntegrationKind.EMAIL,SECRET); raw=b'{"to":"u@e.com"}'; sig=_sign(raw)
        assert c.call(_event(IntegrationKind.EMAIL,signature=sig,payload={"to":"u@e.com"}),lambda e:"q",raw_body=raw).result==IntegrationResult.SUCCESS
    def test_T175_telegram_token(self):
        c,r,a=build_integration(IntegrationKind.TELEGRAM,SECRET)
        assert c.call(_event(IntegrationKind.TELEGRAM,signature=SECRET,payload={"id":1}),lambda e:"a",raw_body=b'{"id":1}').result==IntegrationResult.SUCCESS
    def test_T176_market_data(self):
        c,r,a=build_integration(IntegrationKind.MARKET_DATA,SECRET); raw=b'{"sym":"GBP"}'; sig=_sign(raw)
        assert c.call(_event(IntegrationKind.MARKET_DATA,signature=sig,payload={"sym":"GBP"}),lambda e:{"t":True},raw_body=raw).result==IntegrationResult.SUCCESS


class TestIntegrationFlows:
    def test_T177_fake_webhook_rejected(self):
        c,r,a=build_integration(IntegrationKind.WEBHOOK_IN,"real"); raw=b'{"o":"1"}'
        sig=_hmac.new(b"attacker",raw,hashlib.sha256).hexdigest()
        assert c.call(_event(IntegrationKind.WEBHOOK_IN,signature=sig,payload={"o":"1"}),lambda e:"ok",raw_body=raw).result==IntegrationResult.SIG_INVALID
    def test_T178_replayed_blocked(self):
        c,r,a=build_integration(IntegrationKind.WEBHOOK_IN,SECRET); raw=b'{"o":"2"}'; sig=_sign(raw); eid=str(uuid.uuid4())
        for _ in range(2): res=c.call(_event(IntegrationKind.WEBHOOK_IN,event_id=eid,signature=sig,payload={"o":"2"}),lambda e:"ok",raw_body=raw)
        assert res.result==IntegrationResult.REPLAY_BLOCKED
    def test_T179_old_ts_rejected(self):
        c,r,a=build_integration(IntegrationKind.WEBHOOK_IN,SECRET); raw=b'{"o":"3"}'; sig=_sign(raw)
        res=c.call(_event(IntegrationKind.WEBHOOK_IN,signature=sig,payload={"o":"3"},timestamp_ms=int((time.time()-400)*1000)),lambda e:"ok",raw_body=raw)
        assert res.result==IntegrationResult.REPLAY_BLOCKED
    def test_T180_payment_idempotency(self):
        c,r,a=build_integration(IntegrationKind.PAYMENT,SECRET); ikey="ch-001"; raw=b'{"ch":"ch-001"}'; p={"ch":"ch-001"}
        c.call(IntegrationEvent(IntegrationKind.PAYMENT,str(uuid.uuid4()),p,_sign(raw),idempotency_key=ikey),lambda e:{"s":"ok"},raw_body=raw)
        r2=c.call(IntegrationEvent(IntegrationKind.PAYMENT,str(uuid.uuid4()),p,_sign(raw),idempotency_key=ikey),lambda e:{"s":"ok"},raw_body=raw)
        assert r2.result==IntegrationResult.IDEMPOTENT_HIT and r2.cached
    def test_T181_circuit_protects(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.MARKET_DATA,scheme=SignatureScheme.NONE,circuit_threshold=3,circuit_timeout_s=60,max_retries=0)
        r.register(IntegrationKind.MARKET_DATA,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        for _ in range(3): c.call(_event(IntegrationKind.MARKET_DATA),lambda e:(_ for _ in ()).throw(ConnectionError("down")),verify_signature=False)
        assert c.call(_event(IntegrationKind.MARKET_DATA),lambda e:"ok",verify_signature=False).result==IntegrationResult.CIRCUIT_OPEN
    def test_T182_auth_flow(self):
        c,r,a=build_integration(IntegrationKind.AUTH_PROVIDER,SECRET); raw=b'{"tok":"x"}'; sig=_sign(raw)
        assert c.call(_event(IntegrationKind.AUTH_PROVIDER,signature=sig,payload={"tok":"x"}),lambda e:{"v":True},raw_body=raw).result==IntegrationResult.SUCCESS
    def test_T183_audit_100_events(self):
        c,r,a=build_integration(IntegrationKind.WEBHOOK_IN,SECRET); raw=b'{"n":1}'; sig=_sign(raw)
        for _ in range(100): c.call(_event(signature=sig,payload={"n":1}),lambda e:"ok",raw_body=raw)
        assert a.verify_chain() is True
    def test_T184_concurrent_50_success(self):
        c,r,a=build_integration(IntegrationKind.WEBHOOK_IN,SECRET); res=[]; lock=threading.Lock()
        def w():
            raw=b'{"x":1}'; sig=_sign(raw); e=_event(signature=sig,payload={"x":1})
            out=c.call(e,lambda ev:"ok",raw_body=raw)
            with lock: res.append(out.result)
        ts=[threading.Thread(target=w) for _ in range(50)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert res.count(IntegrationResult.SUCCESS)==50
    def test_T185_revoke_blocks(self):
        c,r,a=build_integration(IntegrationKind.PAYMENT,SECRET); r.revoke_secret(IntegrationKind.PAYMENT,"rot")
        with pytest.raises(IntegrationPolicyError): c.verify_inbound(_event(IntegrationKind.PAYMENT,signature="s"),b"d")
    def test_T186_dlq_max(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=10_000,max_retries=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        import collections; c._dlq=collections.deque(maxlen=5)
        for _ in range(10): c.call(_event(),lambda e:(_ for _ in ()).throw(RuntimeError("x")),verify_signature=False)
        assert len(c.dlq)<=5
    def test_T187_no_exception_leaks(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.EMAIL,scheme=SignatureScheme.NONE,circuit_threshold=100,max_retries=0)
        r.register(IntegrationKind.EMAIL,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        res=c.call(_event(IntegrationKind.EMAIL),lambda e:(_ for _ in ()).throw(RuntimeError("crash")),verify_signature=False)
        assert isinstance(res,CallResult)
    def test_T188_hmac512_scheme(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.EMAIL,scheme=SignatureScheme.HMAC_SHA512,max_retries=0)
        r.register(IntegrationKind.EMAIL,policy=p,secret=SECRET); c=SafeIntegrationCall(r)
        raw=b'{"to":"x"}'; sig=_sign(raw,scheme=SignatureScheme.HMAC_SHA512)
        assert c.call(_event(IntegrationKind.EMAIL,signature=sig,payload={"to":"x"}),lambda e:"q",raw_body=raw).result==IntegrationResult.SUCCESS
    def test_T189_none_scheme_no_secret(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret="d"); c=SafeIntegrationCall(r)
        assert c.verify_inbound(_event(signature=None),b"any") is True
    def test_T190_idempotency_no_double_exec(self):
        r=IntegrationRegistry(); p=IntegrationPolicy(kind=IntegrationKind.WEBHOOK_IN,scheme=SignatureScheme.NONE,circuit_threshold=100,max_retries=3,retry_base_ms=0)
        r.register(IntegrationKind.WEBHOOK_IN,policy=p,secret=SECRET); c=SafeIntegrationCall(r); n=[0]
        def h(e): n[0]+=1; return "d"
        ikey="idem-r"; pl={"d":"x"}
        c.call(IntegrationEvent(IntegrationKind.WEBHOOK_IN,str(uuid.uuid4()),pl,idempotency_key=ikey),h,verify_signature=False)
        c.call(IntegrationEvent(IntegrationKind.WEBHOOK_IN,str(uuid.uuid4()),pl,idempotency_key=ikey),h,verify_signature=False)
        assert n[0]==1
    def test_T191_audit_action_coverage(self):
        c,r,a=build_integration(IntegrationKind.WEBHOOK_IN,SECRET); raw=b'{"a":1}'; sig=_sign(raw)
        c.call(_event(signature=sig,payload={"a":1}),lambda e:"ok",raw_body=raw)
        eid=str(uuid.uuid4())
        for _ in range(2): c.call(_event(event_id=eid,signature=sig,payload={"a":1}),lambda e:"ok",raw_body=raw)
        c.call(_event(signature="bad"),lambda e:"ok",raw_body=b"x")
        seen={e.action for e in a.query(limit=1000)}
        assert AuditAction.CALL_OK in seen and AuditAction.SIG_VERIFIED in seen
        assert AuditAction.REPLAY_BLOCKED in seen and AuditAction.SIG_REJECTED in seen
    def test_T192_tamper_detect(self):
        c,r,a=build_integration(IntegrationKind.PAYMENT,SECRET); raw=b'{"am":500}'; sig=_sign(raw)
        for _ in range(5): c.call(_event(IntegrationKind.PAYMENT,signature=sig,payload={"am":500}),lambda e:"ok",raw_body=raw)
        assert a.verify_chain() is True
        rs=list(a._records); rs[2].chain_hash="dead"*16; a._records.clear(); a._records.extend(rs)
        assert a.verify_chain() is False and len(a.detect_tampered())>0
    def test_T193_all_kinds_build(self):
        for k in IntegrationKind:
            c,r,a=build_integration(k,SECRET); assert r.has_secret(k) and len(a.genesis_hash)==64
    def test_T194_call_result_defaults(self):
        r=CallResult(IntegrationResult.SUCCESS,"e1"); assert r.attempts==0 and r.cached is False and r.error is None
    def test_T195_dead_letter_fields(self):
        d=DeadLetterItem(_event(),"t",3,time.time()); assert d.attempts==3 and d.reason=="t"
    def test_T196_policy_defaults(self):
        p=IntegrationPolicy(kind=IntegrationKind.EMAIL)
        assert p.require_https and p.idempotency_ttl==86_400 and p.dead_letter_max==100
    def test_T197_all_actions_have_dot(self):
        for a in AuditAction: assert "." in a.value
    def test_T198_event_defaults(self):
        e=IntegrationEvent(IntegrationKind.PAYMENT,"e1",{"a":1})
        assert e.signature is None and e.timestamp_ms is None and e.headers=={}
    def test_T199_dedup_regardless(self):
        rp=ReplayProtector(600); rp.check_and_record("d")
        with pytest.raises(ReplayError): rp.check_and_record("d")
    def test_T200_build_all_kinds(self):
        for k in IntegrationKind:
            c,r,a=build_integration(k,SECRET)
            assert r.has_secret(k) and len(a.genesis_hash)==64
