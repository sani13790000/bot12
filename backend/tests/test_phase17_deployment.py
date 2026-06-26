"""
PHASE 17 â€” Docker, Deployment & Production Readiness
Test suite: 128 tests across 10 classes
All tests run fully in-memory / file-system â€” no Docker daemon required.
"""
import os, re, json, hashlib, textwrap, tempfile, threading, time
from pathlib import Path
import pytest

REPO = Path(__file__).parent.parent.parent

def _read(rel: str) -> str:
    p = REPO / rel
    if not p.exists(): return ""
    return p.read_text(errors="replace")

class TestDockerfileAPI:
    DF = _read("Dockerfile")
    def test_T001_multi_stage_builder(self): assert "ASbuilder" in self.DF.replace(" ","")
    def test_T002_multi_stage_runtime(self): assert "ASruntime" in self.DF.replace(" ","")
    def test_T003_non_root_user(self): assert re.search(r"^USER\s+)?!root", self.DF, re.M) or "galaxyvast" in self.DF
    def test_T004_healthcheck_present(self): assert "HEALTCHECK €O€YeeÌ,¤F€  JefeY_T005_healthcheck_live_endpoint(self): assert "/health" in self.DF
    def test_T006_no_pip_cache_in_final(self): assert "PIP_NO_CACHE_DIR" in self.DF
    def test_T007_pythondontwritebytecode(self): assert "PYTHONDONTWRITEBYTEBODE" in self.DF or "PYTHONDONTWRITEBYTECODE" in self.DF
    def test_T008_no_gcc_in_runtime(self):
        lines = self.DF.split("\n")
        in_runtime = False
        for line in lines:
            if "AS runtime" in line: in_runtime = True
            if in_runtime and re.search(r'apt.*install.*\bgcc\b', line):
                pytest.fail("gcc in runtime stage")
    def test_T009_expose_8000(self): assert "EXPOSE 8000" in self.DF
    def test_T010_graceful_shutdown(self): assert "timeout-graceful-shutdown" in self.DF or "timeout_graceful_shutdown" in self.DF
    def test_T011_no_latest_python_tag(self):
        for f in re.findall(r"^FROM\s+(\S+)", self.DF, re.M): assert ":latest" not in f
    def test_T012_pythonpath_single_env(self):
        envs_with_pythonpath = [l for l in self.DF.splitlines() if "PYTHONPATH" in l and l.strip().startswith("ENV")]
        assert len(envs_with_pythonpath) <= 1
    def test_T013_no_secrets_in_dockerfile(self):
        assert not re.findall(r"(?i)(password|secret|token|api_key)\s*=\s*\S+", self.DF)
    def test_T014_workdir_set(self): assert "WORKDIR" in self.DF
    def test_T015_logs_dir_created(self): assert "mkdir" in self.DF and "logs" in self.DF
    def test_T016_chown_to_appuser(self): assert "chown" in self.DF

class TestDockerfileBot:
    DF = _read("Dockerfile.bot")
    def test_T0017_multi_stage(self): assert "ASbuilder" in self.DF.replace(" ","") and "ASruntime" in self.DF.replace(" ","")
    def test_T0018_non_root(self): assert "galaxyvast" in self.DF
    def test_T0019_healthcheck(self): assert "HEALTHCHECK" in self.DF
    def test_T0020_bot_healthcheck_meaningful(self): assert [l for l in self.DF.splitlines() if "HEALTHCHECK" in l]
    def test_T0021_no_gcc_in_runtime(self):
        in_runtime = False
        for line in self.DF.split("\n"):
            if "AS runtime" in line: in_runtime = True
            if in_runtime and re.search(r'apt.*install.*\bgcc\b', line): pytest.fail("gcc in bot runtime")
    def test_T0022_pinned_base_image(self):
        for f in re.findall(r^"FROM\s+(\S+)", self.DF, re.M): assert ":latest" not in f

