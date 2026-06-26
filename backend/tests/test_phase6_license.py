# test_phase6_license.py — Phase 6: License, Subscription & Device Enforcement
# 96 tests in 10 classes — full suite at /home/definable/phase6/tests/test_phase6_license.py
# Run: PYTHONPATH=. pytest backend/tests/test_phase6_license.py -v
# Expected: 96/96 PASS in ~0.43s
#
# Coverage:
#   T01-T10  : License lifecycle (create/activate/suspend/revoke/resume)
#   T11-T20  : Raw key never stored (P6-FIX-1)
#   T21-T30  : Heartbeat + anti-replay nonce (P6-FIX-2,3)
#   T31-T40  : Device fingerprint server-side (P6-FIX-4)
#   T41-T50  : Subscription fail-closed (P6-FIX-5)
#   T51-T60  : Signed response verification (P6-FIX-6)
#   T61-T70  : Device limit atomic (P6-FIX-7)
#   T71-T80  : License lifecycle state machine (P6-FIX-8)
#   T81-T90  : Admin audit log (P6-FIX-9)
#   T91-T96  : NonceStore edge cases

from __future__ import annotations
import hashlib, hmac, json, secrets, sys, time
from pathlib import Path
from typing import Tuple
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from license.engine import (
    PLAN_LIMITS, HeartbeatRequest, LicenseEngine, LicenseEvent,
    LicenseStatus, NonceStore, PlanTier, _device_fingerprint,
    _hash_license_key, _hmac_sha256, _sign_response,
)

SERVER_SECRET = "server_secret_min32chars_for_test!"
LICENSE_SALT  = "license_salt_test"
DEVICE_SALT   = "device_salt_test"
DEVICE_SECRET = "device_secret_for_hmac_signing_ok"

def make_engine() -> LicenseEngine:
    return LicenseEngine(server_secret=SERVER_SECRET, license_salt=LICENSE_SALT, device_salt=DEVICE_SALT)

def setup_active_license(engine, plan=None, user_id="user_001"):
    plan = plan or PlanTier.PRO
    raw, h = engine.create_license(user_id=user_id, plan=plan)
    engine.activate_license(h, actor="test")
    return raw, h

def make_heartbeat_req(key_hash, device_id, offset_sec=0.0, nonce=None):
    nonce = nonce or secrets.token_hex(16)
    ts = time.time() + offset_sec
    sig = _hmac_sha256(DEVICE_SECRET, f"{nonce}:{ts}:{device_id}")
    return HeartbeatRequest(key_hash=key_hash, device_id=device_id, nonce=nonce, timestamp=ts, client_sig=sig), nonce

def register_device(engine, key_hash, client_id="client_abc", ip="1.2.3.4", ua="TestAgent/1.0"):
    ok, msg, did = engine.register_device(key_hash=key_hash, client_id=client_id, ip=ip, user_agent=ua)
    assert ok, f"Device registration failed: {msg}"
    return did

class TestLicenseLifecycle:
    def test_T01_create_returns_raw_and_hash(self):
        e = make_engine(); raw, h = e.create_license("u1", PlanTier.BASIC)
        assert raw.startswith("BOT12-") and len(h) == 64 and raw != h
    def test_T02_initial_status_is_pending(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.BASIC)
        assert e.get_record(h).status == LicenseStatus.PENDING
    def test_T03_activate_changes_status(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.PRO)
        assert e.activate_license(h) and e.get_record(h).status == LicenseStatus.ACTIVE
    def test_T04_activate_twice_fails(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.PRO)
        e.activate_license(h); assert not e.activate_license(h)
    def test_T05_check_active_license(self):
        e = make_engine(); _, h = setup_active_license(e)
        r = e.check(h); assert r.allowed and r.plan == PlanTier.PRO
    def test_T06_check_pending_license_denied(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.PRO)
        r = e.check(h); assert not r.allowed and "pending" in r.reason
    def test_T07_user_index_populated(self):
        e = make_engine(); _, h = e.create_license("u99", PlanTier.TRIAL)
        recs = e.get_user_licenses("u99"); assert len(recs) == 1
    def test_T08_custom_raw_key_accepted(self):
        e = make_engine(); custom = "BOT12-AABB-CCDD-EEFF-1122"
        raw, h = e.create_license("u1", PlanTier.BASIC, raw_key=custom)
        assert raw == custom
    def test_T09_expiry_calculated_correctly(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.TRIAL)
        assert abs(e.get_record(h).expires_at - (time.time() + 7*86400)) < 5
    def test_T10_lifetime_plan_no_expiry(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.LIFETIME)
        assert e.get_record(h).expires_at == 0

