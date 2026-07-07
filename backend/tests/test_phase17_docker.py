"""
Phase 17 — Docker, Deployment & Production Readiness
96 tests across 8 classes
"""

import os
import re

import pytest
import yaml

# ─────────────────────────────────────────────────────────────
REPO = "/home/definable/phase17/repo"


def _file(relpath):
    p = os.path.join(REPO, relpath.lstrip("/"))
    if os.path.exists(p):
        with open(p) as f:
            return f.read()
    raise FileNotFoundError(f"Not found: {relpath}")


def _yaml(relpath):
    return yaml.safe_load(_file(relpath))


class TestDockerfileBackend:
    def setup_method(self):
        self.df = _file("Dockerfile")

    def test_T01_multi_stage_builder(self):
        assert "AS builder" in self.df

    def test_T02_multi_stage_runtime(self):
        assert "AS runtime" in self.df

    def test_T03_non_root_user(self):
        user_lines = [l.strip() for l in self.df.split("\n") if l.strip().startswith("USER ")]
        assert user_lines, "No USER directive found"
        assert all("root" not in l for l in user_lines)

    def test_T04_healthcheck_live(self):
        assert "HEALTHCHECK" in self.df
        assert "/health/live" in self.df

    def test_T05_healthcheck_interval(self):
        assert "--interval=" in self.df

    def test_T06_healthcheck_start_period(self):
        assert "--start-period=" in self.df

    def test_T07_pinned_python_version(self):
        from_lines = [l for l in self.df.split("\n") if l.strip().startswith("FROM")]
        assert all(":latest" not in l for l in from_lines)
        assert "python:3." in self.df

    def test_T08_no_gcc_in_runtime(self):
        lines = self.df.split("\n")
        in_runtime = False
        for line in lines:
            if "AS runtime" in line:
                in_runtime = True
            if in_runtime and "gcc" in line and line.strip().startswith("RUN"):
                pytest.fail("gcc found in runtime stage RUN")

    def test_T09_pythonpath_single_env(self):
        env_lines = [l for l in self.df.split("\n") if l.strip().startswith("ENV")]
        pythonpath_sets = [l for l in env_lines if "PYTHONPATH=" in l]
        assert len(pythonpath_sets) <= 1

    def test_T10_graceful_shutdown(self):
        assert "graceful-shutdown" in self.df or "graceful" in self.df.lower()

    def test_T11_expose_8000(self):
        assert "EXPOSE 8000" in self.df

    def test_T12_uvicorn_workers(self):
        assert "uvicorn" in self.df
        assert "--workers" in self.df

    def test_T13_no_copy_mql5_source(self):
        copy_lines = [l for l in self.df.split("\n") if l.strip().startswith("COPY")]
        assert not any("mql5" in l.lower() for l in copy_lines)

    def test_T14_label_maintainer(self):
        assert "LABEL" in self.df


class TestDockerfileFrontend:
    def setup_method(self):
        self.df = _file("frontend/Dockerfile")

    def test_T15_multi_stage_build(self):
        assert "AS builder" in self.df or "AS build" in self.df or "AS runner" in self.df

    def test_T16_nginx_runtime(self):
        assert "nginx" in self.df.lower()

    def test_T17_non_root(self):
        assert re.search(r"USER\s+\S+", self.df)

    def test_T18_healthcheck_nginx(self):
        assert "HEALTHCHECK" in self.df
        assert "health" in self.df.lower()

    def test_T19_node_pinned(self):
        from_lines = [l for l in self.df.split("\n") if l.strip().startswith("FROM")]
        assert any("node:" in l for l in from_lines)
        assert all(":latest" not in l for l in from_lines if "node" in l)

    def test_T20_npm_ci(self):
        assert "npm ci" in self.df

    def test_T21_expose_80(self):
        assert "EXPOSE 80" in self.df

    def test_T22_spa_fallback(self):
        assert "index.html" in self.df

    def test_T23_gzip(self):
        assert "gzip" in self.df

    def test_T24_security_headers(self):
        assert "X-Frame-Options" in self.df or "X-Content-Type" in self.df


class TestDockerfileDashboard:
    def setup_method(self):
        self.df = _file("dashboard/Dockerfile")

    def test_T25_streamlit_run(self):
        assert "streamlit" in self.df

    def test_T26_expose_8501(self):
        assert "8501" in self.df

    def test_T27_healthcheck_stcore(self):
        assert "HEALTHCHECK" in self.df
        assert "_stcore/health" in self.df

    def test_T28_pinned_streamlit(self):
        assert "streamlit==" in self.df

    def test_T29_headless(self):
        assert "headless" in self.df

    def test_T30_pythonpath(self):
        assert "PYTHONPATH" in self.df

    def test_T31_server_address(self):
        assert "0.0.0.0" in self.df

    def test_T32_dark_theme_or_branding(self):
        assert "dark" in self.df.lower() or "theme" in self.df.lower()


