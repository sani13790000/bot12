"""
backend/security_reporting/report_scheduler.py
Phase-7 — Automatic Report Scheduler
Monthly + manual trigger + Telegram notify
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ── Config from env ──────────────────────────────────────────────────────────
_INTERVAL_H     = int(os.getenv("SECURITY_REPORT_INTERVAL_HOURS", "24"))
_PERIOD_H       = int(os.getenv("SECURITY_REPORT_PERIOD_HOURS",   "168"))   # 7 days default
_MONTHLY_DAY    = int(os.getenv("SECURITY_REPORT_MONTHLY_DAY",    "1"))     # 1st of month
_TG_ENABLED     = os.getenv("SECURITY_REPORT_TELEGRAM", "true").lower() in ("1", "true", "yes")
_MONTHLY_REPORT = os.getenv("SECURITY_MONTHLY_REPORT",  "true").lower() in ("1", "true", "yes")


class ReportScheduler:
    """
    Background scheduler that:
      * Runs a periodic report every _INTERVAL_H hours.
      * On the 1st of every month, generates a monthly report (30-day window).
      * Allows manual trigger via .trigger() — called from API.
      * Sends Telegram alerts to admins after each report.
      * Tracks history of last 50 runs.
    """

    def __init__(self) -> None:
        self._running:      bool               = False
        self._task:         Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._last_run:     Optional[datetime]  = None
        self._last_monthly: Optional[datetime]  = None
        self._report_count: int                = 0
        self._error_count:  int                = 0
        self._history:      List[Dict[str, Any]] = []
        self._lock:         asyncio.Lock        = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background scheduler loop."""
        self._running = True
        log.info(
            "ReportScheduler started | interval=%dh | monthly=%s | period=%dh",
            _INTERVAL_H, _MONTHLY_REPORT, _PERIOD_H,
        )
        while self._running:
            try:
                await self._decide_and_run()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._error_count += 1
                log.error("ReportScheduler error: %s", exc, exc_info=True)

            interval_s = _INTERVAL_H * 3_600
            slept = 0
            while slept < interval_s and self._running:
                await asyncio.sleep(min(30, interval_s - slept))
                slept += 30

    def stop(self) -> None:
        self._running = False
        log.info("ReportScheduler stopping...")

    async def trigger(
        self,
        period_hours: int = _PERIOD_H,
        label: str = "manual",
    ) -> Dict[str, Any]:
        """
        Manually trigger a report — called from Phase-8 API endpoint.
        Returns report metadata.
        """
        async with self._lock:
            return await self._run_once(period_hours=period_hours, label=label)

    def stats(self) -> Dict[str, Any]:
        return {
            "running":        self._running,
            "last_run":       self._last_run.isoformat()     if self._last_run     else None,
            "last_monthly":   self._last_monthly.isoformat() if self._last_monthly else None,
            "report_count":   self._report_count,
            "error_count":    self._error_count,
            "interval_hours": _INTERVAL_H,
            "period_hours":   _PERIOD_H,
            "history":        self._history[-10:],
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _decide_and_run(self) -> None:
        now = datetime.now(timezone.utc)
        if _MONTHLY_REPORT and now.day == _MONTHLY_DAY:
            if self._last_monthly is None or self._last_monthly.month != now.month:
                log.info("Running MONTHLY security report (30-day window)...")
                async with self._lock:
                    await self._run_once(period_hours=720, label="monthly")
                self._last_monthly = now
                return
        async with self._lock:
            await self._run_once(period_hours=_PERIOD_H, label="scheduled")

    async def _run_once(
        self,
        period_hours: int = _PERIOD_H,
        label: str = "scheduled",
    ) -> Dict[str, Any]:
        start = datetime.now(timezone.utc)
        report_id: Optional[str] = None
        exports: Dict[str, Optional[str]] = {}
        error: Optional[str] = None

        try:
            from backend.security_reporting.security_report_service import security_report_service
            from backend.security_reporting.report_exporter import report_exporter

            report    = await security_report_service.generate_report(period_hours=period_hours)
            report_id = report.report_id

            exports["json"] = report_exporter.export_json(report)
            exports["html"] = report_exporter.export_html(report)
            try:
                exports["pdf"] = report_exporter.export_pdf(report)
            except Exception as pdf_err:
                log.debug("PDF export skipped: %s", pdf_err)
                exports["pdf"] = None

            self._report_count += 1
            self._last_run = start

            if _TG_ENABLED:
                await self._send_telegram(report, label)

            log.info("Report [%s] done | id=%s | json=%s", label, report_id, exports.get("json"))

        except Exception as exc:
            self._error_count += 1
            error = str(exc)
            log.error("Report [%s] failed: %s", label, exc, exc_info=True)

        duration_s = (datetime.now(timezone.utc) - start).total_seconds()
        run_record: Dict[str, Any] = {
            "report_id":    report_id,
            "label":        label,
            "period_hours": period_hours,
            "started_at":   start.isoformat(),
            "duration_s":   round(duration_s, 2),
            "exports":      exports,
            "error":        error,
        }
        self._history.append(run_record)
        if len(self._history) > 50:
            self._history.pop(0)
        return run_record

    async def _send_telegram(self, report: Any, label: str) -> None:
        try:
            from backend.telegram.alerts import send_security_report_alert
            await send_security_report_alert(report, label)
        except Exception as exc:
            log.debug("Telegram report alert failed: %s", exc)


report_scheduler = ReportScheduler()
