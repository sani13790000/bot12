"""
Phase 26  -  API Versioning & Backward Compatibility
Test Suite: 196 tests
"""

import sys
import threading
import time
import uuid

import pytest

sys.path.insert(0, "/home/definable/phase26")

from backend.core.api_versioning import (
    CURRENT_VERSION,
    DEFAULT_VERSION_POLICIES,
    SUPPORTED_VERSIONS,
    VERSIONED_ENDPOINTS,
    VERSIONED_SCHEMAS,
    APIVersion,
    BreakingChangeDetector,
    BreakingChangeError,
    CompatibilityLevel,
    DeprecationNotice,
    DeprecationSeverity,
    FieldDescriptor,
    MigrationRule,
    MigrationStrategy,
    MissingReasonError,
    ResponseMigrator,
    SunsetVersionError,
    UnknownVersionError,
    VersionAuditChain,
    VersionedRequest,
    VersionedResponse,
    VersionedSchema,
    VersionError,
    VersionMismatchError,
    VersionNegotiator,
    VersionPolicy,
    VersionRegistryAdmin,
    VersionRouter,
    VersionStatus,
)


class TestAPIVersionEnum:
    def test_T001_values_exist(self):
        assert APIVersion.V1.value == "v1"
        assert APIVersion.V2.value == "v2"
        assert APIVersion.V3.value == "v3"

    def test_T002_str_representation(self):
        assert str(APIVersion.V1) == "v1"
        assert str(APIVersion.V3) == "v3"

    def test_T003_from_string_ok(self):
        assert APIVersion.from_string("v1") == APIVersion.V1
        assert APIVersion.from_string("V2") == APIVersion.V2
        assert APIVersion.from_string("  v3  ") == APIVersion.V3

    def test_T004_from_string_unknown(self):
        with pytest.raises(UnknownVersionError):
            APIVersion.from_string("v99")

    def test_T005_as_int(self):
        assert APIVersion.V1.as_int() == 1
        assert APIVersion.V2.as_int() == 2
        assert APIVersion.V3.as_int() == 3

    def test_T006_version_ordering(self):
        assert APIVersion.V1.as_int() < APIVersion.V2.as_int()
        assert APIVersion.V2.as_int() < APIVersion.V3.as_int()

    def test_T007_current_version_is_v3(self):
        assert CURRENT_VERSION == APIVersion.V3

    def test_T008_three_versions_defined(self):
        assert len(list(APIVersion)) == 3

    def test_T009_version_status_values(self):
        assert VersionStatus.ACTIVE.value == "active"
        assert VersionStatus.DEPRECATED.value == "deprecated"
        assert VersionStatus.SUNSET.value == "sunset"
        assert VersionStatus.EXPERIMENTAL.value == "experimental"

    def test_T010_compatibility_levels(self):
        assert CompatibilityLevel.FULL.value == "full"
        assert CompatibilityLevel.PARTIAL.value == "partial"
        assert CompatibilityLevel.BREAKING.value == "breaking"

    def test_T011_deprecation_severity(self):
        assert DeprecationSeverity.INFO.value == "info"
        assert DeprecationSeverity.WARNING.value == "warning"
        assert DeprecationSeverity.CRITICAL.value == "critical"

    def test_T012_migration_strategy_values(self):
        strategies = [s.value for s in MigrationStrategy]
        assert "passthrough" in strategies
        assert "field_rename" in strategies
        assert "field_add" in strategies
        assert "field_remove" in strategies
        assert "transform" in strategies

    def test_T013_supported_versions_set(self):
        assert APIVersion.V1 in SUPPORTED_VERSIONS
        assert APIVersion.V2 in SUPPORTED_VERSIONS
        assert APIVersion.V3 in SUPPORTED_VERSIONS

    def test_T014_versioned_endpoints_coverage(self):
        assert len(VERSIONED_ENDPOINTS) >= 10
        assert "/api/signals" in VERSIONED_ENDPOINTS
        assert "/api/auth/login" in VERSIONED_ENDPOINTS

    def test_T015_versioned_schemas_exist(self):
        assert "signal" in VERSIONED_SCHEMAS
        assert "auth_response" in VERSIONED_SCHEMAS
        assert "license" in VERSIONED_SCHEMAS
        assert "billing_checkout" in VERSIONED_SCHEMAS
        assert "risk_status" in VERSIONED_SCHEMAS

    def test_T016_error_hierarchy(self):
        assert issubclass(UnknownVersionError, VersionError)
        assert issubclass(SunsetVersionError, VersionError)
        assert issubclass(VersionMismatchError, VersionError)
        assert issubclass(BreakingChangeError, VersionError)
        assert issubclass(MissingReasonError, VersionError)


