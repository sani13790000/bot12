"""
Phase 18 — Final Documentation Tests
103 tests covering all 6 doc files
"""

import re
from pathlib import Path

import pytest

# مسیر docs را نسبت به root repo تعیین می‌کنیم
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
ROOT_DIR = Path(__file__).parent.parent.parent


def read_doc(name: str, root: bool = False) -> str:
    base = ROOT_DIR if root else DOCS_DIR
    p = base / name
    if not p.exists():
        pytest.skip(f"Doc not found: {p}")
    return p.read_text(encoding="utf-8")


def section_exists(text: str, heading: str) -> bool:
    return heading in text


# ===========================================================================
# T01-T16: README.md
# ===========================================================================


class TestREADME:
    DOC = "README.md"

    def _t(self):
        return read_doc(self.DOC, root=True)

    def test_T01_file_exists(self):
        assert (ROOT_DIR / self.DOC).exists()

    def test_T02_min_size(self):
        assert len(self._t()) >= 2000

    def test_T03_risk_warning_present(self):
        t = self._t()
        assert "ریسک" in t or "risk" in t.lower() or "تضمین" in t

    def test_T04_architecture_section(self):
        t = self._t()
        assert "معماری" in t or "Architecture" in t or "architecture" in t.lower()

    def test_T05_quickstart_section(self):
        t = self._t()
        assert "راه‌اندازی" in t or "Quick" in t or "Getting Started" in t

    def test_T06_phase_table(self):
        t = self._t()
        assert ("P1" in t or "Phase" in t) and "✅" in t

    def test_T07_test_count_mentioned(self):
        t = self._t()
        assert "تست" in t or "test" in t.lower()

    def test_T08_docs_links(self):
        t = self._t()
        assert "DEPLOYMENT.md" in t
        assert "SECURITY.md" in t
        assert "MQL5_INSTALLATION.md" in t

    def test_T09_kill_switch_warning(self):
        t = self._t()
        assert "Kill Switch" in t or "/halt" in t

    def test_T10_drawdown_warning(self):
        t = self._t()
        assert "Drawdown" in t or "drawdown" in t or "۱۰" in t or "10" in t

    def test_T11_no_real_secrets(self):
        t = self._t()
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ" not in t

    def test_T12_docker_command(self):
        t = self._t()
        assert "docker compose" in t or "docker-compose" in t

    def test_T13_github_link_or_clone(self):
        t = self._t()
        assert "git clone" in t or "github.com" in t

    def test_T14_saas_mentioned(self):
        t = self._t()
        assert "SaaS" in t or "License" in t or "license" in t.lower()

    def test_T15_badges_present(self):
        t = self._t()
        assert "img.shields.io" in t or "badge" in t.lower()

    def test_T16_code_blocks_present(self):
        assert self._t().count("```") >= 2


# ===========================================================================
# T17-T32: DEPLOYMENT.md
# ===========================================================================


class TestDEPLOYMENT:
    DOC = "DEPLOYMENT.md"

    def _t(self):
        return read_doc(self.DOC, root=True)

    def test_T17_file_exists(self):
        assert (ROOT_DIR / self.DOC).exists()

    def test_T18_min_size(self):
        assert len(self._t()) >= 2000

    def test_T19_risk_warning(self):
        assert "ریسک" in self._t() or "risk" in self._t().lower()

    def test_T20_dev_section(self):
        assert "Development" in self._t() or "Dev" in self._t()

    def test_T21_staging_section(self):
        assert "Staging" in self._t() or "staging" in self._t()

    def test_T22_production_section(self):
        assert "Production" in self._t() or "production" in self._t()

    def test_T23_migration_section(self):
        assert "Migration" in self._t() or "migration" in self._t()

    def test_T24_env_variables_section(self):
        assert "Environment" in self._t() or "env" in self._t().lower()

    def test_T25_health_check_section(self):
        assert "Health" in self._t() or "health" in self._t()

    def test_T26_rollback_section(self):
        assert "Rollback" in self._t() or "rollback" in self._t()

    def test_T27_backup_section(self):
        assert "Backup" in self._t() or "backup" in self._t()

    def test_T28_blue_green(self):
        assert "Blue" in self._t() or "Blue/Green" in self._t()

    def test_T29_generate_secrets_command(self):
        assert "token_hex" in self._t() or "openssl" in self._t()

    def test_T30_supabase_mentioned(self):
        assert "supabase" in self._t().lower()

    def test_T31_docker_compose_command(self):
        assert "docker compose" in self._t() or "docker-compose" in self._t()

    def test_T32_troubleshooting_section(self):
        t = self._t()
        assert "Troubleshooting" in t or "troubleshoot" in t.lower() or "عیب‌یابی" in t