class TestDockerCompose:
    def setup_method(self):
        self.raw = _file("docker-compose.yml")
        self.dc = _yaml("docker-compose.yml")
        self.svc = self.dc.get("services", {})

    def test_T33_api_service_exists(self):
        assert "api" in self.svc

    def test_T34_redis_service_exists(self):
        assert "redis" in self.svc

    def test_T35_dashboard_service_exists(self):
        assert "dashboard" in self.svc

    def test_T36_frontend_service_exists(self):
        assert "frontend" in self.svc

    def test_T37_api_healthcheck(self):
        hc = self.svc["api"].get("healthcheck", {})
        test = hc.get("test", [])
        assert any("health" in str(t) for t in test)

    def test_T38_redis_healthcheck(self):
        hc = self.svc["redis"].get("healthcheck", {})
        assert hc

    def test_T39_dashboard_healthcheck(self):
        hc = self.svc["dashboard"].get("healthcheck", {})
        test = hc.get("test", [])
        assert any("health" in str(t) for t in test)

    def test_T40_frontend_healthcheck(self):
        hc = self.svc["frontend"].get("healthcheck", {})
        assert hc

    def test_T41_ports_bound_localhost(self):
        for name, svc in self.svc.items():
            for port in svc.get("ports", []):
                port_str = str(port)
                if ":" in port_str and not port_str.startswith("127.0.0.1"):
                    if name not in ("nginx", "prometheus", "grafana"):
                        pytest.fail(f"Port {port} in {name} not bound to 127.0.0.1")

    def test_T42_no_hardcoded_passwords(self):
        assert "mysecretpassword" not in self.raw
        assert "admin123" not in self.raw
        assert "password123" not in self.raw

    def test_T43_memory_limits(self):
        for name in ("api", "redis"):
            deploy = self.svc[name].get("deploy", {})
            resources = deploy.get("resources", {})
            assert resources.get("limits", {}).get("memory")

    def test_T44_json_logging(self):
        for name in ("api", "redis"):
            logging = self.svc[name].get("logging", {})
            assert logging.get("driver") == "json-file"

    def test_T45_depends_on_healthy(self):
        api_deps = self.svc["api"].get("depends_on", {})
        if isinstance(api_deps, dict):
            for dep, cond in api_deps.items():
                if isinstance(cond, dict):
                    assert cond.get("condition") == "service_healthy"

    def test_T46_redis_password_from_env(self):
        redis_cmd = str(self.svc["redis"].get("command", ""))
        assert "${" in redis_cmd or "$REDIS_PASSWORD" in redis_cmd

    def test_T47_network_defined(self):
        assert "networks" in self.dc
        assert len(self.dc["networks"]) >= 1

    def test_T48_telegram_bot_service(self):
        assert "telegram_bot" in self.svc or "bot" in self.svc


class TestDockerComposeProd:
    def setup_method(self):
        self.raw = _file("docker-compose.prod.yml")
        self.dc = _yaml("docker-compose.prod.yml")
        self.svc = self.dc.get("services", {})

    def test_T49_restart_unless_stopped(self):
        for name, svc in self.svc.items():
            assert svc.get("restart") == "unless-stopped", f"{name} restart={svc.get('restart')}"

    def test_T50_api_uses_expose_not_ports(self):
        api = self.svc.get("api", {})
        ports = api.get("ports", [])
        expose = api.get("expose", [])
        assert not ports or expose

    def test_T51_nginx_service(self):
        assert "nginx" in self.svc

    def test_T52_prometheus_service(self):
        assert "prometheus" in self.svc

    def test_T53_grafana_service(self):
        assert "grafana" in self.svc

    def test_T54_node_exporter(self):
        assert "node-exporter" in self.svc or "node_exporter" in self.svc

    def test_T55_cadvisor(self):
        assert "cadvisor" in self.svc

    def test_T56_redis_exporter(self):
        assert "redis-exporter" in self.svc or "redis_exporter" in self.svc

    def test_T57_volumes_defined(self):
        assert "volumes" in self.dc
        assert len(self.dc["volumes"]) >= 2

    def test_T58_security_opt_no_new_privileges(self):
        checked = 0
        for name, svc in self.svc.items():
            sec = svc.get("security_opt", [])
            if sec:
                assert any("no-new-privileges" in str(s) for s in sec)
                checked += 1
        assert checked > 0

    def test_T59_grafana_no_anonymous(self):
        gf = self.svc.get("grafana", {})
        env_str = str(gf.get("environment", []))
        assert "false" in env_str.lower()

    def test_T60_backup_service(self):
        assert "backup" in self.svc

    def test_T61_prometheus_healthcheck(self):
        hc = self.svc.get("prometheus", {}).get("healthcheck", {})
        assert hc

    def test_T62_grafana_healthcheck(self):
        hc = self.svc.get("grafana", {}).get("healthcheck", {})
        assert hc

    def test_T63_nginx_ssl_ports(self):
        nginx_ports = self.svc.get("nginx", {}).get("ports", [])
        assert any("443" in str(p) for p in nginx_ports)

    def test_T64_update_config_rollback(self):
        api_deploy = self.svc.get("api", {}).get("deploy", {})
        update_cfg = api_deploy.get("update_config", {})
        assert update_cfg.get("failure_action") == "rollback"