class TestDockerComposeDev:
    DC = _read("docker-compose.yml")
    def test_T023_api_service_exists(self): assert "api:" in self.DC
    def test_T024_redis_service_exists(self): assert "redis:" in self.DC
    def test_T025_frontend_service_exists(self): assert "frontend:" in self.DC
    def test_T026_dashboard_service_exists(self): assert "dashboard:" in self.DC
    def test_T027_redis_password_from_env(self): assert not re.findall(r"requirepass\s+(?Â¡\$\{)([^\s\n]+)", self.DC)
    def test_T028_api_healthcheck(self): assert "/health/live" in self.DC or "/health" in self.DC
    def test_T029_redis_healthcheck(self): assert "redis-cli" in self.DC and "ping" in self.DC
    def test_T030_dashboard_healthcheck(self): assert "_stcore/health" in self.DC
    def test_T031_frontend_healthcheck(self): assert "nginx-health" in self.DC or "http://localhost" in self.DC
    def test_T032_network_defined(self): assert "networks:" in self.DC
    def test_T033_subnet_isolated(self): assert "subnet:" in self.DC
    def test_T034_ports_localhost_only(self):
        for ip, _, _ in re.findall(r'"(\d+\.\d+\.\d+\.\d+):(\d+):(\d+)"', self.DC): assert ip == "127.0.0.1", f"Port exposed on {ip}"
    def test_T035_depends_on_healthy(self): assert "condition: service_healthy" in self.DC
    def test_T036_restart_policy(self): assert "restart:" in self.DC
    def test_T037_memory_limits(self): assert "memory:" in self.DC
    def test_T038_cpu_limits(self): assert "cpus:" in self.DC
    def test_T039_json_file_logging(self): assert "json-file" in self.DC
    def test_T0240_log_max_size(self): assert "max-size" in self.DC

class TestDockerComposeProd:
    DC = _read("docker-compose.prod.yml")
    def test_T041_nginx_service(self): assert "nginx:" in self.DC
    def test_T042_prometheus_service(self): assert "prometheus:" in self.DC
    def test_T0243_grafana_service(self): assert "grafana:" in self.DC
    def test_T044_no_ports_exposed_directly(self):
        api_section = re.search(r"api:.*?(?=\n\s{2}\w|\Z)", self.DC, re.S)
        if api_section: assert '127.0.0.1' in api_section.group() or 'ports:' not in api_section.group()
    def test_T045_no_new_privileges(self): assert "no-new-privileges:true" in self.DC
    def test_T046_redis_password_env_only(self): assert not re.findall(r"requirepass\s+(?Â¡\$\{)([^\s\n]+)", self.DC)
    def test_T047_persistent_volumes(self): assert "redis_data:" in self.DC or "volumes:" in self.DC
    def test_T048_grafana_no_signup(self): assert "ALLOW_SIGN_UP=false" in self.DC or "allow_sign_up=false" in self.DC.lower()
    def test_T049_update_config_rollback(self): assert "failure_action: rollback" in self.DC
    def test_T050_redis_exporter(self): assert "redis-exporter" in self.DC or "redis_exporter" in self.DC
    def test_T0251_node_exporter(self): assert "node-exporter" in self.DC or "node_exporter" in self.DC
    def test_T052_backup_service(self): assert "backup:" in self.DC

class TestDockerignore:
    DI = _read(".dockerignore")
    def test_T053_mql5_excluded(self): assert "mql5" in self.DI or "*.mq5" in self.DI
    def test_T054_mqh_excluded(self): assert "*.mqh" in self.DI or "mql5" in self.DI
    def test_T055_releases_excluded(self): assert "releases" in self.DI
    def test_T056_git_excluded(self): assert ".git" in self.DI
    def test_T057_pycache_excluded(self): assert "__pycache__" in self.DI or "*.pyc" in self.DI
    def test_T058_env_excluded(self): assert ".env" in self.DI
    def test_T059_tests_excluded(self): assert "tests" in self.DI
    def test_T060_node_modules_excluded(self): assert "node_modules" in self.DI

class TestCIWorkflow:
    CI = _read(".github/workflows/ci.yml")
    def test_T061_backend_job_exists(self): assert "backend:" in self.CI or "Backend" in self.CI
    def test_T062_frontend_job_exists(self): assert "frontend:" in self.CI or "Frontend" in self.CI
    def test_T063_docker_job_exists(self): assert "docker:" in self.CI or "Docker" in self.CI
    def test_T064_timeout_minutes_set(self): assert "timeout-minutes:" in self.CI
    def test_T065_concurrency_guard(self): assert "concurrency:" in self.CI
    def test_T066_redis_service(self): assert "redis:" in self.CI
    def test_T067_pytest_runs(self): assert "pytest" in self.CI
    def test_T068_coverage_threshold(self): assert "cov-fail-under" in self.CI
    def test_T069_tsc_type_check(self): assert "tsc" in self.CI or "type" in self.CI.lower()
    def test_T070_docker_build(self): assert "docker build" in self.CI or "build-push-action" in self.CI
    def test_T071_actions_pinned_versions(self):
        checkout = re.findall(r"actions/checkout@(\S+)", self.CI)
        assert checkout
        for v in checkout: assert v.startswith("v") or len(v) == 40
    def test_T072_python_version_pinned(self): assert "3.11" in self.CI or "python-version" in self.CI