# ===========================================================================
# T33-T48: SECURITY.md
# ===========================================================================


class TestSECURITY:
    DOC = "SECURITY.md"

    def _t(self):
        return read_doc(self.DOC, root=True)

    def test_T33_file_exists(self):
        assert (ROOT_DIR / self.DOC).exists()

    def test_T34_min_size(self):
        assert len(self._t()) >= 2000

    def test_T35_no_public_issue(self):
        assert "GitHub Issue" in self._t() or "public" in self._t().lower()

    def test_T36_email_contact(self):
        assert "@" in self._t()

    def test_T37_severity_levels(self):
        t = self._t()
        assert "Critical" in t or "critical" in t
        assert "High" in t or "high" in t

    def test_T38_jwt_mentioned(self):
        assert "JWT" in self._t()

    def test_T39_bcrypt_mentioned(self):
        assert "bcrypt" in self._t()

    def test_T40_rate_limiting_section(self):
        assert "Rate Limit" in self._t() or "rate limit" in self._t().lower()

    def test_T41_hsts_mentioned(self):
        assert "HSTS" in self._t() or "Strict-Transport" in self._t()

    def test_T42_csp_mentioned(self):
        assert "Content-Security-Policy" in self._t() or "CSP" in self._t()

    def test_T43_rls_mentioned(self):
        assert "RLS" in self._t() or "Row Level" in self._t()

    def test_T44_kill_switch_section(self):
        assert "Kill Switch" in self._t() or "/halt" in self._t()

    def test_T45_incident_response(self):
        assert "Incident" in self._t() or "incident" in self._t().lower()

    def test_T46_aes_or_encryption(self):
        assert "AES" in self._t() or "encrypt" in self._t().lower()

    def test_T47_webhook_security(self):
        assert "webhook" in self._t().lower() or "Webhook" in self._t()

    def test_T48_checklist_present(self):
        t = self._t()
        assert "Checklist" in t or "checklist" in t.lower() or "- [ ]" in t


# ===========================================================================
# T49-T64: MQL5_INSTALLATION.md
# ===========================================================================


class TestMQL5Installation:
    DOC = "MQL5_INSTALLATION.md"

    def _t(self):
        return read_doc(self.DOC, root=True)

    def test_T49_file_exists(self):
        assert (ROOT_DIR / self.DOC).exists()

    def test_T50_min_size(self):
        assert len(self._t()) >= 2000

    def test_T51_risk_warning(self):
        t = self._t()
        assert "ریسک" in t or "risk" in t.lower() or "تضمین" in t or "⚠" in t

    def test_T52_demo_first(self):
        assert "Demo" in self._t() or "demo" in self._t()

    def test_T53_30_days(self):
        assert "۳۰" in self._t() or "30" in self._t()

    def test_T54_prerequisites(self):
        assert "پیش‌نیاز" in self._t() or "Prerequisite" in self._t()

    def test_T55_download_section(self):
        assert "دانلود" in self._t() or "Download" in self._t()

    def test_T56_experts_folder(self):
        assert "Experts" in self._t() or "Expert" in self._t()

    def test_T57_webrequest(self):
        assert "WebRequest" in self._t() or "webrequest" in self._t().lower()

    def test_T58_parameters(self):
        assert "پارامتر" in self._t() or "Inputs" in self._t() or "Parameter" in self._t()

    def test_T59_license_key_param(self):
        assert "LicenseKey" in self._t() or "License Key" in self._t()

    def test_T60_drawdown_param(self):
        assert "MaxDrawdown" in self._t() or "Drawdown" in self._t()

    def test_T61_troubleshooting(self):
        assert "عیب‌یابی" in self._t() or "Troubleshooting" in self._t()

    def test_T62_ex5_not_mq5(self):
        assert ".ex5" in self._t()

    def test_T63_update_section(self):
        t = self._t()
        assert "Update" in t or "update" in t.lower() or "به‌روز" in t

    def test_T64_heartbeat(self):
        assert "Heartbeat" in self._t() or "heartbeat" in self._t().lower()


