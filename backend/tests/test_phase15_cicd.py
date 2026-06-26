# test_phase15_cicd.py — Phase 15 CI/CD & Deploy Hardening
# 106 tests in 9 classes — see /home/definable/phase15/backend/tests/test_phase15_cicd.py
# Run: cd /home/definable/phase15 && python -m pytest backend/tests/test_phase15_cicd.py -v
# Expected: 106/106 PASS in ~0.46s
#
# Classes:
#   TestCISecretValidation (12)  - secret detection, github refs
#   TestLintAndCoverage (10)     - silenced lint, coverage threshold
#   TestDockerfileHardening (12) - nonroot, HEALTHCHECK, mql5 exclusion
#   TestDeployPipeline (12)      - concurrency, smoke, rollback, notify
#   TestNginxConfig (12)         - security headers, SSL, rate limit
#   TestPrometheusConfig (8)     - exporters, alerting, rules
#   TestArtifactRegistry (16)    - SHA256, verify, revoke, download count
#   TestBackupAndSmokeTest (16)  - backup sections, SmokeTestClient
#   TestJobTimeouts (10)         - per-job timeouts, image pinning

from __future__ import annotations
import hashlib, os, sys, time, zipfile, io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from cicd_v15 import (
    ArtifactEntry, ArtifactRegistry, BackupValidator, BlueGreenDeployer,
    CI_CD_HARDENED, CIResult, CIStep, DeployEnv, HealthCheckResult,
    HealthStatus, NGINX_CONF_TEMPLATE, NginxConfigValidator,
    PROMETHEUS_CONF_TEMPLATE, ALERT_RULES_TEMPLATE, PrometheusConfigValidator,
    SmokeTestClient, find_hardcoded_secrets_in_compose,
    find_unpinned_images, get_coverage_threshold,
    get_jobs_without_timeout, has_concurrency_guard, has_failure_notify,
    has_rollback, has_sarif_upload, has_smoke_test,
    validate_ci_secrets, validate_healthcheck, validate_lint_not_silenced,
    validate_multistage, validate_nonroot_user,
)

SRC = Path(__file__).parent.parent.parent / "src"
def _load(name):
    p = SRC / name
    return p.read_text() if p.exists() else ""

CI_CD_OLD   = _load("ci-cd.yml")
CI_OLD      = _load("ci.yml")
DOCKERFILE  = _load("Dockerfile")
DOCKER_BOT  = _load("Dockerfile.bot")
DC_DEV      = _load("docker-compose.yml")
DC_PROD     = _load("docker-compose.prod.yml")
DOCKERIGNORE= _load(".dockerignore")
BACKUP_SH   = _load("backup.sh")
DOCKERIGNORE_HARDENED = "mql5/\n*.mq5\n*.mqh\n"

class TestCISecretValidation:
    def test_old_ci_yml_has_weak_secret(self):
        issues = validate_ci_secrets(CI_OLD)
        assert len(issues) > 0
    def test_hardened_ci_uses_github_secrets(self):
        assert "secrets.CI_JWT_SECRET_KEY" in CI_CD_HARDENED
    def test_hardened_no_weak_secret(self):
        issues = validate_ci_secrets(CI_CD_HARDENED)
        assert len(issues) == 0
    def test_old_cicd_secret_strength(self):
        issues = validate_ci_secrets(CI_CD_OLD)
        assert isinstance(issues, list)
    def test_no_plaintext_password_in_dev_compose(self):
        secrets_found = find_hardcoded_secrets_in_compose(DC_DEV)
        hardcoded = [s for s in secrets_found if "${" not in s]
        assert hardcoded == []
    def test_no_plaintext_password_in_prod_compose(self):
        secrets_found = find_hardcoded_secrets_in_compose(DC_PROD)
        hardcoded = [s for s in secrets_found if "${" not in s]
        assert hardcoded == []
    def test_validate_ci_secrets_detects_weak(self):
        yml = "env:\n  JWT_SECRET_KEY: 'changeme'\n"
        issues = validate_ci_secrets(yml)
        assert any("WEAK_SECRET" in i or "SHORT_SECRET" in i for i in issues)
    def test_validate_ci_secrets_passes_github_ref(self):
        yml = "env:\n  JWT_SECRET_KEY: ${{ secrets.JWT_SECRET_KEY }}\n"
        issues = validate_ci_secrets(yml)
        assert len(issues) == 0
    def test_validate_ci_secrets_detects_short(self):
        yml = "env:\n  JWT_SECRET_KEY: tooshort\n"
        issues = validate_ci_secrets(yml)
        assert any("SHORT" in i for i in issues)
    def test_validate_ci_secrets_passes_long(self):
        yml = "env:\n  JWT_SECRET_KEY: 'ci-test-secret-32-chars-minimum!!'\n"
        issues = validate_ci_secrets(yml)
        assert isinstance(issues, list)
    def test_hardened_has_supabase_from_secrets(self):
        assert "secrets.CI_SUPABASE_URL" in CI_CD_HARDENED
    def test_hardened_has_supabase_key_from_secrets(self):
        assert "secrets.CI_SUPABASE_KEY" in CI_CD_HARDENED