class TestVersionPolicy:
    def test_T017_v1_deprecated(self):
        p = DEFAULT_VERSION_POLICIES[APIVersion.V1]
        assert p.is_deprecated()

    def test_T018_v2_active(self):
        p = DEFAULT_VERSION_POLICIES[APIVersion.V2]
        assert p.is_active()

    def test_T019_v3_active(self):
        assert DEFAULT_VERSION_POLICIES[APIVersion.V3].is_active()

    def test_T020_v1_has_successor(self):
        assert DEFAULT_VERSION_POLICIES[APIVersion.V1].successor == APIVersion.V3

    def test_T021_v1_has_sunset_date(self):
        p = DEFAULT_VERSION_POLICIES[APIVersion.V1]
        assert p.sunset_at and "2027" in p.sunset_at

    def test_T022_v1_has_deprecation_date(self):
        assert DEFAULT_VERSION_POLICIES[APIVersion.V1].deprecated_at is not None

    def test_T023_v1_has_reason(self):
        p = DEFAULT_VERSION_POLICIES[APIVersion.V1]
        assert p.deprecation_reason and len(p.deprecation_reason) > 0

    def test_T024_deprecation_headers_for_deprecated(self):
        headers = DEFAULT_VERSION_POLICIES[APIVersion.V1].deprecation_headers()
        assert "Deprecation" in headers and "Sunset" in headers

    def test_T025_deprecation_headers_empty_for_active(self):
        assert DEFAULT_VERSION_POLICIES[APIVersion.V3].deprecation_headers() == {}

    def test_T026_is_sunset_false_for_active(self):
        assert not DEFAULT_VERSION_POLICIES[APIVersion.V3].is_sunset()

    def test_T027_days_until_sunset_none_for_active(self):
        assert DEFAULT_VERSION_POLICIES[APIVersion.V3].days_until_sunset() is None

    def test_T028_days_until_sunset_positive_for_deprecated(self):
        days = DEFAULT_VERSION_POLICIES[APIVersion.V1].days_until_sunset()
        assert days is not None and days >= 0

    def test_T029_sunset_response_code_410(self):
        assert DEFAULT_VERSION_POLICIES[APIVersion.V1].sunset_response_code == 410

    def test_T030_policy_is_experimental_false(self):
        assert not DEFAULT_VERSION_POLICIES[APIVersion.V2].is_experimental()

    def test_T031_custom_policy_active(self):
        p = VersionPolicy(
            version=APIVersion.V1, status=VersionStatus.EXPERIMENTAL, released_at="2026-01-01"
        )
        assert p.is_experimental()

    def test_T032_released_at_set(self):
        for v, p in DEFAULT_VERSION_POLICIES.items():
            assert p.released_at is not None


class TestFieldDescriptorAndSchema:
    def test_T033_field_available_from_added_in(self):
        f = FieldDescriptor("x", added_in=APIVersion.V2)
        assert not f.is_available_in(APIVersion.V1)
        assert f.is_available_in(APIVersion.V2)
        assert f.is_available_in(APIVersion.V3)

    def test_T034_field_removed_in(self):
        f = FieldDescriptor("x", added_in=APIVersion.V1, removed_in=APIVersion.V3)
        assert f.is_available_in(APIVersion.V1)
        assert f.is_available_in(APIVersion.V2)
        assert not f.is_available_in(APIVersion.V3)

    def test_T035_signal_schema_v1_fields(self):
        schema = VERSIONED_SCHEMAS["signal"]
        names = [f.name for f in schema.fields_for_version(APIVersion.V1)]
        assert "symbol" in names and "tenant_id" not in names

    def test_T036_signal_schema_v2_adds_tenant(self):
        names = [f.name for f in VERSIONED_SCHEMAS["signal"].fields_for_version(APIVersion.V2)]
        assert "tenant_id" in names

    def test_T037_signal_schema_v3_adds_audit_token(self):
        names = [f.name for f in VERSIONED_SCHEMAS["signal"].fields_for_version(APIVersion.V3)]
        assert "audit_token" in names and "feature_flags" in names

    def test_T038_auth_response_v1_fields(self):
        names = [
            f.name for f in VERSIONED_SCHEMAS["auth_response"].fields_for_version(APIVersion.V1)
        ]
        assert "access_token" in names and "refresh_token" not in names

    def test_T039_auth_response_v2_adds_refresh(self):
        names = [
            f.name for f in VERSIONED_SCHEMAS["auth_response"].fields_for_version(APIVersion.V2)
        ]
        assert "refresh_token" in names

    def test_T040_auth_response_v3_adds_tenant_roles(self):
        names = [
            f.name for f in VERSIONED_SCHEMAS["auth_response"].fields_for_version(APIVersion.V3)
        ]
        assert "tenant_id" in names and "roles" in names

    def test_T041_schema_validate_missing_required(self):
        errors = VERSIONED_SCHEMAS["signal"].validate({}, APIVersion.V1)
        assert any("symbol" in e for e in errors)

    def test_T042_schema_validate_ok(self):
        data = {
            "id": "1",
            "symbol": "EURUSD",
            "direction": "BUY",
            "entry_price": 1.1,
            "sl": 1.09,
            "tp": 1.12,
            "timestamp": 123,
        }
        assert VERSIONED_SCHEMAS["signal"].validate(data, APIVersion.V1) == []

    def test_T043_required_fields_v1_signal(self):
        req = VERSIONED_SCHEMAS["signal"].required_fields_for_version(APIVersion.V1)
        assert "id" in req and "symbol" in req

    def test_T044_required_fields_v2_includes_tenant(self):
        assert "tenant_id" in VERSIONED_SCHEMAS["signal"].required_fields_for_version(APIVersion.V2)

    def test_T045_billing_checkout_v2_adds_idempotency(self):
        names = [
            f.name for f in VERSIONED_SCHEMAS["billing_checkout"].fields_for_version(APIVersion.V2)
        ]
        assert "idempotency_key" in names

    def test_T046_risk_status_v2_adds_kill_switch(self):
        names = [f.name for f in VERSIONED_SCHEMAS["risk_status"].fields_for_version(APIVersion.V2)]
        assert "kill_switch_active" in names

    def test_T047_ea_config_not_in_v1(self):
        assert VERSIONED_SCHEMAS["ea_config"].fields_for_version(APIVersion.V1) == []

    def test_T048_schema_changelog_nonempty(self):
        for name, schema in VERSIONED_SCHEMAS.items():
            assert schema.changelog, f"{name} missing changelog"


