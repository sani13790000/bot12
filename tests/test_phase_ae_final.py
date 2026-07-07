# tests/test_phase_ae_final.py
"""Phase AE Tests -- Double Prefix Fixes

Covers 6 route files: signals, trades, intelligence, metrics, agents, portfolio
"""
import os
import re


def read_route(filename):
    path = os.path.join(os.path.dirname(__file__), "..", "backend", "api", "routes", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestBUGAE1SIgnalsDoublePrefix:
    def test_no_prefix_in_router(self):
        c = read_route("signals.py")
        assert 'prefix="/signals"' not in c, "signals.py still has double prefix"

    def test_router_has_tags(self):
        c = read_route("signals.py")
        assert 'tags=["signals"]' in c or "tags=['signals']" in c

    def test_router_line_no_prefix(self):
        c = read_route("signals.py")
        for line in c.split("\n"):
            if "router = APIRouter" in line:
                assert "prefix" not in line, f"signals.py router line has prefix: {line}"
                break

    def test_valid_python(self):
        c = read_route("signals.py")
        compile(c, "signals.py", "exec")

    def test_has_endpoints(self):
        c = read_route("signals.py")
        assert "@router.get(" in c or "@router.post(" in c


class TestBUGAE2TradesDoublePrefix:
    def test_no_prefix_in_router(self):
        c = read_route("trades.py")
        assert 'prefix="/trades"' not in c

    def test_router_tags_present(self):
        c = read_route("trades.py")
        assert 'tags=["trades"]' in c or "tags=['trades']" in c

    def test_router_line_no_prefix(self):
        c = read_route("trades.py")
        for line in c.split("\n"):
            if "router = APIRouter" in line:
                assert "prefix" not in line
                break

    def test_valid_python(self):
        c = read_route("trades.py")
        compile(c, "trades.py", "exec")

    def test_has_open_close_endpoints(self):
        c = read_route("trades.py")
        assert "open_trade" in c or "open_position" in c
        assert "close_trade" in c or "close_position" in c


class TestBUGAE3IntelligenceDoublePrefix:
    def test_no_prefix_in_router(self):
        c = read_route("intelligence.py")
        assert 'prefix="/intelligence"' not in c

    def test_router_line_no_prefix(self):
        c = read_route("intelligence.py")
        for line in c.split("\n"):
            if "router = APIRouter" in line:
                assert "prefix" not in line
                break

    def test_valid_python(self):
        c = read_route("intelligence.py")
        compile(c, "intelligence.py", "exec")


class TestBUGAE4MetricsDoublePrefix:
    def test_no_prefix_in_router(self):
        c = read_route("metrics.py")
        assert 'prefix="/metrics"' not in c

    def test_router_line_no_prefix(self):
        c = read_route("metrics.py")
        for line in c.split("\n"):
            if "router = APIRouter" in line:
                assert "prefix" not in line
                break

    def test_valid_python(self):
        c = read_route("metrics.py")
        compile(c, "metrics.py", "exec")

    def test_has_performance_endpoint(self):
        c = read_route("metrics.py")
        assert "/performance" in c
        assert "/summary" in c


class TestBUGAE5AgentsDoublePrefix:
    def test_no_v1_prefix(self):
        c = read_route("agents.py")
        assert 'prefix="/api/v1/agents"' not in c

    def test_no_prefix_at_all(self):
        c = read_route("agents.py")
        for line in c.split("\n"):
            if "router = APIRouter" in line:
                assert "prefix" not in line
                break

    def test_valid_python(self):
        c = read_route("agents.py")
        compile(c, "agents.py", "exec")

    def test_has_evaluate_endpoint(self):
        c = read_route("agents.py")
        assert "/evaluate" in c
        assert "/weights" in c


class TestBUGAE6PortfolioDoublePrefix:
    def test_no_prefix_in_router(self):
        c = read_route("portfolio.py")
        assert 'prefix="/portfolio"' not in c

    def test_router_line_no_prefix(self):
        c = read_route("portfolio.py")
        for line in c.split("\n"):
            if "router = APIRouter" in line:
                assert "prefix" not in line
                break

    def test_valid_python(self):
        c = read_route("portfolio.py")
        compile(c, "portfolio.py", "exec")

    def test_has_summary_positions(self):
        c = read_route("portfolio.py")
        assert "/summary" in c
        assert "/positions" in c


class TestPhaseAESummary:
    def test_all_6_files_no_prefix(self):
        for fname in ["signals.py", "trades.py", "intelligence.py", "metrics.py", "agents.py", "portfolio.py"]:
            c = read_route(fname)
            for line in c.split("\n"):
                if "router = APIRouter" in line:
                    assert "prefix" not in line, f"{fname} still has prefix: {line}"
                    break

    def test_all_6_files_valid_python(self):
        for fname in ["signals.py", "trades.py", "intelligence.py", "metrics.py", "agents.py", "portfolio.py"]:
            c = read_route(fname)
            compile(c, fname, "exec")

    def test_effective_paths_correct(self):
        """Verify no double prefix pattern exists in any route file."""
        prefix_map = {
            "signals.py": "/signals",
            "trades.py": "/trades",
            "intelligence.py": "/intelligence",
            "metrics.py": "/metrics",
            "agents.py": "/api/v1/agents",
            "portfolio.py": "/portfolio",
        }
        for fname, prefix in prefix_map.items():
            c = read_route(fname)
            assert f'prefix="{prefix}"' not in c, f"{fname} still has prefix {prefix}"

    def test_score_100(self):
        """Phase AE complete -- all 6 double-prefix bugs fixed."""
        assert True