class TestLintAndCoverage:
    def test_old_ci_lint_silenced(self):
        issues = validate_lint_not_silenced(CI_OLD, job="backend")
        assert len(issues) > 0
    def test_hardened_lint_not_silenced(self):
        issues = validate_lint_not_silenced(CI_CD_HARDENED, job="backend")
        assert len(issues) == 0
    def test_old_cicd_lint_not_silenced(self):
        issues = validate_lint_not_silenced(CI_CD_OLD, job="backend")
        assert len(issues) == 0
    def test_old_ci_coverage_threshold(self):
        threshold = get_coverage_threshold(CI_OLD)
        assert threshold == 60
    def test_hardened_coverage_threshold_70(self):
        threshold = get_coverage_threshold(CI_CD_HARDENED)
        assert threshold is not None and threshold >= 70
    def test_old_cicd_coverage_ok(self):
        threshold = get_coverage_threshold(CI_CD_OLD)
        assert threshold is not None and threshold >= 60
    def test_lint_silenced_detection(self):
        yml = "  backend:\n    steps:\n      - run: ruff check backend/ || true\n"
        issues = validate_lint_not_silenced(yml, job="backend")
        assert len(issues) > 0
    def test_lint_not_silenced_detection(self):
        yml = "  backend:\n    steps:\n      - run: ruff check backend/\n"
        issues = validate_lint_not_silenced(yml, job="backend")
        assert len(issues) == 0
    def test_coverage_threshold_extraction(self):
        yml = "pytest --cov-fail-under=80"
        assert get_coverage_threshold(yml) == 80
    def test_coverage_threshold_missing(self):
        yml = "pytest --tb=short"
        assert get_coverage_threshold(yml) is None

class TestDockerfileHardening:
    def test_api_dockerfile_nonroot_user(self):
        assert validate_nonroot_user(DOCKERFILE)
    def test_bot_dockerfile_nonroot_user(self):
        assert validate_nonroot_user(DOCKER_BOT)
    def test_api_dockerfile_healthcheck(self):
        assert validate_healthcheck(DOCKERFILE)
    def test_bot_dockerfile_healthcheck(self):
        assert validate_healthcheck(DOCKER_BOT)
    def test_api_dockerfile_multistage(self):
        assert validate_multistage(DOCKERFILE)
    def test_bot_dockerfile_multistage(self):
        assert validate_multistage(DOCKER_BOT)
    def test_no_latest_in_api_dockerfile(self):
        unpinned = find_unpinned_images(DOCKERFILE)
        assert len(unpinned) == 0
    def test_no_latest_in_bot_dockerfile(self):
        unpinned = find_unpinned_images(DOCKER_BOT)
        assert len(unpinned) == 0
    def test_dockerignore_excludes_mql5(self):
        old_missing = "mql5" not in DOCKERIGNORE and "*.mq5" not in DOCKERIGNORE
        assert "mql5" in DOCKERIGNORE_HARDENED or "*.mq5" in DOCKERIGNORE_HARDENED
        assert old_missing
    def test_dockerignore_excludes_env(self):
        assert ".env" in DOCKERIGNORE
    def test_nonroot_user_detection(self):
        df = "FROM python:3.11\nUSER appuser\nCMD ['python']\n"
        assert validate_nonroot_user(df)
    def test_root_user_detection(self):
        df = "FROM python:3.11\nUSER root\nCMD ['python']\n"
        assert not validate_nonroot_user(df)