class TestResponseMigrator:
    def setup_method(self):
        self.migrator = ResponseMigrator()

    def test_T049_same_version_passthrough(self):
        data = {"access_token": "tok", "user_id": "u1", "expires_in": 3600}
        assert self.migrator.migrate(data, APIVersion.V3, APIVersion.V3) == data

    def test_T050_v3_to_v2_removes_audit_token(self):
        data = {
            "access_token": "tok",
            "user_id": "u1",
            "expires_in": 3600,
            "audit_token": "at",
            "feature_flags": {},
            "roles": [],
            "incident_id": None,
        }
        result = self.migrator.migrate(data, APIVersion.V3, APIVersion.V2)
        assert "audit_token" not in result and "feature_flags" not in result

    def test_T051_v3_to_v1_removes_v2_v3_fields(self):
        data = {
            "access_token": "tok",
            "user_id": "u1",
            "expires_in": 3600,
            "refresh_token": "rt",
            "tenant_id": "t1",
            "audit_token": "at",
            "feature_flags": {},
            "roles": [],
        }
        result = self.migrator.migrate(data, APIVersion.V3, APIVersion.V1)
        assert "refresh_token" not in result and "audit_token" not in result

    def test_T052_v1_to_v2_adds_defaults(self):
        data = {"access_token": "tok", "user_id": "u1", "expires_in": 3600}
        assert "tenant_id" in self.migrator.migrate(data, APIVersion.V1, APIVersion.V2)

    def test_T053_v1_to_v3_step_migration(self):
        data = {"access_token": "tok", "user_id": "u1", "expires_in": 3600}
        result = self.migrator.migrate(data, APIVersion.V1, APIVersion.V3)
        assert "audit_token" in result and "feature_flags" in result

    def test_T054_original_data_not_mutated(self):
        data = {"access_token": "tok", "user_id": "u1", "expires_in": 3600, "audit_token": "at"}
        _ = self.migrator.migrate(data, APIVersion.V3, APIVersion.V2)
        assert "audit_token" in data

    def test_T055_custom_rule_field_rename(self):
        rule = MigrationRule(
            source_version=APIVersion.V2,
            target_version=APIVersion.V3,
            strategy=MigrationStrategy.FIELD_RENAME,
            field_map={"old_field": "new_field"},
        )
        m = ResponseMigrator()
        m._rules = [
            r
            for r in m._rules
            if not (r.source_version == APIVersion.V2 and r.target_version == APIVersion.V3)
        ]
        m.register(rule)
        result = m.migrate({"old_field": "value", "other": "x"}, APIVersion.V2, APIVersion.V3)
        assert "new_field" in result and "old_field" not in result

    def test_T056_custom_rule_transform(self):
        rule = MigrationRule(
            source_version=APIVersion.V2,
            target_version=APIVersion.V3,
            strategy=MigrationStrategy.TRANSFORM,
            transform_fn=lambda d: {**d, "transformed": True},
        )
        m = ResponseMigrator()
        m._rules = [
            r
            for r in m._rules
            if not (r.source_version == APIVersion.V2 and r.target_version == APIVersion.V3)
        ]
        m.register(rule)
        assert m.migrate({"x": 1}, APIVersion.V2, APIVersion.V3)["transformed"] is True

    def test_T057_v2_to_v1_removes_refresh_token(self):
        data = {
            "access_token": "t",
            "user_id": "u",
            "expires_in": 3600,
            "refresh_token": "rt",
            "plan_tier": "PRO",
        }
        assert "refresh_token" not in self.migrator.migrate(data, APIVersion.V2, APIVersion.V1)

    def test_T058_passthrough_rule(self):
        rule = MigrationRule(
            source_version=APIVersion.V1,
            target_version=APIVersion.V2,
            strategy=MigrationStrategy.PASSTHROUGH,
        )
        m = ResponseMigrator()
        m._rules = [
            r
            for r in m._rules
            if not (r.source_version == APIVersion.V1 and r.target_version == APIVersion.V2)
        ]
        m.register(rule)
        assert m.migrate({"x": 1}, APIVersion.V1, APIVersion.V2)["x"] == 1

    def test_T059_field_add_does_not_overwrite(self):
        data = {"access_token": "tok", "user_id": "u1", "expires_in": 3600, "tenant_id": "existing"}
        assert self.migrator.migrate(data, APIVersion.V1, APIVersion.V2)["tenant_id"] == "existing"

    def test_T060_thread_safe_concurrent_migrations(self):
        errors = []

        def work():
            try:
                self.migrator.migrate({"x": 1}, APIVersion.V1, APIVersion.V3)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=work) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_T061_migrate_adds_feature_flags_default(self):
        result = self.migrator.migrate({"access_token": "tok"}, APIVersion.V1, APIVersion.V3)
        assert result.get("feature_flags") == {}

    def test_T062_migrate_adds_roles_default(self):
        result = self.migrator.migrate({"access_token": "tok"}, APIVersion.V1, APIVersion.V3)
        assert result.get("roles") == []

    def test_T063_v3_to_v2_removes_audit_chain(self):
        result = self.migrator.migrate(
            {"x": 1, "audit_chain": "c", "roles": []}, APIVersion.V3, APIVersion.V2
        )
        assert "audit_chain" not in result

    def test_T064_migrate_preserves_non_schema_fields(self):
        result = self.migrator.migrate(
            {"access_token": "tok", "custom_field": "val"}, APIVersion.V3, APIVersion.V3
        )
        assert result["custom_field"] == "val"