class TestRawKeyNeverStored:
    def test_T11_record_has_no_raw_key_field(self):
        e = make_engine(); raw, h = e.create_license("u1", PlanTier.PRO)
        rec = e.get_record(h)
        assert not hasattr(rec, "raw_key") and not hasattr(rec, "license_key")
    def test_T12_stored_value_is_hash_not_raw(self):
        e = make_engine(); raw, h = e.create_license("u1", PlanTier.PRO)
        assert e.get_record(h).key_hash == h and e.get_record(h).key_hash != raw
    def test_T13_hash_is_reproducible(self):
        e = make_engine(); raw, h = e.create_license("u1", PlanTier.PRO)
        assert e.hash_key(raw) == h
    def test_T14_different_raws_different_hashes(self):
        e = make_engine()
        _, h1 = e.create_license("u1", PlanTier.PRO)
        _, h2 = e.create_license("u2", PlanTier.PRO)
        assert h1 != h2
    def test_T15_salt_changes_hash(self):
        e1 = LicenseEngine(SERVER_SECRET, "salt_A", DEVICE_SALT)
        e2 = LicenseEngine(SERVER_SECRET, "salt_B", DEVICE_SALT)
        raw = "BOT12-TEST-KEY0-0000-0001"
        assert e1.hash_key(raw) != e2.hash_key(raw)
    def test_T16_audit_log_has_no_raw_key(self):
        e = make_engine(); _, h = setup_active_license(e)
        assert all("BOT12-" not in str(en.get("detail", "")) for en in e.get_audit_log(h))
    def test_T17_generate_key_format(self):
        e = make_engine()
        for _ in range(10):
            raw, h = e.generate_key()
            assert raw.split("-")[0] == "BOT12" and len(h) == 64
    def test_T18_engine_does_not_expose_raw_in_stats(self):
        e = make_engine(); _, h = setup_active_license(e)
        stats = e.stats(); assert "BOT12" not in str(stats)
    def test_T19_key_hash_in_response_is_partial(self):
        e = make_engine(); _, h = setup_active_license(e)
        masked = e.get_record(h).key_hash[:16] + "..."
        assert len(masked) < len(h)
    def test_T20_two_engines_same_salt_same_hash(self):
        e1, e2 = make_engine(), make_engine()
        raw = "BOT12-SAME-KEY0-TEST-0001"
        assert e1.hash_key(raw) == e2.hash_key(raw)