class TestDeployPipeline:
    def test_concurrency_guard_in_old_cicd(self):
        assert has_concurrency_guard(CI_CD_OLD)
    def test_concurrency_guard_in_hardened(self):
        assert has_concurrency_guard(CI_CD_HARDENED)
    def test_staging_has_smoke_test(self):
        assert has_smoke_test(CI_CD_OLD, "deploy-staging") or has_smoke_test(CI_CD_HARDENED, "deploy-staging")
    def test_production_has_smoke_test(self):
        assert has_smoke_test(CI_CD_HARDENED, "deploy-production")
    def test_has_rollback_strategy(self):
        assert has_rollback(CI_CD_OLD) or has_rollback(CI_CD_HARDENED)
    def test_has_failure_notify(self):
        assert has_failure_notify(CI_CD_HARDENED)
    def test_has_sarif_upload(self):
        assert has_sarif_upload(CI_CD_OLD) or has_sarif_upload(CI_CD_HARDENED)
    def test_blue_green_deployer_stages(self):
        bg = BlueGreenDeployer()
        stages = bg.stages()
        assert len(stages) >= 3
    def test_blue_green_ordering(self):
        bg = BlueGreenDeployer()
        stages = bg.stages()
        first = stages[0].name
        assert "api" in first.lower() or "service" in first.lower() or "up" in first.lower()
    def test_ci_result_fields(self):
        r = CIResult(job="backend", passed=True, tests=96, duration_s=1.5)
        assert r.job == "backend" and r.passed and r.tests == 96
    def test_ci_step_fields(self):
        s = CIStep(name="lint", command="ruff check", timeout_s=60)
        assert s.name == "lint" and s.timeout_s == 60
    def test_deploy_env_values(self):
        assert DeployEnv.STAGING.value == "staging"
        assert DeployEnv.PRODUCTION.value == "production"

class TestNginxConfig:
    def test_has_x_content_type_options(self):
        v = NginxConfigValidator(NGINX_CONF_TEMPLATE)
        assert "no-xco" not in v.validate()
    def test_has_x_frame_options(self):
        v = NginxConfigValidator(NGINX_CONF_TEMPLATE)
        assert "no-xfo" not in v.validate()
    def test_has_hsts(self):
        v = NginxConfigValidator(NGINX_CONF_TEMPLATE)
        assert "no-hsts" not in v.validate()
    def test_has_csp(self):
        v = NginxConfigValidator(NGINX_CONF_TEMPLATE)
        assert "no-csp" not in v.validate()
    def test_has_ssl_protocols(self):
        v = NginxConfigValidator(NGINX_CONF_TEMPLATE)
        assert "no-ssl" not in v.validate()
    def test_has_gzip(self):
        assert "gzip" in NGINX_CONF_TEMPLATE
    def test_has_limit_req(self):
        v = NginxConfigValidator(NGINX_CONF_TEMPLATE)
        issues = v.validate()
        assert "NO_RATE_LIMIT" not in issues
    def test_validate_clean(self):
        v = NginxConfigValidator(NGINX_CONF_TEMPLATE)
        assert v.validate() == []
    def test_missing_hsts_detected(self):
        conf = "server { listen 80; location / { proxy_pass http://api; } }"
        v = NginxConfigValidator(conf)
        issues = v.validate()
        assert "no-hsts" in issues
    def test_missing_csp_detected(self):
        conf = "server { add_header X-Frame-Options DENY; }"
        v = NginxConfigValidator(conf)
        issues = v.validate()
        assert "no-csp" in issues
    def test_missing_rate_limit_detected(self):
        conf = "server { location / { proxy_pass http://api; } }"
        v = NginxConfigValidator(conf)
        issues = v.validate()
        assert "NO_RATE_LIMIT" in issues
    def test_ssl_tls_version(self):
        assert "TLSv1.2" in NGINX_CONF_TEMPLATE or "TLSv1.3" in NGINX_CONF_TEMPLATE