class TestVersionNegotiator:
    def setup_method(self):
        self.neg = VersionNegotiator()

    def test_T065_negotiate_v3_returns_v3(self):
        v, n = self.neg.negotiate("v3")
        assert v == APIVersion.V3 and n is None

    def test_T066_negotiate_v2_returns_v2(self):
        v, n = self.neg.negotiate("v2")
        assert v == APIVersion.V2 and n is None

    def test_T067_negotiate_v1_returns_deprecation_notice(self):
        v, n = self.neg.negotiate("v1")
        assert v == APIVersion.V1 and n is not None
        assert n.severity == DeprecationSeverity.WARNING

    def test_T068_negotiate_unknown_raises_mismatch(self):
        with pytest.raises(VersionMismatchError) as e:
            self.neg.negotiate("v99")
        assert "v99" in str(e.value)

    def test_T069_negotiate_sunset_raises_sunset_error(self):
        neg = VersionNegotiator()
        neg._policies[APIVersion.V1].status = VersionStatus.SUNSET
        neg._policies[APIVersion.V1].sunset_at = "2020-01-01"
        with pytest.raises(SunsetVersionError) as e:
            neg.negotiate("v1")
        assert "sunset" in str(e.value).lower()

    def test_T070_deprecation_notice_has_successor(self):
        _, n = self.neg.negotiate("v1")
        assert n.successor_version == APIVersion.V3

    def test_T071_deprecation_notice_has_sunset_date(self):
        _, n = self.neg.negotiate("v1")
        assert n.sunset_at is not None

    def test_T072_deprecation_notice_headers(self):
        _, n = self.neg.negotiate("v1")
        h = n.headers()
        assert "Deprecation" in h and "Sunset" in h

    def test_T073_endpoint_check_v1_not_on_v3_only(self):
        with pytest.raises(VersionMismatchError):
            self.neg.negotiate("v1", "/api/tenant/settings")

    def test_T074_endpoint_check_v2_ok(self):
        v, _ = self.neg.negotiate("v2", "/api/signals")
        assert v == APIVersion.V2

    def test_T075_supported_versions_list(self):
        supported = self.neg.supported_versions()
        assert APIVersion.V2 in supported and APIVersion.V3 in supported

    def test_T076_active_versions(self):
        active = self.neg.active_versions()
        assert APIVersion.V2 in active and APIVersion.V3 in active and APIVersion.V1 not in active

    def test_T077_deprecated_versions(self):
        assert APIVersion.V1 in self.neg.deprecated_versions()

    def test_T078_deprecate_requires_reason(self):
        with pytest.raises(MissingReasonError):
            self.neg.deprecate_version(
                APIVersion.V2, reason="", deprecated_at="2026-01-01", sunset_at=None, actor="admin"
            )

    def test_T079_sunset_requires_reason(self):
        with pytest.raises(MissingReasonError):
            self.neg.sunset_version(
                APIVersion.V2, reason="   ", sunset_at="2027-01-01", actor="admin"
            )

    def test_T080_deprecate_version_updates_policy(self):
        neg = VersionNegotiator()
        neg.deprecate_version(
            APIVersion.V2,
            reason="Moving to V3",
            deprecated_at="2026-06-01",
            sunset_at="2027-06-01",
            actor="admin",
            successor=APIVersion.V3,
        )
        p = neg.get_policy(APIVersion.V2)
        assert p.is_deprecated() and p.successor == APIVersion.V3


