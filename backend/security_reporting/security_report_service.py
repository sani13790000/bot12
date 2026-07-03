"""
backend/security_reporting/security_report_service.py
Phase-6 -- Security Reporting System
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SecurityReportService:
    """Generate and manage security reports."""

    def __init__(self) -> None:
        self._reports: list[dict] = []

    def generate_report(self, scan_results: dict) -> dict:
        """Generate a structured security report from scan results."""
        report = {
            "id": len(self._reports) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity_summary": self._summarize_severity(scan_results),
            "findings": scan_results.get("findings", []),
            "recommendations": self._generate_recommendations(scan_results),
            "compliance_status": self._check_compliance(scan_results),
        }
        self._reports.append(report)
        logger.info("Generated security report #%d", report["id"])
        return report

    def _summarize_severity(self, results: dict) -> dict:
        findings = results.get("findings", [])
        summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in findings:
            sev = f.get("severity", "info").lower()
            summary[sev] = summary.get(sev, 0) + 1
        return summary

    def _generate_recommendations(self, results: dict) -> list[str]:
        recs = []
        findings = results.get("findings", [])
        critical = [f for f in findings if f.get("severity") == "CRITICAL"]
        if critical:
            recs.append(f"Address {len(critical)} critical findings immediately")
        return recs

    def _check_compliance(self, results: dict) -> dict:
        findings = results.get("findings", [])
        critical_count = sum(1 for f in findings if f.get("severity") == "CRITICAL")
        return {
            "passed": critical_count == 0,
            "critical_issues": critical_count,
            "standards": ["OWASP", "ISO27001"],
        }

    def get_reports(self) -> list[dict]:
        return list(self._reports)

    def get_report(self, report_id: int) -> Optional[dict]:
        for r in self._reports:
            if r["id"] == report_id:
                return r
        return None


security_report_service = SecurityReportService()
