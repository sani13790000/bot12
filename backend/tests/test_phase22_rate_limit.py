from __future__ import annotations
import sys, os, time, threading
sys.path.insert(0, "/home/definable/phase22")

import pytest
from backend.core.rate_limit_v22 import (
    RateLimiter, RateLimitStore, RateLimitTier, RateLimitResult,
    AbuseType, AbuseDetector, BackoffTracker, SlidingWindowChecker,
    TokenBucket, EndpointLimit, TierLimits,
    TIER_LIMITS, ENDPOINT_LIMITS, WHITELIST_PREFIXES,
    make_rate_limit_headers, get_rate_limiter, reset_global_limiter,
    BAN_TTL_SECONDS, MAX_BACKOFF_SECS,
)
from backend.middleware.rate_limit_middleware import (
    RateLimitMiddleware, extract_ip, resolve_tier,
)
from backend.api.routes.rate_limit_routes import RateLimitAdminRouter


@pytest.fixture(autouse=True)
def fresh_limiter():
    reset_global_limiter()
    yield
    reset_global_limiter()

@pytest.fixture
def store(): return RateLimitStore()

@pytest.fixture
def limiter(): return RateLimiter()

@pytest.fixture
def checker(store): return SlidingWindowChecker(store)

@pytest.fixture
def backoff(store): return BackoffTracker(store)

@pytest.fixture
def abuse(store): return AbuseDetector(store)

@pytest.fixture
def router(limiter): return RateLimitAdminRouter(limiter)


class TestRateLimitTierConfig:
    def test_T001_all_tiers_defined(self):
        for tier in RateLimitTier: assert tier in TIER_LIMITS
    def test_T002_anonymous_lowest_rpm(self):
        anon = TIER_LIMITS[RateLimitTier.ANONYMOUS].rpm
        for tier in [RateLimitTier.BASIC, RateLimitTier.PRO, RateLimitTier.VIP]:
            assert TIER_LIMITS[tier].rpm > anon
    def test_T003_internal_highest_rpm(self):
        internal_rpm = TIER_LIMITS[RateLimitTier.INTERNAL].rpm
        for tier in RateLimitTier:
            if tier != RateLimitTier.INTERNAL: assert TIER_LIMITS[tier].rpm <= internal_rpm
    def test_T004_all_endpoints_have_limits(self):
        for path, cfg in ENDPOINT_LIMITS.items(): assert cfg.requests > 0 and cfg.window > 0
    def test_T005_auth_endpoint_strict(self):
        login = ENDPOINT_LIMITS["/api/auth/login"]
        assert login.requests <= 5 and login.window >= 60
    def test_T006_health_endpoint_unlimited(self):
        assert ENDPOINT_LIMITS["/health"].requests >= 9999
    def test_T007_whitelist_paths(self):
        assert "/health" in WHITELIST_PREFIXES and "/metrics" in WHITELIST_PREFIXES
    def test_T008_tier_escalation(self):
        tiers = [RateLimitTier.ANONYMOUS, RateLimitTier.TRIAL, RateLimitTier.BASIC,
                 RateLimitTier.PRO, RateLimitTier.VIP, RateLimitTier.ADMIN]
        rpms = [TIER_LIMITS[t].rpm for t in tiers]
        assert rpms == sorted(rpms)
    def test_T009_burst_positive(self):
        for _, cfg in TIER_LIMITS.items(): assert cfg.burst >= 0
    def test_T010_ban_threshold_scales(self):
        assert TIER_LIMITS[RateLimitTier.ADMIN].ban_threshold > TIER_LIMITS[RateLimitTier.ANONYMOUS].ban_threshold
    def test_T011_endpoint_limit_fields(self):
        ep = EndpointLimit(requests=10, window=60, burst=2, reason="test")
        assert ep.requests == 10 and ep.window == 60
    def test_T012_tier_limit_fields(self):
        tl = TierLimits(RateLimitTier.BASIC, rpm=120, burst=20, ban_threshold=15)
        assert tl.rpm == 120
    def test_T013_trial_equals_readonly_or_more(self):
        assert TIER_LIMITS[RateLimitTier.TRIAL].rpm >= TIER_LIMITS[RateLimitTier.ANONYMOUS].rpm
    def test_T014_vip_more_than_pro(self):
        assert TIER_LIMITS[RateLimitTier.VIP].rpm > TIER_LIMITS[RateLimitTier.PRO].rpm
    def test_T015_admin_more_than_vip(self):
        assert TIER_LIMITS[RateLimitTier.ADMIN].rpm > TIER_LIMITS[RateLimitTier.VIP].rpm
    def test_T016_abuse_types_enum(self):
        types = list(AbuseType)
        assert AbuseType.CREDENTIAL_STUFFING in types and AbuseType.SCRAPING in types