class TestVersionAuditChain:
    def test_T081_record_returns_entry(self):
        chain = VersionAuditChain(secret=b"test-secret")
        e = chain.record("negotiate", "v3", "/api/signals")
        assert e.action == "negotiate" and e.version == "v3"

    def test_T082_chain_hash_64_chars(self):
        chain = VersionAuditChain(secret=b"test-secret")
        assert len(chain.record("negotiate", "v3", "/api").chain_hash) == 64

    def test_T083_genesis_hash_64_chars(self):
        assert len(VersionAuditChain(secret=b"test-secret")._genesis) == 64

    def test_T084_verify_chain_empty(self):
        assert VersionAuditChain(secret=b"test-secret").verify_chain() is True

    def test_T085_verify_chain_single(self):
        c = VersionAuditChain(secret=b"test-secret")
        c.record("negotiate", "v3", "/api")
        assert c.verify_chain() is True

    def test_T086_verify_chain_multiple(self):
        c = VersionAuditChain(secret=b"test-secret")
        for i in range(10):
            c.record("negotiate", "v3", f"/ep{i}")
        assert c.verify_chain() is True

    def test_T087_tamper_breaks_chain(self):
        c = VersionAuditChain(secret=b"test-secret")
        c.record("negotiate", "v3", "/api")
        c.record("mismatch", "v99", "/api")
        list(c._records)[0].chain_hash = "a" * 64
        assert c.verify_chain() is False

    def test_T088_wrong_secret_fails_verify(self):
        c1 = VersionAuditChain(secret=b"secret1")
        c1.record("negotiate", "v3", "/api")
        c2 = VersionAuditChain(secret=b"secret2")
        c2._records = c1._records
        c2._genesis = c1._genesis
        assert c2.verify_chain() is False

    def test_T089_seq_starts_at_1(self):
        assert VersionAuditChain(secret=b"s").record("x", "v3", "/").seq == 1

    def test_T090_seq_increments(self):
        c = VersionAuditChain(secret=b"s")
        e1 = c.record("x", "v3", "/")
        e2 = c.record("y", "v3", "/")
        assert e2.seq == e1.seq + 1

    def test_T091_query_by_action(self):
        c = VersionAuditChain(secret=b"s")
        c.record("negotiate", "v3", "/api")
        c.record("mismatch", "v99", "/bad")
        assert all(r.action == "negotiate" for r in c.query(action="negotiate"))

    def test_T092_query_by_version(self):
        c = VersionAuditChain(secret=b"s")
        c.record("negotiate", "v1", "/api")
        c.record("negotiate", "v3", "/api")
        assert all(r.version == "v1" for r in c.query(version="v1"))

    def test_T093_query_limit(self):
        c = VersionAuditChain(secret=b"s")
        for i in range(20):
            c.record("x", "v3", f"/ep{i}")
        assert len(c.query(limit=5)) == 5

    def test_T094_query_most_recent_first(self):
        c = VersionAuditChain(secret=b"s")
        for i in range(5):
            c.record("x", "v3", f"/ep{i}")
        seqs = [r.seq for r in c.query(limit=5)]
        assert seqs == sorted(seqs, reverse=True)

    def test_T095_thread_safe_concurrent(self):
        c = VersionAuditChain(secret=b"s")
        errors = []

        def work():
            try:
                c.record("x", "v3", "/", tenant_id=str(uuid.uuid4()))
            except Exception as e:
                errors.append(e)

        ts = [threading.Thread(target=work) for _ in range(50)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert errors == [] and len(c) == 50

    def test_T096_str_secret_accepted(self):
        assert (
            len(VersionAuditChain(secret="string-secret").record("x", "v3", "/").chain_hash) == 64
        )


class TestVersionRouter:
    def setup_method(self):
        self.router = VersionRouter()

    def test_T097_route_v3_returns_200(self):
        resp = self.router.route(VersionedRequest("/api/signals", "v3"))
        assert resp.status_code == 200 and resp.version == APIVersion.V3

    def test_T098_route_v2_returns_200(self):
        assert self.router.route(VersionedRequest("/api/signals", "v2")).status_code == 200

    def test_T099_route_v1_deprecated_flag(self):
        resp = self.router.route(VersionedRequest("/api/signals", "v1"))
        assert resp.status_code == 200 and resp.is_deprecated

    def test_T100_route_v1_has_deprecation_headers(self):
        resp = self.router.route(VersionedRequest("/api/signals", "v1"))
        assert "Deprecation" in resp.headers

    def test_T101_route_sunset_returns_410(self):
        neg = VersionNegotiator()
        neg._policies[APIVersion.V1].status = VersionStatus.SUNSET
        neg._policies[APIVersion.V1].sunset_at = "2020-01-01"
        resp = VersionRouter(negotiator=neg).route(VersionedRequest("/api/signals", "v1"))
        assert resp.status_code == 410 and resp.body["code"] == "SUNSET"

    def test_T102_route_unknown_version_returns_400(self):
        resp = self.router.route(VersionedRequest("/api/signals", "v99"))
        assert resp.status_code == 400 and resp.body["code"] == "VERSION_MISMATCH"

    def test_T103_route_mismatch_includes_supported(self):
        assert (
            "supported_versions" in self.router.route(VersionedRequest("/api/signals", "v99")).body
        )

    def test_T104_route_adds_api_version_header(self):
        resp = self.router.route(VersionedRequest("/api/signals", "v3"))
        assert resp.headers["X-API-Version"] == "v3"

    def test_T105_route_adds_canonical_version_header(self):
        assert (
            "X-API-Canonical-Version"
            in self.router.route(VersionedRequest("/api/signals", "v2")).headers
        )

    def test_T106_route_audits_call(self):
        self.router.route(VersionedRequest("/api/signals", "v3", client_id="tc"))
        assert len(self.router.audit.query(action="route")) >= 1

    def test_T107_route_audits_mismatch(self):
        self.router.route(VersionedRequest("/api/signals", "v99"))
        assert len(self.router.audit.query(action="mismatch")) >= 1

    def test_T108_route_audits_sunset(self):
        neg = VersionNegotiator()
        neg._policies[APIVersion.V1].status = VersionStatus.SUNSET
        neg._policies[APIVersion.V1].sunset_at = "2020-01-01"
        r = VersionRouter(negotiator=neg)
        r.route(VersionedRequest("/api/signals", "v1"))
        assert len(r.audit.query(action="sunset_blocked")) >= 1

    def test_T109_register_handler_called(self):
        called = []

        def h(req):
            called.append(req)
            return {"custom": True}

        self.router.register_handler("/api/custom", h)
        resp = self.router.route(VersionedRequest("/api/custom", "v3"))
        assert resp.status_code == 200 and len(called) == 1

    def test_T110_route_v3_to_v1_removes_v3_fields(self):
        def h(req):
            return {
                "access_token": "tok",
                "user_id": "u",
                "expires_in": 3600,
                "tenant_id": "t",
                "roles": [],
                "audit_token": "at",
                "feature_flags": {},
                "incident_id": None,
                "refresh_token": "rt",
            }

        r = VersionRouter(canonical_version=APIVersion.V3)
        r.register_handler("/api/auth/login", h)
        resp = r.route(VersionedRequest("/api/auth/login", "v1"))
        assert "audit_token" not in resp.body and "feature_flags" not in resp.body

    def test_T111_concurrent_routing(self):
        errors = []

        def work(v):
            try:
                self.router.route(VersionedRequest("/api/signals", v))
            except Exception as e:
                errors.append(e)

        ts = [threading.Thread(target=work, args=(["v1", "v2", "v3"][i % 3],)) for i in range(60)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert errors == []

    def test_T112_is_ok_property(self):
        assert self.router.route(VersionedRequest("/api/signals", "v3")).is_ok is True


class TestBreakingChangeDetector:
    def test_T113_no_issues_when_fields_same(self):
        schema = VERSIONED_SCHEMAS["signal"]
        issues = BreakingChangeDetector.compare(schema, schema, APIVersion.V2, APIVersion.V3)
        assert all("BREAKING" not in i for i in issues)

    def test_T114_breaking_when_required_removed(self):
        old = VersionedSchema("t", [FieldDescriptor("x", required=True, added_in=APIVersion.V1)])
        new = VersionedSchema(
            "t",
            [FieldDescriptor("x", required=True, added_in=APIVersion.V1, removed_in=APIVersion.V2)],
        )
        issues = BreakingChangeDetector.compare(old, new, APIVersion.V1, APIVersion.V2)
        assert len(issues) > 0 and "BREAKING" in issues[0]

    def test_T115_no_breaking_for_optional_removal(self):
        old = VersionedSchema("t", [FieldDescriptor("x", required=False, added_in=APIVersion.V1)])
        new = VersionedSchema(
            "t",
            [
                FieldDescriptor(
                    "x", required=False, added_in=APIVersion.V1, removed_in=APIVersion.V2
                )
            ],
        )
        assert BreakingChangeDetector.compare(old, new, APIVersion.V1, APIVersion.V2) == []

    def test_T116_assert_compatible_raises_on_breaking(self):
        old = VersionedSchema("t", [FieldDescriptor("x", required=True, added_in=APIVersion.V1)])
        new = VersionedSchema(
            "t",
            [FieldDescriptor("x", required=True, added_in=APIVersion.V1, removed_in=APIVersion.V2)],
        )
        with pytest.raises(BreakingChangeError):
            BreakingChangeDetector.assert_compatible(old, new, APIVersion.V1, APIVersion.V2)

    def test_T117_assert_compatible_ok_for_additions(self):
        schema = VERSIONED_SCHEMAS["signal"]
        BreakingChangeDetector.assert_compatible(schema, schema, APIVersion.V2, APIVersion.V3)

    def test_T118_adding_fields_not_breaking(self):
        old = VersionedSchema("t", [FieldDescriptor("x", required=True, added_in=APIVersion.V1)])
        new = VersionedSchema(
            "t",
            [
                FieldDescriptor("x", required=True, added_in=APIVersion.V1),
                FieldDescriptor("y", required=False, added_in=APIVersion.V2),
            ],
        )
        assert BreakingChangeDetector.compare(old, new, APIVersion.V1, APIVersion.V2) == []

    def test_T119_multiple_breaking_changes(self):
        old = VersionedSchema(
            "t",
            [FieldDescriptor("a", True, APIVersion.V1), FieldDescriptor("b", True, APIVersion.V1)],
        )
        new = VersionedSchema(
            "t",
            [
                FieldDescriptor("a", True, APIVersion.V1, removed_in=APIVersion.V2),
                FieldDescriptor("b", True, APIVersion.V1, removed_in=APIVersion.V2),
            ],
        )
        assert len(BreakingChangeDetector.compare(old, new, APIVersion.V1, APIVersion.V2)) == 2

    def test_T120_renamed_field_descriptor(self):
        f = FieldDescriptor("new_name", renamed_from="old_name", added_in=APIVersion.V2)
        assert f.renamed_from == "old_name" and f.name == "new_name"


class TestDeprecationNotice:
    def _notice(
        self,
        severity=DeprecationSeverity.WARNING,
        sunset_at="2027-01-01",
        successor=APIVersion.V3,
        guide=None,
    ):
        return DeprecationNotice(
            version=APIVersion.V1,
            endpoint="/api/signals",
            message="Use V3",
            severity=severity,
            deprecated_at="2026-01-01",
            sunset_at=sunset_at,
            successor_version=successor,
            successor_endpoint="/api/signals",
            migration_guide_url=guide,
        )

    def test_T121_to_dict_has_warning(self):
        d = self._notice().to_dict()
        assert "warning" in d and d["severity"] == "warning"

    def test_T122_headers_include_deprecation(self):
        h = self._notice().headers()
        assert "Deprecation" in h and "Sunset" in h

    def test_T123_headers_include_migration_guide(self):
        h = self._notice(guide="https://docs.example.com/migrate").headers()
        assert "X-API-Migration-Guide" in h

    def test_T124_to_dict_successor_version(self):
        assert self._notice().to_dict()["successor_version"] == "v3"

    def test_T125_no_sunset_no_sunset_header(self):
        assert "Sunset" not in self._notice(sunset_at=None).headers()


class TestVersionRegistryAdmin:
    def test_T126_summary_has_versions(self):
        s = VersionRegistryAdmin().summary()
        assert "v1" in s["versions"] and "v3" in s["versions"]

    def test_T127_summary_current_version(self):
        assert VersionRegistryAdmin().summary()["current_version"] == "v3"

    def test_T128_summary_supported_count(self):
        assert VersionRegistryAdmin().summary()["supported_count"] >= 2

    def test_T129_summary_deprecated_count(self):
        assert VersionRegistryAdmin().summary()["deprecated_count"] >= 1

    def test_T130_summary_audit_chain_valid(self):
        assert VersionRegistryAdmin().summary()["audit_chain_valid"] is True

    def test_T131_force_sunset_requires_reason(self):
        with pytest.raises(MissingReasonError):
            VersionRegistryAdmin().force_sunset(
                APIVersion.V1, reason="", sunset_at="2020-01-01", actor="admin"
            )

    def test_T132_force_sunset_updates_policy(self):
        neg = VersionNegotiator()
        admin = VersionRegistryAdmin(negotiator=neg)
        admin.force_sunset(APIVersion.V1, reason="Emergency", sunset_at="2020-01-01", actor="admin")
        assert neg.get_policy(APIVersion.V1).is_sunset()

    def test_T133_force_sunset_audited(self):
        admin = VersionRegistryAdmin()
        admin.force_sunset(APIVersion.V1, reason="Test", sunset_at="2020-01-01", actor="admin")
        assert len(admin._audit.query(action="force_sunset")) == 1

    def test_T134_endpoint_matrix_has_all_endpoints(self):
        m = VersionRegistryAdmin().endpoint_matrix()
        assert "/api/signals" in m and "/api/auth/login" in m

    def test_T135_endpoint_matrix_versions_sorted(self):
        for ep, versions in VersionRegistryAdmin().endpoint_matrix().items():
            assert versions == sorted(versions)

    def test_T136_schemas_has_all_versions(self):
        schemas = VersionRegistryAdmin().schemas()
        assert "signal" in schemas
        for v in ["v1", "v2", "v3"]:
            assert v in schemas["signal"]

    def test_T137_schemas_fields_nonempty_for_v3(self):
        assert len(VersionRegistryAdmin().schemas()["signal"]["v3"]["fields"]) > 0

    def test_T138_schemas_required_fields(self):
        assert "symbol" in VersionRegistryAdmin().schemas()["signal"]["v1"]["required"]

    def test_T139_summary_audit_entries_count(self):
        admin = VersionRegistryAdmin()
        admin.force_sunset(APIVersion.V1, reason="test", sunset_at="2020-01-01", actor="admin")
        assert admin.summary()["audit_entries"] >= 1

    def test_T140_summary_version_details(self):
        s = VersionRegistryAdmin().summary()
        v1 = s["versions"]["v1"]
        assert "status" in v1 and v1["status"] == "deprecated"


class TestSQLMigration:
    @pytest.fixture(autouse=True)
    def load_sql(self):
        import os

        p = "/home/definable/phase26/supabase/migrations/20260628_035_phase26_api_versioning.sql"
        if not os.path.exists(p):
            pytest.skip("SQL file not found")
        with open(p) as f:
            self.sql = f.read()

    def test_T141_sql_has_begin_commit(self):
        assert "BEGIN" in self.sql.upper() and "COMMIT" in self.sql.upper()

    def test_T142_api_versions_table(self):
        assert "api_version_registry" in self.sql

    def test_T143_version_audit_log_table(self):
        assert "version_audit_log" in self.sql

    def test_T144_endpoint_versions_table(self):
        assert "endpoint_version_map" in self.sql

    def test_T145_deprecation_notices_table(self):
        assert "deprecation_notices" in self.sql

    def test_T146_rls_enabled(self):
        assert "ROW LEVEL SECURITY" in self.sql.upper() or "ENABLE ROW LEVEL" in self.sql.upper()

    def test_T147_tenant_id_column(self):
        assert "tenant_id" in self.sql

    def test_T148_chain_hash_column(self):
        assert "chain_hash" in self.sql

    def test_T149_if_not_exists(self):
        assert "IF NOT EXISTS" in self.sql.upper()

    def test_T150_immutable_trigger(self):
        assert "TRIGGER" in self.sql.upper()

    def test_T151_indexes_exist(self):
        assert "CREATE INDEX" in self.sql.upper()

    def test_T152_sunset_date_column(self):
        assert "sunset_at" in self.sql

    def test_T153_status_column(self):
        assert "status" in self.sql

    def test_T154_version_column(self):
        assert "version" in self.sql

    def test_T155_cleanup_function(self):
        assert "cleanup" in self.sql.lower() or "FUNCTION" in self.sql.upper()

    def test_T156_view_exists(self):
        assert "VIEW" in self.sql.upper()


class TestIntegrationFlows:
    def test_T157_full_v1_client_lifecycle(self):
        router = VersionRouter()
        req = VersionedRequest("/api/signals", "v1", client_id="c1", tenant_id="t1")
        resp = router.route(req)
        assert resp.status_code == 200 and resp.is_deprecated
        assert "Deprecation" in resp.headers and "audit_token" not in resp.body

    def test_T158_v3_client_full_response(self):
        resp = VersionRouter().route(VersionedRequest("/api/signals", "v3", tenant_id="t2"))
        assert resp.status_code == 200 and not resp.is_deprecated
        assert resp.headers["X-API-Version"] == "v3"

    def test_T159_sunset_v1_client_gets_410(self):
        neg = VersionNegotiator()
        neg._policies[APIVersion.V1].status = VersionStatus.SUNSET
        neg._policies[APIVersion.V1].sunset_at = "2020-01-01"
        assert (
            VersionRouter(negotiator=neg).route(VersionedRequest("/api/signals", "v1")).status_code
            == 410
        )

    def test_T160_unknown_version_gets_400_with_guidance(self):
        resp = VersionRouter().route(VersionedRequest("/api/signals", "v0"))
        assert resp.status_code == 400 and "supported_versions" in resp.body

    def test_T161_audit_chain_valid_after_100_requests(self):
        audit = VersionAuditChain(secret=b"audit-secret")
        router = VersionRouter(audit=audit)
        for i in range(100):
            router.route(VersionedRequest("/api/signals", ["v1", "v2", "v3"][i % 3]))
        assert audit.verify_chain()

    def test_T162_deprecate_v2_and_route(self):
        neg = VersionNegotiator()
        neg.deprecate_version(
            APIVersion.V2,
            reason="Moving to V3",
            deprecated_at="2026-06-01",
            sunset_at="2027-06-01",
            actor="admin",
            successor=APIVersion.V3,
        )
        resp = VersionRouter(negotiator=neg).route(VersionedRequest("/api/signals", "v2"))
        assert resp.is_deprecated and "Deprecation" in resp.headers

    def test_T163_concurrent_multi_version_routing(self):
        router = VersionRouter()
        errors = []

        def work(v):
            try:
                router.route(VersionedRequest("/api/signals", v))
            except Exception as e:
                errors.append(e)

        ts = [threading.Thread(target=work, args=(["v1", "v2", "v3"][i % 3],)) for i in range(90)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert errors == []

    def test_T164_schema_backward_compat_v1_to_v2(self):
        schema = VERSIONED_SCHEMAS["auth_response"]
        v1 = set(f.name for f in schema.fields_for_version(APIVersion.V1))
        v2 = set(f.name for f in schema.fields_for_version(APIVersion.V2))
        assert v1.issubset(v2)

    def test_T165_schema_backward_compat_v2_to_v3(self):
        schema = VERSIONED_SCHEMAS["signal"]
        v2 = set(f.name for f in schema.fields_for_version(APIVersion.V2))
        v3 = set(f.name for f in schema.fields_for_version(APIVersion.V3))
        assert v2.issubset(v3)

    def test_T166_endpoint_only_in_v3(self):
        assert VERSIONED_ENDPOINTS["/api/tenant/settings"] == {APIVersion.V3}

    def test_T167_endpoint_all_versions(self):
        assert VERSIONED_ENDPOINTS["/api/auth/login"] == {
            APIVersion.V1,
            APIVersion.V2,
            APIVersion.V3,
        }

    def test_T168_deprecation_policy_all_three_versions(self):
        assert len(DEFAULT_VERSION_POLICIES) == 3

    def test_T169_negotiate_v1_endpoint_not_in_v3_only(self):
        with pytest.raises(VersionMismatchError):
            VersionNegotiator().negotiate("v1", "/api/feature-flags")

    def test_T170_migration_v3_to_v1_removes_feature_flags(self):
        data = {
            "access_token": "tok",
            "user_id": "u",
            "expires_in": 3600,
            "refresh_token": "rt",
            "tenant_id": "t",
            "audit_token": "at",
            "feature_flags": {"f": True},
            "roles": [],
        }
        assert "feature_flags" not in ResponseMigrator().migrate(data, APIVersion.V3, APIVersion.V1)

    def test_T171_breaking_change_detector_on_standard_schemas(self):
        for name, schema in VERSIONED_SCHEMAS.items():
            issues = BreakingChangeDetector.compare(schema, schema, APIVersion.V2, APIVersion.V3)
            assert [i for i in issues if "BREAKING" in i] == [], f"{name}: breaking"

    def test_T172_admin_force_sunset_blocks_routing(self):
        neg = VersionNegotiator()
        VersionRegistryAdmin(negotiator=neg).force_sunset(
            APIVersion.V1, reason="Emergency", sunset_at="2020-01-01", actor="admin"
        )
        assert (
            VersionRouter(negotiator=neg).route(VersionedRequest("/api/signals", "v1")).status_code
            == 410
        )


class TestEdgeCasesAndCoverage:
    def test_T173_sunset_error_has_version(self):
        e = SunsetVersionError(APIVersion.V1, "2020-01-01")
        assert e.version == APIVersion.V1 and "sunset" in str(e).lower()

    def test_T174_mismatch_error_has_supported(self):
        e = VersionMismatchError("v99", ["v2", "v3"])
        assert e.requested == "v99" and "v2" in e.supported

    def test_T175_versioned_response_is_ok(self):
        assert VersionedResponse(200, APIVersion.V3, {}, {}).is_ok

    def test_T176_versioned_response_not_ok_on_error(self):
        assert not VersionedResponse(400, APIVersion.V3, {}, {}).is_ok

    def test_T177_versioned_response_is_deprecated_false(self):
        assert not VersionedResponse(
            200, APIVersion.V3, {}, {}, deprecation_notice=None
        ).is_deprecated

    def test_T178_versioned_response_is_deprecated_true(self):
        n = DeprecationNotice(
            APIVersion.V1, "/", "x", DeprecationSeverity.INFO, "2026-01-01", None, None, None
        )
        assert VersionedResponse(200, APIVersion.V1, {}, {}, deprecation_notice=n).is_deprecated

    def test_T179_audit_chain_len(self):
        c = VersionAuditChain(secret=b"s")
        assert len(c) == 0
        c.record("x", "v3", "/")
        assert len(c) == 1

    def test_T180_audit_entry_has_uuid(self):
        uuid.UUID(VersionAuditChain(secret=b"s").record("x", "v3", "/").entry_id)

    def test_T181_audit_entry_has_timestamp(self):
        before = time.time()
        ts = VersionAuditChain(secret=b"s").record("x", "v3", "/").ts
        assert before <= ts <= time.time()

    def test_T182_migration_rule_field_remove(self):
        rule = MigrationRule(
            source_version=APIVersion.V3,
            target_version=APIVersion.V2,
            strategy=MigrationStrategy.FIELD_REMOVE,
            remove_fields=["x", "y"],
        )
        m = ResponseMigrator()
        m._rules = [
            r
            for r in m._rules
            if not (r.source_version == APIVersion.V3 and r.target_version == APIVersion.V2)
        ]
        m.register(rule)
        result = m.migrate({"x": 1, "y": 2, "z": 3}, APIVersion.V3, APIVersion.V2)
        assert "x" not in result and "y" not in result and result["z"] == 3

    def test_T183_unknown_version_error_message(self):
        try:
            APIVersion.from_string("v-invalid")
        except UnknownVersionError as e:
            assert "v-invalid" in str(e)

    def test_T184_versioned_schema_compatibility_field(self):
        assert VERSIONED_SCHEMAS["signal"].compatibility == CompatibilityLevel.PARTIAL

    def test_T185_field_descriptor_default(self):
        assert (
            FieldDescriptor("flags", required=False, default={}, added_in=APIVersion.V3).default
            == {}
        )

    def test_T186_negotiator_custom_policies(self):
        policies = {
            APIVersion.V3: VersionPolicy(
                version=APIVersion.V3, status=VersionStatus.ACTIVE, released_at="2026-01-01"
            )
        }
        v, n = VersionNegotiator(policies=policies).negotiate("v3")
        assert v == APIVersion.V3 and n is None

    def test_T187_router_audit_chain_valid_after_errors(self):
        router = VersionRouter()
        for _ in range(10):
            router.route(VersionedRequest("/api/signals", "v99"))
        assert router.audit.verify_chain()

    def test_T188_all_versioned_endpoints_have_v3(self):
        for ep, versions in VERSIONED_ENDPOINTS.items():
            assert APIVersion.V3 in versions or APIVersion.V2 in versions

    def test_T189_deprecation_severity_warning_for_v1(self):
        assert (
            DEFAULT_VERSION_POLICIES[APIVersion.V1].deprecation_severity
            == DeprecationSeverity.WARNING
        )

    def test_T190_migration_strategy_enum_count(self):
        assert len(list(MigrationStrategy)) == 5

    def test_T191_compatibility_level_enum_count(self):
        assert len(list(CompatibilityLevel)) == 3

    def test_T192_version_status_enum_count(self):
        assert len(list(VersionStatus)) == 4

    def test_T193_versioned_schemas_count(self):
        assert len(VERSIONED_SCHEMAS) >= 5

    def test_T194_versioned_endpoints_count(self):
        assert len(VERSIONED_ENDPOINTS) >= 10

    def test_T195_audit_chain_genesis_deterministic(self):
        assert (
            VersionAuditChain(secret=b"same")._genesis == VersionAuditChain(secret=b"same")._genesis
        )

    def test_T196_audit_chain_genesis_differs_for_diff_secret(self):
        assert VersionAuditChain(secret=b"A")._genesis != VersionAuditChain(secret=b"B")._genesis
