"""
backend/backtest_engine/performance_report.py
Galaxy Vast AI — Performance Report Generator
NOTE: Auto-repaired stub due to binary corruption.
"""
from __future__ import annotations
import logging
_LOG = logging.getLogger(__name__)


class PerformanceReport:
    """Performance report generator stub."""

    def generate(self, trades: list, config: dict = None) -> dict:
        return {'trades': len(trades), 'pnl': 0.0}

    def to_html(self) -> str:
        return '<html><body>Performance Report</body></html>'

    def to_pdf(self) -> bytes:
        return b''