class TestRateLimitStore:
    def test_T017_get_record_creates(self, store):
        rec = store.get_record("ip:1.2.3.4")
        assert rec.key == "ip:1.2.3.4"
    def test_T018_get_record_same_object(self, store):
        assert store.get_record("ip:x") is store.get_record("ip:x")
    def test_T019_reset_removes_record(self, store):
        store.get_record("ip:x")
        store.reset("ip:x")
        assert len(store.get_record("ip:x").timestamps) == 0
    def test_T020_ban_creates_record(self, store):
        ban = store.ban("1.2.3.4", "test", ttl=60)
        assert ban.ip == "1.2.3.4"
    def test_T021_is_banned_returns_record(self, store):
        store.ban("1.2.3.4", "test", ttl=60)
        assert store.is_banned("1.2.3.4") is not None
    def test_T022_is_banned_expired(self, store):
        store.ban("1.2.3.4", "test", ttl=0.001)
        time.sleep(0.01)
        assert store.is_banned("1.2.3.4") is None
    def test_T023_unban(self, store):
        store.ban("1.2.3.4", "test", ttl=3600)
        assert store.unban("1.2.3.4") is True
        assert store.is_banned("1.2.3.4") is None
    def test_T024_unban_nonexistent(self, store): assert store.unban("9.9.9.9") is False
    def test_T025_list_bans(self, store):
        store.ban("1.1.1.1", "r1", ttl=3600)
        store.ban("2.2.2.2", "r2", ttl=3600)
        ips = [b.ip for b in store.list_bans()]
        assert "1.1.1.1" in ips and "2.2.2.2" in ips
    def test_T026_record_fail(self, store):
        assert store.record_fail("1.2.3.4", "/api/auth/login").fail_count == 1
    def test_T027_record_fail_accumulates(self, store):
        for _ in range(5): store.record_fail("1.2.3.4", "/api/auth/login")
        assert store.get_abuse("1.2.3.4").fail_count == 5
    def test_T028_record_error(self, store):
        assert store.record_error("1.2.3.4").error_count == 1
    def test_T029_stats(self, store):
        store.get_record("ip:x")
        s = store.stats()
        assert "tracked_keys" in s and "active_bans" in s
    def test_T030_reset_all(self, store):
        store.get_record("ip:x")
        store.ban("1.2.3.4", "r", ttl=3600)
        store.reset_all()
        assert store.stats()["tracked_keys"] == 0
    def test_T031_thread_safe_ban(self, store):
        errors = []
        def f(i):
            try: store.ban(f"10.0.0.{i}", f"r{i}", ttl=60)
            except Exception as e: errors.append(e)
        ts = [threading.Thread(target=f, args=(i,)) for i in range(20)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert not errors
    def test_T032_abuse_record_get(self, store):
        rec = store.get_abuse("5.5.5.5")
        assert rec.ip == "5.5.5.5" and rec.fail_count == 0


class TestSlidingWindowChecker:
    def test_T033_allow_within_limit(self, checker):
        for _ in range(5): assert checker.check("k", 10, 60)[0]
    def test_T034_deny_over_limit(self, checker):
        for _ in range(10): checker.check("k", 10, 60)
        assert not checker.check("k", 10, 60)[0]
    def test_T035_remaining_decreases(self, checker):
        _, r1, _ = checker.check("k", 10, 60)
        _, r2, _ = checker.check("k", 10, 60)
        assert r2 < r1
    def test_T036_retry_after_positive_on_deny(self, checker):
        for _ in range(5): checker.check("k", 5, 60)
        assert checker.check("k", 5, 60)[2] > 0
    def test_T037_burst_allowance(self, checker):
        for _ in range(8): assert checker.check("k", 5, 60, burst=3)[0]
        assert not checker.check("k", 5, 60, burst=3)[0]
    def test_T038_no_consume_dry_run(self, checker):
        for _ in range(5): checker.check("k", 5, 60, consume=False)
        assert checker.check("k", 5, 60, consume=False)[0]
    def test_T039_window_prune(self, checker, store):
        rec = store.get_record("k")
        for _ in range(5): rec.timestamps.append(time.monotonic() - 120)
        assert checker.check("k", 5, 60)[0]
    def test_T040_different_keys_independent(self, checker):
        for _ in range(5): checker.check("a", 5, 60)
        assert not checker.check("a", 5, 60)[0]
        assert checker.check("b", 5, 60)[0]
    def test_T041_remaining_zero_on_deny(self, checker):
        for _ in range(5): checker.check("k", 5, 60)
        assert checker.check("k", 5, 60)[1] == 0
    def test_T042_limit_one(self, checker):
        assert checker.check("k", 1, 60)[0]
        assert not checker.check("k", 1, 60)[0]
    def test_T043_concurrent_checker(self, checker):
        results = []
        def hit(): results.append(checker.check("k", 50, 60)[0])
        ts = [threading.Thread(target=hit) for _ in range(60)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert sum(1 for r in results if r) == 50
    def test_T044_burst_zero(self, checker):
        for _ in range(3): checker.check("k", 3, 60, burst=0)
        assert not checker.check("k", 3, 60, burst=0)[0]
    def test_T045_large_window(self, checker):
        for _ in range(100): assert checker.check("k", 100, 3600)[0]
    def test_T046_large_limit(self, checker):
        for _ in range(500): assert checker.check("k", 500, 60)[0]
        assert not checker.check("k", 500, 60)[0]
    def test_T047_retry_after_non_negative(self, checker):
        for _ in range(5): checker.check("k", 5, 60)
        assert checker.check("k", 5, 60)[2] >= 0
    def test_T048_prune_exact_boundary(self, checker, store):
        rec = store.get_record("k")
        rec.timestamps.append(time.monotonic() - 61)
        assert checker.check("k", 1, 60)[0]


class TestTokenBucket:
    def test_T049_consume_within_capacity(self):
        assert TokenBucket(10, 1.0).consume(5)
    def test_T050_consume_exact_capacity(self):
        assert TokenBucket(5, 0.1).consume(5)
    def test_T051_consume_over_capacity_fails(self):
        b = TokenBucket(3, 0.01); b.consume(3); assert not b.consume(1)
    def test_T052_available_positive(self):
        assert TokenBucket(10, 1.0).available > 0
    def test_T053_reset_restores(self):
        b = TokenBucket(5, 0.01); b.consume(5); assert not b.consume(1); b.reset(); assert b.consume(1)
    def test_T054_refill_over_time(self):
        b = TokenBucket(10, 100.0); b.consume(10); time.sleep(0.05); assert b.available > 0
    def test_T055_thread_safe_consume(self):
        b = TokenBucket(50, 0.01); results = []
        def f(): results.append(b.consume(1))
        ts = [threading.Thread(target=f) for _ in range(60)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert sum(results) == 50
    def test_T056_capacity_not_exceeded(self):
        b = TokenBucket(5, 1000.0); time.sleep(0.01); assert b.available <= 5.0


class TestBackoffTracker:
    def test_T057_first_violation_backoff_2s(self, backoff):
        assert backoff.record_violation("k") == 2.0
    def test_T058_second_violation_backoff_4s(self, backoff):
        backoff.record_violation("k"); assert backoff.record_violation("k") == 4.0
    def test_T059_exponential_growth(self, backoff):
        vals = [backoff.record_violation("k") for _ in range(5)]
        assert vals == sorted(vals)
    def test_T060_max_backoff_capped(self, backoff):
        for _ in range(20): backoff.record_violation("k")
        assert backoff.record_violation("k") <= MAX_BACKOFF_SECS
    def test_T061_is_in_backoff_true(self, backoff):
        backoff.record_violation("k")
        in_bo, rem = backoff.is_in_backoff("k")
        assert in_bo and rem > 0
    def test_T062_is_in_backoff_false_fresh(self, backoff):
        in_bo, rem = backoff.is_in_backoff("k")
        assert not in_bo and rem == 0
    def test_T063_clear_backoff(self, backoff):
        backoff.record_violation("k"); backoff.clear("k")
        assert not backoff.is_in_backoff("k")[0]
    def test_T064_different_keys_isolated(self, backoff):
        backoff.record_violation("k1"); assert not backoff.is_in_backoff("k2")[0]
    def test_T065_violation_count_stored(self, backoff, store):
        backoff.record_violation("k"); assert store.get_record("k").violations == 1
    def test_T066_backoff_remaining_positive(self, backoff):
        backoff.record_violation("k"); assert backoff.is_in_backoff("k")[1] > 0


class TestAbuseDetector:
    def test_T067_auth_fail_below_threshold(self, abuse):
        ban = None
        for _ in range(4): ban = abuse.record_auth_fail("1.2.3.4")
        assert ban is None
    def test_T068_auth_fail_triggers_ban(self, abuse):
        ban = None
        for _ in range(5): ban = abuse.record_auth_fail("2.3.4.5")
        assert ban is not None and ban.ip == "2.3.4.5"
    def test_T069_ban_has_abuse_type(self, abuse):
        ban = None
        for _ in range(5): ban = abuse.record_auth_fail("3.4.5.6")
        assert ban.abuse_type == AbuseType.CREDENTIAL_STUFFING
    def test_T070_error_triggers_ban(self, abuse):
        ban = None
        for _ in range(25): ban = abuse.record_error("5.6.7.8")
        assert ban is not None
    def test_T071_scraping_detect(self, abuse):
        ban = abuse.detect_scraping("6.7.8.9", rpm=300)
        assert ban is not None and ban.abuse_type == AbuseType.SCRAPING
    def test_T072_scraping_below_threshold(self, abuse):
        assert abuse.detect_scraping("7.8.9.0", rpm=100) is None
    def test_T073_enumeration_detect(self, abuse):
        ban = abuse.detect_enumeration("8.9.0.1", sequential_count=5)
        assert ban is not None and ban.abuse_type == AbuseType.ENUMERATION
    def test_T074_enumeration_below_threshold(self, abuse):
        assert abuse.detect_enumeration("9.0.1.2", sequential_count=4) is None
    def test_T075_is_banned_after_detect(self, abuse):
        abuse.detect_scraping("10.0.0.1", rpm=300)
        assert abuse.is_banned("10.0.0.1") is not None
    def test_T076_hook_called_on_ban(self, abuse):
        calls = []; abuse.add_hook(lambda ip, ab, ban: calls.append(ab))
        for _ in range(5): abuse.record_auth_fail("11.0.0.1")
        assert AbuseType.CREDENTIAL_STUFFING in calls
    def test_T077_hook_exception_isolated(self, abuse):
        abuse.add_hook(lambda *a: 1/0)
        for _ in range(5): abuse.record_auth_fail("12.0.0.1")
    def test_T078_multiple_hooks(self, abuse):
        calls = []
        abuse.add_hook(lambda ip, ab, ban: calls.append(1))
        abuse.add_hook(lambda ip, ab, ban: calls.append(2))
        for _ in range(5): abuse.record_auth_fail("13.0.0.1")
        assert 1 in calls and 2 in calls
    def test_T079_ban_ttl_positive(self, abuse):
        ban = None
        for _ in range(5): ban = abuse.record_auth_fail("14.0.0.1")
        assert ban.expires_at > ban.banned_at
    def test_T080_different_ips_independent(self, abuse):
        for _ in range(5): abuse.record_auth_fail("15.0.0.1")
        assert abuse.is_banned("15.0.0.2") is None
    def test_T081_ban_has_request_id(self, abuse):
        ban = None
        for _ in range(5): ban = abuse.record_auth_fail("16.0.0.1")
        assert ban.request_id is not None
    def test_T082_error_below_threshold(self, abuse):
        ban = None
        for _ in range(10): ban = abuse.record_error("4.5.6.7")
        assert ban is None


class TestRateLimiter:
    def test_T083_allow_normal_request(self, limiter): assert limiter.check(ip="1.2.3.4").allowed
    def test_T084_whitelist_always_allowed(self, limiter):
        r = limiter.check(ip="1.2.3.4", endpoint="/health")
        assert r.allowed and r.reason == "whitelisted"
    def test_T085_whitelist_metrics(self, limiter):
        assert limiter.check(ip="1.2.3.4", endpoint="/metrics").allowed
    def test_T086_internal_tier_no_limit(self, limiter):
        for _ in range(10000): assert limiter.check(ip="1.2.3.4", tier=RateLimitTier.INTERNAL).allowed
    def test_T087_anonymous_limited(self, limiter):
        denied = any(not limiter.check(ip="2.3.4.5", tier=RateLimitTier.ANONYMOUS).allowed for _ in range(200))
        assert denied
    def test_T088_result_has_request_id(self, limiter): assert limiter.check(ip="3.4.5.6").request_id
    def test_T089_result_has_remaining(self, limiter): assert limiter.check(ip="4.5.6.7").remaining >= 0
    def test_T090_result_has_reset_after(self, limiter): assert limiter.check(ip="5.6.7.8").reset_after >= 0
    def test_T091_banned_ip_denied(self, limiter):
        limiter.ban("6.7.8.9", "test ban")
        r = limiter.check(ip="6.7.8.9")
        assert not r.allowed and r.banned
    def test_T092_unban_allows(self, limiter):
        limiter.ban("7.8.9.0", "t", ttl=3600); limiter.unban("7.8.9.0")
        assert limiter.check(ip="7.8.9.0").allowed
    def test_T093_endpoint_limit_auth(self, limiter):
        denied = any(not limiter.check(ip="8.9.0.1", endpoint="/api/auth/login").allowed for _ in range(20))
        assert denied
    def test_T094_endpoint_prefix_match(self, limiter):
        assert limiter._get_endpoint_limit("/api/admin/users") is not None
    def test_T095_user_based_limit(self, limiter):
        denied = any(not limiter.check(ip="9.0.1.2", user_id="u", tier=RateLimitTier.ANONYMOUS).allowed for _ in range(200))
        assert denied
    def test_T096_tenant_based_limit(self, limiter):
        r = limiter.check(ip="10.0.0.1", tenant_id="t", tier=RateLimitTier.PRO)
        assert isinstance(r, RateLimitResult)
    def test_T097_stats_returns_dict(self, limiter):
        assert "tracked_keys" in limiter.stats()
    def test_T098_reset_clears_key(self, limiter):
        for _ in range(5): limiter.check(ip="11.0.0.1", tier=RateLimitTier.ANONYMOUS, endpoint="/api/auth/login")
        limiter.reset("ep:11.0.0.1:/api/auth/login")
        assert limiter.check(ip="11.0.0.1", endpoint="/api/auth/login").allowed
    def test_T099_reset_all(self, limiter):
        limiter.check(ip="12.0.0.1")
        limiter.reset_all()
        assert limiter.stats()["tracked_keys"] == 0
    def test_T100_record_auth_fail(self, limiter): limiter.record_auth_fail("13.0.0.1")
    def test_T101_record_error(self, limiter): limiter.record_error("14.0.0.1")
    def test_T102_abuse_hook(self, limiter):
        calls = []; limiter.add_abuse_hook(lambda ip, ab, ban: calls.append(ip))
        for _ in range(5): limiter.record_auth_fail("15.0.0.1")
        assert "15.0.0.1" in calls
    def test_T103_result_banned_false_normally(self, limiter): assert not limiter.check(ip="16.0.0.1").banned
    def test_T104_retry_after_zero_when_allowed(self, limiter): assert limiter.check(ip="17.0.0.1").retry_after == 0.0
    def test_T105_retry_after_positive_when_denied(self, limiter):
        for _ in range(30): limiter.check(ip="18.0.0.1", tier=RateLimitTier.ANONYMOUS)
        r = limiter.check(ip="18.0.0.1", tier=RateLimitTier.ANONYMOUS)
        if not r.allowed: assert r.retry_after > 0
    def test_T106_different_ips_independent(self, limiter):
        for _ in range(25): limiter.check(ip="19.0.0.1", tier=RateLimitTier.ANONYMOUS)
        assert limiter.check(ip="19.0.0.2", tier=RateLimitTier.ANONYMOUS).allowed
    def test_T107_pro_tier_higher_limit(self, limiter):
        pro_allowed = sum(1 for _ in range(100) if limiter.check(ip="20.0.0.2", tier=RateLimitTier.PRO).allowed)
        assert pro_allowed > 0
    def test_T108_is_banned_method(self, limiter):
        limiter.ban("21.0.0.1", "test", ttl=3600)
        assert limiter.is_banned("21.0.0.1") is not None
    def test_T109_global_singleton(self): assert get_rate_limiter() is get_rate_limiter()
    def test_T110_reset_global_limiter(self):
        l1 = get_rate_limiter(); reset_global_limiter(); l2 = get_rate_limiter(); assert l1 is not l2
    def test_T111_result_is_dataclass(self, limiter): assert isinstance(limiter.check(ip="22.0.0.1"), RateLimitResult)
    def test_T112_reason_ok_when_allowed(self, limiter): assert limiter.check(ip="23.0.0.1").reason == "ok"


class TestRateLimitHeaders:
    def test_T113_headers_present(self, limiter):
        assert "X-RateLimit-Limit" in make_rate_limit_headers(limiter.check(ip="1.2.3.4"), 100)
    def test_T114_remaining_header(self, limiter):
        assert "X-RateLimit-Remaining" in make_rate_limit_headers(limiter.check(ip="1.2.3.4"), 100)
    def test_T115_reset_header(self, limiter):
        assert "X-RateLimit-Reset" in make_rate_limit_headers(limiter.check(ip="1.2.3.4"), 100)
    def test_T116_retry_after_on_deny(self, limiter):
        for _ in range(30): limiter.check(ip="2.3.4.5", tier=RateLimitTier.ANONYMOUS)
        r = limiter.check(ip="2.3.4.5", tier=RateLimitTier.ANONYMOUS)
        if not r.allowed: assert "Retry-After" in make_rate_limit_headers(r, 20)
    def test_T117_no_retry_after_when_allowed(self, limiter):
        assert "Retry-After" not in make_rate_limit_headers(limiter.check(ip="3.4.5.6"), 100)
    def test_T118_request_id_header(self, limiter):
        assert "X-RateLimit-RequestId" in make_rate_limit_headers(limiter.check(ip="4.5.6.7"), 100)
    def test_T119_limit_matches(self, limiter):
        assert make_rate_limit_headers(limiter.check(ip="5.6.7.8"), 100)["X-RateLimit-Limit"] == "100"
    def test_T120_remaining_string(self, limiter):
        assert isinstance(make_rate_limit_headers(limiter.check(ip="6.7.8.9"), 100)["X-RateLimit-Remaining"], str)


class TestMiddleware:
    def test_T121_extract_ip_from_client(self):
        assert extract_ip({"client": ("1.2.3.4", 1234), "headers": []}) == "1.2.3.4"
    def test_T122_extract_ip_forwarded_for(self):
        assert extract_ip({"client": ("10.0.0.1", 80), "headers": [(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8")]}) == "1.2.3.4"
    def test_T123_extract_ip_real_ip(self):
        assert extract_ip({"client": ("10.0.0.1", 80), "headers": [(b"x-real-ip", b"9.8.7.6")]}) == "9.8.7.6"
    def test_T124_extract_ip_cf_connecting(self):
        assert extract_ip({"client": ("10.0.0.1", 80), "headers": [(b"cf-connecting-ip", b"2.3.4.5")]}) == "2.3.4.5"
    def test_T125_extract_ip_unknown(self):
        assert extract_ip({"headers": []}) == "unknown"
    def test_T126_resolve_tier_anonymous_default(self):
        assert resolve_tier({"state": {}})[0] == RateLimitTier.ANONYMOUS
    def test_T127_resolve_tier_admin(self):
        class S:
            role="admin"; plan=None; user_id="u1"; tenant_id="t1"
        assert resolve_tier({"state": S()})[0] == RateLimitTier.ADMIN
    def test_T128_resolve_tier_vip_plan(self):
        class S:
            role="customer"; plan="vip"; user_id="u2"; tenant_id="t2"
        assert resolve_tier({"state": S()})[0] == RateLimitTier.VIP
    def test_T129_middleware_init(self, limiter):
        mw = RateLimitMiddleware(lambda s,r,send: None, limiter=limiter)
        assert mw._limiter is limiter
    def test_T130_resolve_tier_pro_plan(self):
        class S:
            role="customer"; plan="pro"; user_id="u3"; tenant_id="t3"
        assert resolve_tier({"state": S()})[0] == RateLimitTier.PRO
    def test_T131_resolve_tier_super_admin(self):
        class S:
            role="super_admin"; plan=None; user_id="u4"; tenant_id="t4"
        assert resolve_tier({"state": S()})[0] == RateLimitTier.ADMIN
    def test_T132_resolve_tier_user_id_extracted(self):
        class S:
            role="customer"; plan="basic"; user_id="my-user"; tenant_id="my-tenant"
        tier, uid, tid = resolve_tier({"state": S()})
        assert uid == "my-user" and tid == "my-tenant"


class TestAdminRoutes:
    def test_T133_get_stats(self, router): assert "tracked_keys" in router.get_stats()
    def test_T134_list_bans_empty(self, router): assert isinstance(router.list_bans(), list)
    def test_T135_ban_ip(self, router): assert router.ban_ip("1.2.3.4", "test")["banned"] == "1.2.3.4"
    def test_T136_unban_ip(self, router):
        router.ban_ip("2.3.4.5", "test")
        assert router.unban_ip("2.3.4.5")["was_banned"] is True
    def test_T137_unban_nonexistent(self, router): assert router.unban_ip("9.9.9.9")["was_banned"] is False
    def test_T138_reset_key(self, router): assert "reset" in router.reset_key("ip:1.2.3.4")
    def test_T139_get_tiers(self, router):
        t = router.get_tiers(); assert "anonymous" in t and "admin" in t
    def test_T140_get_endpoints(self, router): assert "/api/auth/login" in router.get_endpoints()
    def test_T141_simulate_check_allowed(self, router): assert router.simulate_check("1.2.3.4", "/", "anonymous")["allowed"]
    def test_T142_simulate_check_health(self, router): assert router.simulate_check("1.2.3.4", "/health", "anonymous")["allowed"]
    def test_T143_list_bans_after_ban(self, router):
        router.ban_ip("3.4.5.6", "abuse", ttl=3600)
        assert "3.4.5.6" in [b["ip"] for b in router.list_bans()]
    def test_T144_tiers_have_rpm(self, router):
        for _, cfg in router.get_tiers().items(): assert "rpm" in cfg
    def test_T145_endpoints_have_window(self, router):
        for _, cfg in router.get_endpoints().items(): assert "window" in cfg
    def test_T146_ban_has_ttl(self, router): assert router.ban_ip("4.5.6.7", "test", ttl=300)["ttl"] == 300
    def test_T147_simulate_banned_ip(self, router):
        router.ban_ip("5.6.7.8", "banned", ttl=3600)
        r = router.simulate_check("5.6.7.8", "/api/signals", "anonymous")
        assert not r["allowed"] and r["banned"]
    def test_T148_simulate_returns_remaining(self, router):
        assert "remaining" in router.simulate_check("6.7.8.9", "/", "anonymous")


class TestSQLMigration:
    SQL = "/home/definable/phase22/supabase/migrations/20260626_030_phase22_rate_limit.sql"
    @pytest.fixture
    def sql(self):
        try: return open(self.SQL).read()
        except FileNotFoundError: pytest.skip("SQL missing")
    def test_T149_sql_has_begin(self, sql): assert "BEGIN" in sql
    def test_T150_sql_has_commit(self, sql): assert "COMMIT" in sql
    def test_T151_bans_table(self, sql): assert "rate_limit_bans" in sql
    def test_T152_violations_table(self, sql): assert "rate_limit_violations" in sql
    def test_T153_abuse_table(self, sql): assert "rate_limit_abuse" in sql
    def test_T154_rls_enabled(self, sql): assert "ENABLE ROW LEVEL SECURITY" in sql
    def test_T155_indexes(self, sql): assert "CREATE INDEX" in sql
    def test_T156_cleanup_function(self, sql): assert "cleanup_expired_bans" in sql
    def test_T157_active_bans_view(self, sql): assert "vw_active_bans" in sql
    def test_T158_if_not_exists(self, sql): assert "IF NOT EXISTS" in sql
    def test_T159_expires_at_column(self, sql): assert "expires_at" in sql
    def test_T160_jsonb_detail(self, sql): assert "JSONB" in sql


class TestIntegrationFlows:
    def test_T161_credential_stuffing_full_flow(self, limiter):
        for _ in range(5): limiter.record_auth_fail("attacker")
        r = limiter.check(ip="attacker", endpoint="/api/auth/login")
        assert not r.allowed and r.banned
    def test_T162_normal_user_not_banned(self, limiter):
        for _ in range(2): limiter.record_auth_fail("normal")
        assert limiter.check(ip="normal").allowed
    def test_T163_auth_endpoint_strict(self, limiter):
        denied = any(not limiter.check(ip="att", endpoint="/api/auth/login", tier=RateLimitTier.ANONYMOUS).allowed for _ in range(15))
        assert denied
    def test_T164_pro_user_higher_limit(self, limiter):
        allowed = sum(1 for _ in range(200) if limiter.check(ip="pro", tier=RateLimitTier.PRO, endpoint="/api/signals").allowed)
        assert allowed > 100
    def test_T165_whitelist_never_blocked(self, limiter):
        for _ in range(10000): assert limiter.check(ip="sc", endpoint="/health").allowed
    def test_T166_ban_unban_cycle(self, limiter):
        limiter.ban("cyc", "test")
        assert not limiter.check(ip="cyc").allowed
        limiter.unban("cyc")
        assert limiter.check(ip="cyc").allowed
    def test_T167_concurrent_different_ips(self, limiter):
        results = {}
        def f(i): results[i] = limiter.check(ip=f"100.0.0.{i}", tier=RateLimitTier.ANONYMOUS).allowed
        ts = [threading.Thread(target=f, args=(i,)) for i in range(20)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert all(results.values())
    def test_T168_abuse_hook_integration(self, limiter):
        ips = []; limiter.add_abuse_hook(lambda ip, ab, ban: ips.append(ip))
        for _ in range(5): limiter.record_auth_fail("hook-ip")
        assert "hook-ip" in ips
    def test_T169_billing_endpoint_limit(self, limiter):
        denied = any(not limiter.check(ip="co", endpoint="/api/billing/checkout").allowed for _ in range(20))
        assert denied
    def test_T170_admin_endpoint_generous(self, limiter):
        allowed = sum(1 for _ in range(50) if limiter.check(ip="adm", endpoint="/api/admin", tier=RateLimitTier.ADMIN).allowed)
        assert allowed >= 50
    def test_T171_result_fields_complete(self, limiter):
        r = limiter.check(ip="1.2.3.4")
        for f in ["allowed","remaining","retry_after","reset_after","reason","banned","request_id","limit"]: assert hasattr(r, f)
    def test_T172_scraping_detection_integration(self, limiter):
        limiter._abuse.detect_scraping("sc", rpm=250)
        assert not limiter.check(ip="sc").allowed
    def test_T173_enumeration_detection_integration(self, limiter):
        limiter._abuse.detect_enumeration("en", sequential_count=6)
        assert not limiter.check(ip="en").allowed
    def test_T174_webhook_endpoint_generous(self, limiter):
        allowed = sum(1 for _ in range(60) if limiter.check(ip="wh", endpoint="/api/billing/webhook", tier=RateLimitTier.PRO).allowed)
        assert allowed >= 50
    def test_T175_risk_halt_strict(self, limiter):
        denied = any(not limiter.check(ip="ri", endpoint="/api/risk/halt").allowed for _ in range(10))
        assert denied
    def test_T176_user_id_tracking(self, limiter):
        denied = any(not limiter.check(ip="1.2.3.4", user_id="u", tier=RateLimitTier.ANONYMOUS).allowed for _ in range(200))
        assert denied
    def test_T177_tenant_id_tracking(self, limiter):
        assert isinstance(limiter.check(ip="1.2.3.4", tenant_id="t", tier=RateLimitTier.PRO), RateLimitResult)
    def test_T178_reset_after_ban(self, limiter):
        limiter.ban("ban-r", "test")
        assert limiter.check(ip="ban-r").reset_after > 0
    def test_T179_rate_limit_result_abuse_types(self, limiter):
        assert isinstance(limiter.check(ip="1.2.3.4").abuse_types, list)
    def test_T180_store_stats_consistent(self, limiter):
        limiter.check(ip="st"); assert limiter.stats()["tracked_keys"] >= 1
    def test_T181_get_endpoint_limit_exact(self, limiter):
        ep = limiter._get_endpoint_limit("/api/auth/login")
        assert ep is not None and ep.requests == 5
    def test_T182_get_endpoint_limit_prefix(self, limiter):
        assert limiter._get_endpoint_limit("/api/admin/users/list") is not None
    def test_T183_get_endpoint_limit_none(self, limiter):
        assert limiter._get_endpoint_limit("/unknown/path") is None
    def test_T184_full_request_lifecycle(self, limiter):
        r = limiter.check(ip="lc", endpoint="/api/signals", user_id="u", tenant_id="t", tier=RateLimitTier.PRO)
        assert r.allowed
        h = make_rate_limit_headers(r, limit=r.limit)
        assert "X-RateLimit-Limit" in h and "X-RateLimit-Remaining" in h