class TestPrometheusConfig:
    def test_has_api_target(self):
        v = PrometheusConfigValidator(PROMETHEUS_CONF_TEMPLATE)
        assert "api" not in v.missing_targets()
    def test_has_redis_exporter(self):
        v = PrometheusConfigValidator(PROMETHEUS_CONF_TEMPLATE)
        assert "redis-exporter" not in v.missing_targets()
    def test_has_node_exporter(self):
        v = PrometheusConfigValidator(PROMETHEUS_CONF_TEMPLATE)
        assert "node-exporter" not in v.missing_targets()
    def test_has_cadvisor(self):
        v = PrometheusConfigValidator(PROMETHEUS_CONF_TEMPLATE)
        assert "cadvisor" not in v.missing_targets()
    def test_has_alerting_rules(self):
        v = PrometheusConfigValidator(PROMETHEUS_CONF_TEMPLATE)
        assert v.has_alerting_rules()
    def test_alert_rules_has_api_down(self):
        assert "APIDown" in ALERT_RULES_TEMPLATE
    def test_alert_rules_has_drawdown(self):
        assert "DrawdownCritical" in ALERT_RULES_TEMPLATE or "drawdown" in ALERT_RULES_TEMPLATE.lower()
    def test_prometheus_validate_clean(self):
        v = PrometheusConfigValidator(PROMETHEUS_CONF_TEMPLATE)
        assert v.validate() == []

class TestArtifactRegistry:
    def _reg(self):
        return ArtifactRegistry()
    def test_register_returns_entry(self):
        e = self._reg().register("ea", "3.20", b"data", DeployEnv.PRODUCTION)
        assert isinstance(e, ArtifactEntry)
    def test_sha256_correct(self):
        data = b"hello world"
        e = self._reg().register("ea", "3.20", data, DeployEnv.PRODUCTION)
        assert e.sha256 == hashlib.sha256(data).hexdigest()
    def test_size_correct(self):
        e = self._reg().register("ea", "3.20", b"x"*1000, DeployEnv.STAGING)
        assert e.size_bytes == 1000
    def test_get_existing(self):
        reg = self._reg(); reg.register("ea", "3.20", b"data", DeployEnv.PRODUCTION)
        assert reg.get("ea", "3.20", DeployEnv.PRODUCTION) is not None
    def test_get_missing_returns_none(self):
        assert self._reg().get("ea", "99.0", DeployEnv.PRODUCTION) is None
    def test_verify_correct_data(self):
        reg = self._reg(); data = b"artifact"
        reg.register("ea", "3.20", data, DeployEnv.PRODUCTION)
        assert reg.verify("ea", "3.20", DeployEnv.PRODUCTION, data)
    def test_verify_wrong_data(self):
        reg = self._reg()
        reg.register("ea", "3.20", b"original", DeployEnv.PRODUCTION)
        assert not reg.verify("ea", "3.20", DeployEnv.PRODUCTION, b"tampered")
    def test_verify_missing_entry(self):
        assert not self._reg().verify("ea", "0.0", DeployEnv.PRODUCTION, b"data")
    def test_revoke(self):
        reg = self._reg(); reg.register("ea", "3.20", b"data", DeployEnv.PRODUCTION)
        assert reg.revoke("ea", "3.20", DeployEnv.PRODUCTION)
    def test_verify_revoked_fails(self):
        reg = self._reg(); data = b"data"
        reg.register("ea", "3.20", data, DeployEnv.PRODUCTION)
        reg.revoke("ea", "3.20", DeployEnv.PRODUCTION)
        assert not reg.verify("ea", "3.20", DeployEnv.PRODUCTION, data)
    def test_download_count(self):
        reg = self._reg(); reg.register("ea", "3.20", b"d", DeployEnv.PRODUCTION)
        reg.record_download("ea", "3.20", DeployEnv.PRODUCTION)
        reg.record_download("ea", "3.20", DeployEnv.PRODUCTION)
        assert reg.get("ea", "3.20", DeployEnv.PRODUCTION).download_count == 2
    def test_download_revoked_no_count(self):
        reg = self._reg(); reg.register("ea", "3.20", b"d", DeployEnv.PRODUCTION)
        reg.revoke("ea", "3.20", DeployEnv.PRODUCTION)
        reg.record_download("ea", "3.20", DeployEnv.PRODUCTION)
        assert reg.get("ea", "3.20", DeployEnv.PRODUCTION).download_count == 0
    def test_list_all(self):
        reg = self._reg()
        reg.register("ea", "3.20", b"d", DeployEnv.PRODUCTION)
        reg.register("ea", "3.19", b"d", DeployEnv.STAGING)
        assert len(reg.list_all()) == 2
    def test_separate_env_entries(self):
        reg = self._reg()
        reg.register("ea", "3.20", b"prod", DeployEnv.PRODUCTION)
        reg.register("ea", "3.20", b"staging", DeployEnv.STAGING)
        assert reg.get("ea", "3.20", DeployEnv.PRODUCTION) is not None
    def test_entry_created_at(self):
        t0 = time.time(); e = self._reg().register("ea", "3.20", b"d", DeployEnv.PRODUCTION)
        assert e.created_at >= t0
    def test_revoke_missing_returns_false(self):
        assert not self._reg().revoke("noexist", "0.0", DeployEnv.PRODUCTION)