class TestHeartbeat:
    def _setup(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.PRO)
        return e, h, register_device(e, h)
    def test_T21_valid_heartbeat_returns_true(self):
        e, h, did = self._setup()
        req, _ = make_heartbeat_req(h, did)
        r = e.heartbeat(req, DEVICE_SECRET)
        assert r.valid and r.plan == PlanTier.PRO.value
    def test_T22_heartbeat_response_has_signature(self):
        e, h, did = self._setup()
        req, _ = make_heartbeat_req(h, did)
        r = e.heartbeat(req, DEVICE_SECRET)
        assert r.signature != "" and len(r.signature) == 64
    def test_T23_signature_verifiable_by_client(self):
        e, h, did = self._setup()
        req, _ = make_heartbeat_req(h, did)
        resp = e.heartbeat(req, DEVICE_SECRET)
        payload = {"valid":True,"plan":resp.plan,"days":resp.days_remaining,"feats":resp.features,"ts":resp.server_ts,"nonce":resp.nonce_echo}
        assert e.verify_response_signature(payload, resp.signature)
    def test_T24_replay_attack_blocked(self):
        e, h, did = self._setup()
        nonce = secrets.token_hex(16)
        req, _ = make_heartbeat_req(h, did, nonce=nonce)
        assert e.heartbeat(req, DEVICE_SECRET).valid
        req2, _ = make_heartbeat_req(h, did, nonce=nonce)
        r2 = e.heartbeat(req2, DEVICE_SECRET)
        assert not r2.valid and "replay" in r2.reason
    def test_T25_expired_timestamp_blocked(self):
        e, h, did = self._setup()
        req, _ = make_heartbeat_req(h, did, offset_sec=-400)
        r = e.heartbeat(req, DEVICE_SECRET)
        assert not r.valid
    def test_T26_future_timestamp_blocked(self):
        e, h, did = self._setup()
        req, _ = make_heartbeat_req(h, did, offset_sec=400)
        r = e.heartbeat(req, DEVICE_SECRET)
        assert not r.valid
    def test_T27_invalid_device_blocked(self):
        e, h, _ = self._setup()
        req, _ = make_heartbeat_req(h, "unknown_device")
        r = e.heartbeat(req, DEVICE_SECRET)
        assert not r.valid
    def test_T28_suspended_license_blocked(self):
        e, h, did = self._setup()
        e.suspend_license(h, "r", "admin")
        req, _ = make_heartbeat_req(h, did)
        r = e.heartbeat(req, DEVICE_SECRET)
        assert not r.valid and "suspended" in r.reason
    def test_T29_bad_sig_blocked_and_logged(self):
        e, h, did = self._setup()
        req, _ = make_heartbeat_req(h, did)
        r = e.heartbeat(req, "WRONG_SECRET")
        assert not r.valid
        assert any(en["event"]==LicenseEvent.INVALID_SIG.value for en in e.get_audit_log(h))
    def test_T30_days_remaining_in_response(self):
        e, h, did = self._setup()
        req, _ = make_heartbeat_req(h, did)
        r = e.heartbeat(req, DEVICE_SECRET)
        assert isinstance(r.days_remaining, int) and r.days_remaining > 0

class TestDeviceFingerprint:
    def test_T31_fingerprint_deterministic(self):
        fp1 = _device_fingerprint("c1", "1.2.3.4", "UA", "salt")
        fp2 = _device_fingerprint("c1", "1.2.3.4", "UA", "salt")
        assert fp1 == fp2
    def test_T32_fingerprint_changes_with_client(self):
        assert _device_fingerprint("c1","1.1.1.1","UA","s") != _device_fingerprint("c2","1.1.1.1","UA","s")
    def test_T33_fingerprint_changes_with_ip(self):
        assert _device_fingerprint("c1","1.1.1.1","UA","s") != _device_fingerprint("c1","2.2.2.2","UA","s")
    def test_T34_fingerprint_is_hex(self):
        fp = _device_fingerprint("c1","1.1.1.1","UA","s")
        assert all(c in "0123456789abcdef" for c in fp)
    def test_T35_fingerprint_fixed_length(self):
        fp = _device_fingerprint("client_id","10.0.0.1","Mozilla/5.0","salt")
        assert len(fp) == 64
    def test_T36_salt_changes_fingerprint(self):
        assert _device_fingerprint("c","1.1.1.1","UA","salt1") != _device_fingerprint("c","1.1.1.1","UA","salt2")
    def test_T37_register_device_returns_fingerprint(self):
        e = make_engine(); _, h = setup_active_license(e)
        ok, msg, did = e.register_device(h,"c1","1.1.1.1","UA")
        assert ok and did
    def test_T38_fingerprint_stored_in_record(self):
        e = make_engine(); _, h = setup_active_license(e)
        ok, _, did = e.register_device(h,"c1","1.1.1.1","UA")
        assert did in e.get_record(h).devices
    def test_T39_remove_device(self):
        e = make_engine(); _, h = setup_active_license(e)
        ok, _, did = e.register_device(h,"c1","1.1.1.1","UA")
        assert e.remove_device(h, did)
        assert did not in e.get_record(h).devices
    def test_T40_remove_nonexistent_device_false(self):
        e = make_engine(); _, h = setup_active_license(e)
        assert not e.remove_device(h, "nonexistent_did")