class TestDockerignore:
    def setup_method(self):
        self.di = _file(".dockerignore")

    def test_T65_mql5_excluded(self):
        assert "mql5/" in self.di

    def test_T66_mq5_files_excluded(self):
        assert "*.mq5" in self.di

    def test_T67_mqh_files_excluded(self):
        assert "*.mqh" in self.di

    def test_T68_git_excluded(self):
        assert ".git" in self.di

    def test_T69_env_secrets_excluded(self):
        assert ".env" in self.di

    def test_T70_tests_excluded(self):
        assert "tests/" in self.di or "test_" in self.di

    def test_T71_node_modules_excluded(self):
        assert "node_modules" in self.di

    def test_T72_pycache_excluded(self):
        assert "__pycache__" in self.di

    def test_T73_releases_excluded(self):
        assert "releases/" in self.di

    def test_T74_infra_excluded(self):
        assert "infra/" in self.di


class TestNginxConfig:
    def setup_method(self):
        self.nginx = _file("infra/nginx/nginx.conf")

    def test_T75_server_tokens_off(self):
        assert "server_tokens off" in self.nginx

    def test_T76_hsts_header(self):
        assert "Strict-Transport-Security" in self.nginx
        assert "max-age=" in self.nginx

    def test_T77_x_frame_deny(self):
        assert "X-Frame-Options" in self.nginx

    def test_T78_x_content_type(self):
        assert "X-Content-Type-Options" in self.nginx

    def test_T79_rate_limit_zone(self):
        assert "limit_req_zone" in self.nginx

    def test_T80_tls_12_plus(self):
        assert "TLSv1.2" in self.nginx or "TLSv1.3" in self.nginx

    def test_T81_gzip_enabled(self):
        assert "gzip on" in self.nginx

    def test_T82_health_endpoint(self):
        assert "nginx-health" in self.nginx

    def test_T83_ssl_session_cache(self):
        assert "ssl_session_cache" in self.nginx

    def test_T84_proxy_headers(self):
        assert "X-Real-IP" in self.nginx or "X-Forwarded-For" in self.nginx


class TestCIWorkflow:
    def setup_method(self):
        self.ci = _file(".github/workflows/ci-cd-hardened.yml")
        self.yml = _yaml(".github/workflows/ci-cd-hardened.yml")

    def test_T85_has_backend_job(self):
        jobs = self.yml.get("jobs", {})
        assert "backend" in jobs or "test" in jobs

    def test_T86_has_frontend_job(self):
        jobs = self.yml.get("jobs", {})
        assert "frontend" in jobs

    def test_T87_has_security_job(self):
        jobs = self.yml.get("jobs", {})
        assert "security" in jobs

    def test_T88_has_docker_job(self):
        jobs = self.yml.get("jobs", {})
        assert "docker" in jobs

    def test_T89_has_deploy_staging(self):
        jobs = self.yml.get("jobs", {})
        assert any("staging" in k for k in jobs)

    def test_T90_has_deploy_production(self):
        jobs = self.yml.get("jobs", {})
        assert any("production" in k or "prod" in k for k in jobs)

    def test_T91_no_hardcoded_secrets(self):
        assert "ci-test-secret-key-not-for-production" not in self.ci
        assert "jwt-secret-key-hardcoded" not in self.ci

    def test_T92_lint_not_silenced(self):
        ruff_lines = [l for l in self.ci.split("\n") if "ruff" in l and "check" in l]
        assert ruff_lines
        assert not any("|| true" in l for l in ruff_lines)

    def test_T93_coverage_threshold(self):
        assert "cov-fail-under" in self.ci
        m = re.search(r"cov-fail-under=(\d+)", self.ci)
        if m:
            assert int(m.group(1)) >= 70

    def test_T94_telegram_notify(self):
        assert "telegram" in self.ci.lower()

    def test_T95_smoke_test_health(self):
        assert "health/live" in self.ci
        assert "health/ready" in self.ci

    def test_T96_blue_green_and_rollback(self):
        assert "Blue/Green" in self.ci or "blue" in self.ci.lower()
        assert "restart" in self.ci or "rollback" in self.ci