# ===========================================================================
# T65-T80: SAAS_RELEASE_GUIDE.md
# ===========================================================================


class TestSAASReleaseGuide:
    DOC = "SAAS_RELEASE_GUIDE.md"

    def _t(self):
        return read_doc(self.DOC)

    def test_T65_file_exists(self):
        assert (DOCS_DIR / self.DOC).exists()

    def test_T66_min_size(self):
        assert len(self._t()) >= 2000

    def test_T67_plans_table(self):
        t = self._t()
        assert "Trial" in t and "Basic" in t and "Pro" in t and "VIP" in t

    def test_T68_pricing(self):
        assert "$" in self._t() or "USD" in self._t() or "قیمت" in self._t()

    def test_T69_onboarding(self):
        assert "Onboarding" in self._t() or "ثبت‌نام" in self._t()

    def test_T70_artifact_table(self):
        assert "Artifact" in self._t() or "artifact" in self._t()

    def test_T71_ex5_in_artifact(self):
        assert ".ex5" in self._t()

    def test_T72_source_not_delivered(self):
        t = self._t()
        assert ".mq5" in t or "source" in t.lower()
        assert "محرمانه" in t or "not delivered" in t.lower() or "داده نمی" in t

    def test_T73_download_token(self):
        assert "Token" in self._t() or "token" in self._t().lower()

    def test_T74_checksum(self):
        assert "checksum" in self._t().lower() or "SHA" in self._t()

    def test_T75_lifecycle(self):
        assert "Lifecycle" in self._t() or "lifecycle" in self._t() or "چرخه" in self._t()

    def test_T76_subscription_states(self):
        t = self._t()
        assert "ACTIVE" in t or "active" in t
        assert "SUSPENDED" in t or "suspended" in t or "تعلیق" in t

    def test_T77_offboarding(self):
        assert "Offboard" in self._t() or "Cancel" in self._t() or "cancel" in self._t()

    def test_T78_faq(self):
        assert "FAQ" in self._t() or "سؤال" in self._t()

    def test_T79_refund(self):
        assert (
            "refund" in self._t().lower()
            or "money-back" in self._t().lower()
            or "بازگشت" in self._t()
        )

    def test_T80_payment_method(self):
        assert "Stripe" in self._t() or "ZarinPal" in self._t() or "پرداخت" in self._t()


# ===========================================================================
# T81-T96: ADMIN_MANUAL.md
# ===========================================================================