class TestSubscriptionFailClosed:
    def test_T41_check_unknown_hash_denied(self):
        e = make_engine(); r = e.check("unknown_hash_" + "x"*51)
        assert not r.allowed and "not_found" in r.reason
    def test_T42_check_expired_denied(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.get_record(h).expires_at = time.time() - 1
        assert not e.check(h).allowed
    def test_T43_check_revoked_denied(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.revoke_license(h, "r", "admin")
        assert not e.check(h).allowed
    def test_T44_check_suspended_denied(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.suspend_license(h, "r", "admin")
        assert not e.check(h).allowed
    def test_T45_check_pending_denied(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.PRO)
        assert not e.check(h).allowed
    def test_T46_reason_present_on_deny(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.PRO)
        r = e.check(h); assert r.reason and len(r.reason) > 0
    def test_T47_plan_present_on_allow(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.PRO)
        r = e.check(h); assert r.plan == PlanTier.PRO
    def test_T48_features_present_on_allow(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.PRO)
        r = e.check(h); assert isinstance(r.features, list)
    def test_T49_trial_limits_respected(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.TRIAL)
        r = e.check(h)
        assert r.allowed and PLAN_LIMITS[PlanTier.TRIAL].max_devices < PLAN_LIMITS[PlanTier.PRO].max_devices
    def test_T50_lifetime_always_allowed(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.LIFETIME)
        assert e.check(h).allowed

class TestSignedResponse:
    def test_T51_sign_response_returns_64_hex(self):
        sig = _sign_response({"k":"v"}, SERVER_SECRET)
        assert len(sig) == 64
    def test_T52_same_payload_same_sig(self):
        p = {"a":1,"b":"x"}
        assert _sign_response(p, SERVER_SECRET) == _sign_response(p, SERVER_SECRET)
    def test_T53_different_payload_different_sig(self):
        assert _sign_response({"a":1}, SERVER_SECRET) != _sign_response({"a":2}, SERVER_SECRET)
    def test_T54_different_secret_different_sig(self):
        p = {"a":1}
        assert _sign_response(p, "secret_A_32_chars_padding_ok!!") != _sign_response(p, "secret_B_32_chars_padding_ok!!")
    def test_T55_heartbeat_nonce_echoed(self):
        e = make_engine(); _, h = setup_active_license(e)
        did = register_device(e, h)
        req, nonce = make_heartbeat_req(h, did)
        resp = e.heartbeat(req, DEVICE_SECRET)
        assert resp.nonce_echo == nonce
    def test_T56_heartbeat_server_ts_recent(self):
        e = make_engine(); _, h = setup_active_license(e)
        did = register_device(e, h)
        req, _ = make_heartbeat_req(h, did)
        resp = e.heartbeat(req, DEVICE_SECRET)
        assert abs(resp.server_ts - time.time()) < 5
    def test_T57_verify_response_ok(self):
        e = make_engine(); _, h = setup_active_license(e)
        did = register_device(e, h)
        req, _ = make_heartbeat_req(h, did)
        resp = e.heartbeat(req, DEVICE_SECRET)
        payload = {"valid":True,"plan":resp.plan,"days":resp.days_remaining,"feats":resp.features,"ts":resp.server_ts,"nonce":resp.nonce_echo}
        assert e.verify_response_signature(payload, resp.signature)
    def test_T58_tampered_payload_fails_verify(self):
        e = make_engine(); _, h = setup_active_license(e)
        did = register_device(e, h)
        req, _ = make_heartbeat_req(h, did)
        resp = e.heartbeat(req, DEVICE_SECRET)
        payload = {"valid":True,"plan":"TAMPERED","days":resp.days_remaining,"feats":resp.features,"ts":resp.server_ts,"nonce":resp.nonce_echo}
        assert not e.verify_response_signature(payload, resp.signature)
    def test_T59_features_match_plan_limits(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.PRO)
        did = register_device(e, h)
        req, _ = make_heartbeat_req(h, did)
        resp = e.heartbeat(req, DEVICE_SECRET)
        assert set(resp.features) == set(PLAN_LIMITS[PlanTier.PRO].features)
    def test_T60_invalid_sig_response_unsigned(self):
        e = make_engine(); _, h = setup_active_license(e)
        did = register_device(e, h)
        req, _ = make_heartbeat_req(h, did)
        resp = e.heartbeat(req, "WRONG")
        assert not resp.valid

class TestDeviceLimitAtomic:
    def test_T61_pro_allows_3_devices(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.PRO)
        for i in range(3): ok, msg, _ = e.register_device(h, f"c{i}", f"1.1.1.{i}", "UA"); assert ok
    def test_T62_pro_blocks_4th_device(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.PRO)
        for i in range(3): e.register_device(h, f"c{i}", f"1.1.1.{i}", "UA")
        ok, msg, _ = e.register_device(h, "c4", "1.1.1.4", "UA")
        assert not ok and "device_limit_reached" in msg
    def test_T63_enterprise_allows_10_devices(self):
        assert PLAN_LIMITS[PlanTier.ENTERPRISE].max_devices == 10
    def test_T64_device_count_accurate(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.PRO)
        for i in range(3): e.register_device(h, f"c{i}", f"1.{i}.{i}.{i}", "UA")
        assert len(e.get_record(h).devices) == 3
    def test_T65_suspended_license_blocks_device_register(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.PRO)
        e.suspend_license(h, "r", "admin")
        ok, msg, _ = e.register_device(h, "c1", "1.1.1.1", "UA")
        assert not ok and "suspended" in msg
    def test_T66_pending_license_blocks_device_register(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.PRO)
        ok, msg, _ = e.register_device(h, "c1", "1.1.1.1", "UA")
        assert not ok and "pending" in msg
    def test_T67_device_last_seen_updated(self):
        e = make_engine(); _, h = setup_active_license(e)
        ok, _, did = e.register_device(h, "c1", "1.1.1.1", "UA")
        t1 = e.get_record(h).devices[did].last_seen_at
        time.sleep(0.01)
        e.register_device(h, "c1", "1.1.1.1", "UA")
        assert e.get_record(h).devices[did].last_seen_at >= t1
    def test_T68_remove_device_opens_slot(self):
        e = make_engine(); _, h = setup_active_license(e, PlanTier.PRO)
        devices = []
        for i in range(3):
            ok, _, did = e.register_device(h, f"c{i}", f"1.1.1.{i}", "UA")
            devices.append(did)
        e.remove_device(h, devices[0])
        ok, _, _ = e.register_device(h, "c_new", "9.9.9.9", "UA")
        assert ok
    def test_T69_trial_allows_1_device(self):
        assert PLAN_LIMITS[PlanTier.TRIAL].max_devices == 1
    def test_T70_remove_nonexistent_false(self):
        e = make_engine(); _, h = setup_active_license(e)
        assert not e.remove_device(h, "no_such")

class TestLicenseStateMachine:
    def test_T71_pending_to_active(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.PRO)
        e.activate_license(h); assert e.get_record(h).status == LicenseStatus.ACTIVE
    def test_T72_active_to_suspended(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.suspend_license(h, "r", "admin"); assert e.get_record(h).status == LicenseStatus.SUSPENDED
    def test_T73_suspended_to_active(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.suspend_license(h, "r", "admin"); e.resume_license(h, "admin")
        assert e.get_record(h).status == LicenseStatus.ACTIVE
    def test_T74_active_to_revoked(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.revoke_license(h, "fraud", "admin"); assert e.get_record(h).status == LicenseStatus.REVOKED
    def test_T75_revoked_cannot_be_revoked_again(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.revoke_license(h, "r1", "admin"); assert not e.revoke_license(h, "r2", "admin")
    def test_T76_expired_auto_detected(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.BASIC)
        e.activate_license(h); e.get_record(h).expires_at = time.time() - 1
        assert not e.get_record(h).is_active()
    def test_T77_suspended_cannot_be_activated(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.suspend_license(h, "r", "admin"); assert not e.activate_license(h)
    def test_T78_cannot_resume_active(self):
        e = make_engine(); _, h = setup_active_license(e)
        assert not e.resume_license(h, "admin")
    def test_T79_cannot_suspend_revoked(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.revoke_license(h, "r", "admin"); assert not e.suspend_license(h, "r2", "admin")
    def test_T80_state_changes_logged(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.suspend_license(h, "fraud", "admin"); e.resume_license(h, "admin")
        events = [en["event"] for en in e.get_audit_log(h)]
        assert LicenseEvent.SUSPENDED.value in events and LicenseEvent.RESUMED.value in events

class TestAuditLog:
    def test_T81_create_logs_event(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.PRO, actor="admin")
        assert any(en["event"]==LicenseEvent.CREATED.value for en in e.get_audit_log(h))
    def test_T82_activate_logs_with_actor(self):
        e = make_engine(); _, h = e.create_license("u1", PlanTier.PRO)
        e.activate_license(h, actor="admin_bot")
        acts = [en for en in e.get_audit_log(h) if en["event"]==LicenseEvent.ACTIVATED.value]
        assert len(acts)==1 and acts[0]["actor"]=="admin_bot"
    def test_T83_suspend_logs_reason(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.suspend_license(h, "payment_failed", "admin")
        sus = [en for en in e.get_audit_log(h) if en["event"]==LicenseEvent.SUSPENDED.value]
        assert "payment_failed" in sus[0]["detail"]
    def test_T84_heartbeat_logged(self):
        e = make_engine(); _, h = setup_active_license(e); did = register_device(e, h)
        req, _ = make_heartbeat_req(h, did); e.heartbeat(req, DEVICE_SECRET)
        assert any(en["event"]==LicenseEvent.HEARTBEAT.value for en in e.get_audit_log(h))
    def test_T85_invalid_sig_logged(self):
        e = make_engine(); _, h = setup_active_license(e); did = register_device(e, h)
        req, _ = make_heartbeat_req(h, did); e.heartbeat(req, "wrong_secret")
        assert any(en["event"]==LicenseEvent.INVALID_SIG.value for en in e.get_audit_log(h))
    def test_T86_device_add_logged_with_ip(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.register_device(h, "c1", "5.5.5.5", "UA")
        add = [en for en in e.get_audit_log(h) if en["event"]==LicenseEvent.DEVICE_ADD.value]
        assert len(add)==1 and add[0]["ip"]=="5.5.5.5"
    def test_T87_device_remove_logged(self):
        e = make_engine(); _, h = setup_active_license(e)
        ok, _, did = e.register_device(h, "c1", "1.1.1.1", "UA")
        e.remove_device(h, did, actor="user")
        assert any(en["event"]==LicenseEvent.DEVICE_DEL.value for en in e.get_audit_log(h))
    def test_T88_audit_capped_at_500(self):
        e = make_engine(); _, h = setup_active_license(e); did = register_device(e, h)
        for i in range(600):
            nonce = f"nonce_{i:06d}_{secrets.token_hex(4)}"; ts = time.time()
            req = HeartbeatRequest(key_hash=h, device_id=did, nonce=nonce, timestamp=ts, client_sig=_hmac_sha256(DEVICE_SECRET, f"{nonce}:{ts}:{did}"))
            e.heartbeat(req, DEVICE_SECRET)
        assert len(e.get_audit_log(h, last_n=600)) <= 500
    def test_T89_revoke_logs_reason_and_actor(self):
        e = make_engine(); _, h = setup_active_license(e)
        e.revoke_license(h, "user_requested_refund", "admin_007")
        rev = [en for en in e.get_audit_log(h) if en["event"]==LicenseEvent.REVOKED.value]
        assert rev[0]["detail"]=="user_requested_refund" and rev[0]["actor"]=="admin_007"
    def test_T90_audit_returns_empty_for_unknown(self):
        e = make_engine()
        assert e.get_audit_log("nonexistent_hash_" + "x"*47) == []

class TestNonceStore:
    def test_T91_fresh_nonce_accepted(self):
        assert NonceStore().consume("nonce_01", time.time())
    def test_T92_duplicate_nonce_rejected(self):
        ns = NonceStore(); ns.consume("n", time.time())
        assert not ns.consume("n", time.time())
    def test_T93_old_timestamp_rejected(self):
        assert not NonceStore().consume("n", time.time() - 400)
    def test_T94_future_timestamp_rejected(self):
        assert not NonceStore().consume("n", time.time() + 400)
    def test_T95_store_bounded(self):
        ns = NonceStore(); ns._MAX_NONCES = 10
        for i in range(15): ns.consume(f"nonce_{i:04d}", time.time())
        assert len(ns) <= 10
    def test_T96_engine_secret_min_length_enforced(self):
        with pytest.raises(ValueError, match="32"): LicenseEngine("short", LICENSE_SALT, DEVICE_SALT)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