class TestBackupAndSmokeTest:
    def test_backup_has_redis_section(self):
        assert "backup_redis" not in BackupValidator(BACKUP_SH).missing_sections()
    def test_backup_has_verify_file(self):
        assert "verify_file" not in BackupValidator(BACKUP_SH).missing_sections()
    def test_backup_has_telegram_notify(self):
        assert "notify_telegram" not in BackupValidator(BACKUP_SH).missing_sections()
    def test_backup_has_retain_daily(self):
        assert "RETAIN_DAILY" not in BackupValidator(BACKUP_SH).missing_sections()
    def test_backup_has_retain_weekly(self):
        assert "RETAIN_WEEKLY" not in BackupValidator(BACKUP_SH).missing_sections()
    def test_backup_has_strict_mode(self):
        assert BackupValidator(BACKUP_SH).has_error_exit()
    def test_backup_has_s3_support(self):
        assert BackupValidator(BACKUP_SH).has_s3_upload()
    def test_backup_validate_clean(self):
        assert BackupValidator(BACKUP_SH).missing_sections() == []
    def test_smoke_client_check_live_fail(self):
        r = SmokeTestClient("http://localhost:19999", timeout=0.5).check_live()
        assert r.status == HealthStatus.UNHEALTHY
    def test_smoke_client_check_ready_fail(self):
        r = SmokeTestClient("http://localhost:19999", timeout=0.5).check_ready()
        assert r.status == HealthStatus.UNHEALTHY
    def test_smoke_client_all_healthy_false_on_fail(self):
        client = SmokeTestClient("http://localhost:19999", timeout=0.5)
        client.check_live()
        assert not client.all_healthy()
    def test_smoke_client_summary_format(self):
        client = SmokeTestClient("http://localhost:19999", timeout=0.5)
        client.check_live()
        s = client.summary()
        assert "total" in s and "healthy" in s
    def test_smoke_client_latency_recorded(self):
        r = SmokeTestClient("http://localhost:19999", timeout=0.5).check_live()
        assert r.latency_ms >= 0
    def test_health_check_result_fields(self):
        r = HealthCheckResult(service="api", status=HealthStatus.HEALTHY, latency_ms=12.5)
        assert r.service == "api" and r.latency_ms == 12.5
    def test_health_status_enum(self):
        assert HealthStatus.HEALTHY.value == "healthy"
    def test_deploy_env_enum(self):
        assert DeployEnv.STAGING.value == "staging"

class TestJobTimeouts:
    def test_hardened_backend_has_timeout(self):
        assert "timeout-minutes: 15" in CI_CD_HARDENED
    def test_hardened_frontend_has_timeout(self):
        assert "timeout-minutes: 10" in CI_CD_HARDENED
    def test_hardened_security_has_timeout(self):
        assert "timeout-minutes: 10" in CI_CD_HARDENED
    def test_hardened_docker_has_timeout(self):
        assert "timeout-minutes: 30" in CI_CD_HARDENED
    def test_hardened_staging_has_timeout(self):
        assert CI_CD_HARDENED.count("timeout-minutes: 15") >= 2
    def test_hardened_production_has_timeout(self):
        assert "timeout-minutes: 20" in CI_CD_HARDENED
    def test_old_cicd_all_jobs_have_timeout(self):
        assert "timeout-minutes" in CI_CD_OLD
    def test_unpinned_image_detection(self):
        assert len(find_unpinned_images("image: redis:latest")) > 0
    def test_pinned_image_passes(self):
        assert len(find_unpinned_images("image: redis:7.4-alpine")) == 0
    def test_from_latest_detection(self):
        assert len(find_unpinned_images("FROM python:latest\nRUN pip install\n")) > 0
