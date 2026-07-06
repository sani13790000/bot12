"""
test_phase_ae_final.py — Phase AE: Systemic Double-Prefix Fix

BUG-AE1: signals.py — prefix='/signals' removed → /signals/* correct
BUG-AE2: trades.py  — prefix='/trades' removed  → /trades/* correct
BUG-AE3: intelligence.py — prefix removed        → /intelligence/* correct

Note verified: metrics.py, agents.py, portfolio.py already had no prefix ✅
"""
from __future__ import annotations
import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
ROUTES = ROOT / "backend" / "api" / "routes"
MAIN   = ROOT / "backend" / "api" / "main.py"


# ─────────────────────────────────────────────────────────────────────
class TestBugAE1SignalsDoublePrefix:
    def test_signals_file_exists(self):
        assert (ROUTES / "signals.py").exists()

    def test_signals_not_placeholder(self):
        content = (ROUTES / "signals.py").read_text()
        assert content.strip() not in ('"SIGNALS_PLACEHOLDER"', "'SIGNALS_PLACEHOLDER'")
        assert len(content) > 500

    def test_signals_no_prefix_in_router(self):
        content = (ROUTES / "signals.py").read_text()
        assert not re.search(r'router\s*=\s*APIRouter\(prefix=', content), \
            "signals.py still has prefix= in APIRouter — double prefix bug"

    def test_signals_has_tags(self):
        content = (ROUTES / "signals.py").read_text()
        assert 'tags=["signals"]' in content or "tags=['signals']" in content

    def test_signals_valid_python(self):
        content = (ROUTES / "signals.py").read_text()
        ast.parse(content)

    def test_signals_has_endpoints(self):
        content = (ROUTES / "signals.py").read_text()
        assert "@router.get" in content or "@router.post" in content


class TestBugAE2TradesDoublePrefix:
    def test_trades_file_exists(self):
        assert (ROUTES / "trades.py").exists()

    def test_trades_not_placeholder(self):
        content = (ROUTES / "trades.py").read_text()
        assert content.strip() not in ('"TRADES_PLACEHOLDER"', "'TRADES_PLACEHOLDER'")
        assert len(content) > 500

    def test_trades_no_prefix_in_router(self):
        content = (ROUTES / "trades.py").read_text()
        assert not re.search(r'router\s*=\s*APIRouter\(prefix=', content), \
            "trades.py still has prefix= in APIRouter — double prefix bug"

    def test_trades_has_tags(self):
        content = (ROUTES / "trades.py").read_text()
        assert 'tags=["trades"]' in content or "tags=['trades']" in content

    def test_trades_valid_python(self):
        content = (ROUTES / "trades.py").read_text()
        ast.parse(content)

    def test_trades_has_endpoints(self):
        content = (ROUTES / "trades.py").read_text()
        assert "@router.get" in content or "@router.post" in content


class TestBugAE3IntelligenceDoublePrefix:
    def test_intelligence_file_exists(self):
        assert (ROUTES / "intelligence.py").exists()

    def test_intelligence_not_placeholder(self):
        content = (ROUTES / "intelligence.py").read_text()
        assert content.strip() not in ('"INTELLIGENCE_PLACEHOLDER"', "'INTELLIGENCE_PLACEHOLDER'")
        assert len(content) > 500

    def test_intelligence_no_prefix_in_router(self):
        content = (ROUTES / "intelligence.py").read_text()
        assert not re.search(r'router\s*=\s*APIRouter\(prefix=', content), \
            "intelligence.py still has prefix= in APIRouter — double prefix bug"

    def test_intelligence_valid_python(self):
        content = (ROUTES / "intelligence.py").read_text()
        ast.parse(content)

    def test_intelligence_has_endpoints(self):
        content = (ROUTES / "intelligence.py").read_text()
        assert "@router." in content


class TestPhaseAEAlreadyFixed:
    """Verify metrics, agents, portfolio were already fixed."""

    def test_metrics_no_prefix(self):
        content = (ROUTES / "metrics.py").read_text()
        assert not re.search(r'router\s*=\s*APIRouter\(prefix=', content)

    def test_agents_no_prefix(self):
        content = (ROUTES / "agents.py").read_text()
        assert not re.search(r'router\s*=\s*APIRouter\(prefix=', content)

    def test_portfolio_no_prefix(self):
        content = (ROUTES / "portfolio.py").read_text()
        assert not re.search(r'router\s*=\s*APIRouter\(prefix=', content)

    def test_billing_no_prefix(self):
        content = (ROUTES / "billing.py").read_text()
        assert not re.search(r'router\s*=\s*APIRouter\(prefix=', content)

    def test_backtest_no_prefix(self):
        content = (ROUTES / "backtest.py").read_text()
        assert not re.search(r'router\s*=\s*APIRouter\(prefix=', content)

    def test_admin_no_prefix(self):
        content = (ROUTES / "admin.py").read_text()
        assert not re.search(r'router\s*=\s*APIRouter\(prefix=', content)


class TestPhaseAESummary:
    def test_no_double_prefix_in_any_route(self):
        """All route files must not have prefix= in their APIRouter definition."""
        route_files = list(ROUTES.glob("*.py"))
        violators = []
        for f in route_files:
            content = f.read_text()
            if re.search(r'router\s*=\s*APIRouter\(prefix=', content):
                violators.append(f.name)
        assert not violators, f"Double prefix still in: {violators}"

    def test_all_route_files_valid_python(self):
        for f in ROUTES.glob("*.py"):
            try:
                ast.parse(f.read_text())
            except SyntaxError as e:
                assert False, f"{f.name}: SyntaxError: {e}"

    def test_main_has_signals_router(self):
        content = MAIN.read_text()
        assert "signals" in content

    def test_main_has_trades_router(self):
        content = MAIN.read_text()
        assert "trades" in content

    def test_main_has_intelligence_router(self):
        content = MAIN.read_text()
        assert "intelligence" in content