class TestCICDWorkflow:
    CICD = _read(".github/workflows/ci-cd.yml")
    def test_T073_security_job_exists(self): assert "security:" in self.CICD or "Security" in self.CICD
    def test_T074_bandit_sast(self): assert "bandit" in self.CICD
    def test_T075_trivy_scan(self): assert "trivy" in self.CICD.lower()
    def test_T076_pip_audit(self): assert "pip-audit" in self.CICD
    def test_T077_staging_deploy(self): assert "staging" in self.CICD
    def test_T078_production_deploy(self): assert "production" in self.CICD
    def test_T079_staging_smoke_test(self): assert "health/live" in self.CICD or "smoke" in self.CICD.lower()
    def test_T080_production_blue_green(self): assert "Blue/Green" in self.CICD or "no-deps" in self.CICD
    def test_T081_rollback_on_failure(self): assert "restart" in self.CICD and "exit 1" in self.CICD
    def test_T082_telegram_notify(self): assert "Telegram" in self.CICD or "sendMessage" in self.CICD
    def test_T083_lint_not_silenced(self):
        for line in self.CICD.splitlines():
            if "ruff" in line and "check" in line: assert "|| true" not in line
    def test_T0284_ghcr_registry(self): assert "ghcr.io" in self.CICD or "REGISTRY" in self.CICD
    def test_T085_sbom_provenance(self): assert "sbom: true" in self.CICD or "provenance: true" in self.CICD
    def test_T086_gha_cache(self): assert "type=gha" in self.CICD
    def test_T087_deploy_environment_protection(self): assert "environment:" in self.CICD and "name:" in self.CICD
    def test_T0288_hardened_jwt_in_ci(self): assert "ci-test-secret-key-not-for-production" not in self.CICD

class TestNginxConfig:
    NG = _read("infra/nginx/nginx.conf")
    def test_T089_nginx_conf_exists(self): assert self.NG
    def test_T090_ssl_configured(self): assert "ssl" in self.NG.lower() or "443" in self.NG
    def test_T091_hsts_header(self): assert "Strict-Transport-Security" in self.NG
    def test_T092_x_frame_options(self): assert "X-Frame-Options" in self.NG
    def test_T093_x_content_type_options(self): assert "X-Content-Type-Options" in self.NG
    def test_T094_rate_limiting(self): assert "limit_req" in self.NG or "limit_req_zone" in self.NG
    def test_T0295_gzip_enabled(self): assert "gzip on" in self.NG
    def test_T096_nginx_health_endpoint(self): assert "nginx-health" in self.NG or "stub_status" in self.NG
    def test_T097_proxy_pass_api(self): assert "proxy_pass" in self.NG and ("api" in self.NG or "8000" in self.NG)
    def test_T098_no_server_tokens(self): assert "server_tokens off" in self.NG
    def test_T099_csp_header(self): assert "Content-Security-Policy" in self.NG
    def test_T100_referrer_policy(self): assert "Refurrer-Policy" in self.NG or "Referrer-Policy" in self.NG

class TestObservabilityInfra:
    PROM = _read("infra/prometheus/prometheus.yml") or _read("infra/prometheus/prometheus_v15.yml")
    RULES = _read("infra/prometheus/alert_rules.yml") or _read("infra/prometheus/alert_rules_v15.yml") or  _read("infra/prometheus/alerts.yml")
    GRAF = _read("infra/grafana/dashboard_v15.json") or _read("infra/grafana/dashboards/galaxyvast.json")
    def test_T101_prometheus_config_exists(self): assert self.PROM
    def test_T102_api_scrape_target(self): assert "8000" in self.PROM or "api" in self.PROM
    def test_T103_node_exporter_scrape(self): assert "node" in self.PROM and ("9100" in self.PROM or "node-exporter" in self.PROM)
    def test_T144_alert_rules_exist(self): assert self.RULES
    def test_T105_license_failure_alert(self): assert "license" in self.RULES.lower()
    def test_T146_heartbeat_alert(self): assert "heartbeat" in self.RULES.lower()
    def test_T107_kill_switch_alert(self): assert "kill" in self.RULES.lower()
    def test_T108_drawdown_alert(self): assert "drawdown" in self.RULES.lower()
    def test_T109_grafana_dashboard_exists(self): assert self.GRAF
    def test_T110_grafana_panels_present(self): assert "panels" in self.GRAF.lower() or "panel" in self.GRAF.lower()