class TestAdminManual:
    DOC = "ADMIN_MANUAL.md"

    def _t(self):
        return read_doc(self.DOC)

    def test_T81_file_exists(self):
        assert (DOCS_DIR / self.DOC).exists()

    def test_T82_min_size(self):
        assert len(self._t()) >= 3000

    def test_T83_telegram_commands(self):
        t = self._t()
        assert "/halt" in t and "/resume" in t and "/status" in t

    def test_T84_grafana(self):
        assert "Grafana" in self._t() or "grafana" in self._t()

    def test_T85_prometheus(self):
        assert "Prometheus" in self._t() or "prometheus" in self._t()

    def test_T86_trace_api(self):
        assert "trace" in self._t().lower() or "Trace" in self._t()

    def test_T87_license_management(self):
        assert "License" in self._t() or "license" in self._t()

    def test_T88_billing_management(self):
        assert "Billing" in self._t() or "billing" in self._t()

    def test_T89_kill_switch(self):
        assert "Kill Switch" in self._t() or "kill" in self._t().lower()

    def test_T90_user_management(self):
        assert "User" in self._t() or "user" in self._t()

    def test_T91_runbooks(self):
        assert "Runbook" in self._t() or "runbook" in self._t() or "RB-" in self._t()

    def test_T92_license_failure_runbook(self):
        assert (
            "License Failure" in self._t()
            or "license_failure" in self._t()
            or "RB-001" in self._t()
        )

    def test_T93_heartbeat_runbook(self):
        assert "Heartbeat" in self._t() or "heartbeat" in self._t() or "RB-002" in self._t()

    def test_T94_kill_switch_runbook(self):
        t = self._t()
        assert "RB-003" in t or ("خودکار" in t and "Kill" in t)

    def test_T95_reconciliation_runbook(self):
        assert "Reconciliation" in self._t() or "RB-005" in self._t()

    def test_T96_export_csv(self):
        assert "csv" in self._t().lower() or "CSV" in self._t()


# ===========================================================================
# Cross-doc consistency
# ===========================================================================


class TestCrossDocConsistency:
    def test_readme_links_docs(self):
        readme = read_doc("README.md", root=True)
        for doc in ["DEPLOYMENT.md", "SECURITY.md", "MQL5_INSTALLATION.md"]:
            assert doc in readme, f"README باید link داشته باشد به {doc}"

    def test_all_docs_have_date(self):
        for doc, is_root in [
            ("README.md", True),
            ("DEPLOYMENT.md", True),
            ("SECURITY.md", True),
            ("MQL5_INSTALLATION.md", True),
            ("SAAS_RELEASE_GUIDE.md", False),
            ("ADMIN_MANUAL.md", False),
        ]:
            text = read_doc(doc, root=is_root)
            assert "2026" in text, f"{doc} باید تاریخ داشته باشد"

    def test_all_trading_docs_have_risk_warning(self):
        for doc, is_root in [
            ("README.md", True),
            ("DEPLOYMENT.md", True),
            ("MQL5_INSTALLATION.md", True),
        ]:
            text = read_doc(doc, root=is_root)
            has = "ریسک" in text or "risk" in text.lower() or "تضمین" in text or "⚠" in text
            assert has, f"{doc} باید هشدار ریسک داشته باشد"

    def test_no_real_credentials(self):
        patterns = [
            r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
            r"sk_live_[A-Za-z0-9]+",
        ]
        for doc, is_root in [("README.md", True), ("SECURITY.md", True), ("DEPLOYMENT.md", True)]:
            text = read_doc(doc, root=is_root)
            for p in patterns:
                matches = re.findall(p, text)
                assert not matches, f"{doc} contains potential real secret"

    def test_kill_switch_in_multiple_docs(self):
        count = 0
        for doc, is_root in [
            ("README.md", True),
            ("DEPLOYMENT.md", True),
            ("SECURITY.md", True),
            ("MQL5_INSTALLATION.md", True),
            ("ADMIN_MANUAL.md", False),
        ]:
            text = read_doc(doc, root=is_root)
            if "Kill Switch" in text or "/halt" in text:
                count += 1
        assert count >= 3

    def test_ex5_in_multiple_docs(self):
        count = sum(
            1
            for doc, is_root in [
                ("README.md", True),
                ("MQL5_INSTALLATION.md", True),
                ("SAAS_RELEASE_GUIDE.md", False),
            ]
            if ".ex5" in read_doc(doc, root=is_root)
        )
        assert count >= 2

    def test_all_required_docs_exist(self):
        for doc in ["SAAS_RELEASE_GUIDE.md", "ADMIN_MANUAL.md"]:
            assert (DOCS_DIR / doc).exists()
        for doc in ["README.md", "DEPLOYMENT.md", "SECURITY.md", "MQL5_INSTALLATION.md"]:
            assert (ROOT_DIR / doc).exists()
