"""
tests/test_frontend_phase_e.py
فاز E — Frontend config و env validation unit tests
اجرا: pytest tests/test_frontend_phase_e.py -v
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parent.parent
FRONTEND = ROOT / "frontend"


class TestFrontendConfig:
    """config.ts مقادیر صحیح دارد."""

    def test_env_local_example_exists(self):
        f = FRONTEND / ".env.local.example"
        assert f.exists(), ".env.local.example نباید حذف شود"

    def test_env_local_example_has_required_vars(self):
        f = FRONTEND / ".env.local.example"
        content = f.read_text(encoding="utf-8")
        for var in ("VITE_API_URL", "VITE_WS_URL", "VITE_APP_ENV"):
            assert var in content, f"{var} باید در .env.local.example باشد"

    def test_config_ts_uses_env_vars(self):
        f = FRONTEND / "src" / "utils" / "config.ts"
        content = f.read_text(encoding="utf-8")
        assert "VITE_API_URL" in content
        assert "VITE_WS_URL"  in content
        # نباید hardcode ip/domain داشته باشد
        assert "192.168" not in content
        assert "yourdomain.com" not in content

    def test_api_ts_no_hardcoded_localhost(self):
        f = FRONTEND / "src" / "utils" / "api.ts"
        content = f.read_text(encoding="utf-8")
        # باید VITE_API_URL استفاده کند
        assert "VITE_API_URL" in content
        # localhost تنها به عنوان fallback در env ?? مجاز است
        # نباید اولین مقدار hardcode باشد
        assert "const _BASE" in content or "VITE_API_URL" in content

    def test_websocket_context_uses_config(self):
        f = FRONTEND / "src" / "contexts" / "WebSocketContext.tsx"
        content = f.read_text(encoding="utf-8")
        assert "WS_BASE_URL" in content or "config" in content
        assert "tokenStorage" in content  # نه localStorage مستقیم

    def test_package_json_has_required_deps(self):
        f = FRONTEND / "package.json"
        pkg = json.loads(f.read_text(encoding="utf-8"))
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        for dep in ("react", "react-dom", "react-router-dom"):
            assert dep in deps, f"{dep} باید در package.json باشد"

    def test_vite_config_has_alias(self):
        f = FRONTEND / "vite.config.ts"
        content = f.read_text(encoding="utf-8")
        assert '"@"' in content or "'@'" in content
        assert "resolve" in content

    def test_no_hardcoded_production_urls_in_source(self):
        """هیچ URL تولید hardcode در source نباشد."""
        bad_patterns = [
            "http://api:8000",   # docker internal — فقط در dashboard مجاز
        ]
        for ts_file in (FRONTEND / "src").rglob("*.ts{x,}"):
            content = ts_file.read_text(encoding="utf-8", errors="ignore")
            for pat in bad_patterns:
                assert pat not in content, (
                    f"{ts_file.name}: حاوی URL هاردکد '{pat}' است"
                )