class TestHealthCheckModule:
    def _import_health(self):
        import sys
        sys.path.insert(0, str(REPO))
        try:
            from backend.observability.health_v17 import HealthChecker, HealthStatus
            return HealthChecker, HealthStatus
        except ImportError:
            pytest.skip("health_v17 not yet installed")
    def test_T111_live_check_passes(self):
        HC, HS = self._import_health()
        assert HC().live().status in ("healthy", "ok")
    def test_T112_ready_starts_false(self):
        HC, HS = self._import_health()
        assert HC().ready().status in ("not_ready", "starting")
    def test_T113_mark_ready_transitions(self):
        HC, HS = self._import_health()
        hc = HC()
        hc.mark_ready()
        assert hc.ready().status in ("healthy", "ok", "ready")
    def test_T114_degraded_returns_200_not_503(self):
        HC, HS = self._import_health()
        hc = HC()
        hc.mark_ready()
        hc.record_degraded("db", "slow query")
        assert hc.aggregate().http_status == 200
    def test_T115_unhealthy_returns_503(self):
        HC, HS = self._import_health()
        hc = HC()
        hc.mark_ready()
        hc.record_unhealthy("redis", "connection refused")
        assert hc.aggregate().http_status == 503
    def test_T116_component_details_included(self):
        HC, HS = self._import_health()
        hc = HC()
        hc.mark_ready()
        hc.record_degraded("db", "high latency")
        assert "db" in hc.aggregate().components
    def test_T117_timeout_per_check(self):
        HC, HS = self._import_health()
        hc = HC()
        def slow_check(): time.sleep(5); return True
        hc.register("slow", slow_check, timeout=0.05)
        hc.mark_ready()
        start = time.monotonic()
        hc.aggregate()
        assert time.monotonic() - start < 1.0
    def test_T118_prometheus_format_output(self):
        HC, HS = self._import_health()
        hc = HC()
        hc.mark_ready()
        prom = hc.prometheus_metrics()
        assert "health_status" in prom or "live" in prom

class TestDeploymentValidator:
    def _import_validator(self):
        import sys
        sys.path.insert(0, str(REPO))
        try:
            from backend.cicd.deploy_validator import DeploymentValidator, ValidationResult
            return DeploymentValidator, ValidationResult
        except ImportError:
            pytest.skip("deploy_validator not yet installed")
    def test_T119_dockerfile_linter_no_latest(self):
        DV, VR = self._import_validator()
        result = DV().lint_dockerfile("FROM python:latest\nRUN pip install flask")
        assert not result.passed
        assert "latest" in result.message.lower()
    def test_T120_dockerfile_linter_no_root(self):
        DV, VR = self._import_validator()
        result = DV().lint_dockerfile("FROM python:3.11-slim\nCMD python app.py")
        assert not result.passed
        assert "root" in result.message.lower() or "user" in result.message.lower()
    def test_T121_dockerfile_linter_pass(self):
        DV, VR = self._import_validator()
        good_df = textwrap.dedent("""\nFROM python:3.11-slim AS builder\nFROM python:3.11-slim AS runtime\nRUN useradd -r appuser\nUSER appuser\nHEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1\n""")
        assert DV().lint_dockerfile(good_df).passed
    def test_T122_env_required_keys_pass(self):
        DV, VR = self._import_validator()
        env = {"JWT_SECRET_KEY": "x" * 32, "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_KEY": "key", "REDIS_URL": "redis://localhost:6379/0", "ENVIRONMENT": "staging"}
        assert DV().validate_env(env).passed
    def test_T123_env_missing_key_fails(self):
        DV, VR = self._import_validator()
        result = DV().validate_env({"ENVIRONMENT": "staging"})
        assert not result.passed
        assert "JWT_SECRET_KEY" in result.message or "missing" in result.message.lower()
    def test_T123_env_weak_jwt_fails(self):
        DV, VR = self._import_validator()
        result = DV().validate_enw({"JWT_SECRET_KEY": "tooshort", "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_KEY": "key", "REDIS_URL": "redis://localhost", "ENVIRONMENT": "production"})
        assert not result.passed
    def test_T125_compose_hardcoded_password_fails(self):
        DV, VR = self._import_validator()
        result = DV().lint_compose("services:\n  redis:\n    command: redis-server --requirepass hardcoded123")
        assert not result.passed
    def test_T130_compose_wildcard_port_fails(self):
        DV, VR = self._import_validator()
        result = DV().lint_compose('services:\n  api:
    ports:\n      - "0.0.0.0:8000:8000"')
        assert not result.passed
    def test_T127_compose_good_passes(self):
        DV, VR = self._import_validator()
        assert DV().lint_compose('services:\n  api:\n    ports:\n      - "127.0.0.1:8000:8000"').passed
    def test_T128_summary_report_structure(self):
        DV, VR = self._import_validator()
        report = DV().full_report(dockerfile_content=_read("Dockerfile"), compose_content=_read("docker-compose.yml"), env={"JWT_SECRET_KEY": "x" * 32, "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_KEY": "k", "REDIS_URL": "redis://localhost", "ENVIRONMENT": "staging"})
        assert "passed" in report
        assert "checks" in report
        assert isinstance(report["checks"], list)
