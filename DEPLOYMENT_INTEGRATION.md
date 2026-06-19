# Phase 11-13 Integration Guide

## main.py lifespan additions

Add these blocks to `backend/api/main.py`:

### 1. Import block (at top, in try/except)
```python
try:
    from backend.agents.security_ai_agent import security_ai_agent
    HAS_SECURITY_AI = True
except ImportError as exc:
    logger.warning("Security AI not available: %s", exc)
    HAS_SECURITY_AI = False

try:
    from backend.security_reporting.security_score_engine import security_score_engine
    HAS_SCORE_ENGINE = True
except ImportError as exc:
    logger.warning("Score engine not available: %s", exc)
    HAS_SCORE_ENGINE = False

try:
    from backend.security_reporting.report_scheduler import report_scheduler
    HAS_REPORT_SCHEDULER = True
except ImportError as exc:
    logger.warning("Report scheduler not available: %s", exc)
    HAS_REPORT_SCHEDULER = False
```

### 2. Startup tasks (in lifespan, before yield)
```python
    if HAS_SECURITY_AI:
        startup_tasks.append(
            asyncio.create_task(security_ai_agent.start(), name="security_ai_agent")
        )
        logger.info("Security AI Agent started.")

    if HAS_SCORE_ENGINE:
        startup_tasks.append(
            asyncio.create_task(security_score_engine.start(), name="security_score_engine")
        )
        logger.info("Security Score Engine started.")

    if HAS_REPORT_SCHEDULER:
        startup_tasks.append(
            asyncio.create_task(report_scheduler.start(), name="report_scheduler")
        )
        logger.info("Report Scheduler started.")
```

### 3. Shutdown (in lifespan, after yield)
```python
    if HAS_SECURITY_AI:       security_ai_agent.stop()
    if HAS_SCORE_ENGINE:      security_score_engine.stop()
    if HAS_REPORT_SCHEDULER:  report_scheduler.stop()
```

## New API Endpoints (all in analytics router)

| Endpoint | Description |
|---|---|
| GET /analytics/security/metrics | Phase-11 dashboard metrics (O(1) + parallel DB) |
| GET /analytics/security/score/history | 24h score chart (288 points) |
| GET /analytics/security/score/dimensions | 8-dimension breakdown |
| GET /analytics/security/anomalies | Paginated anomaly feed |
| GET /analytics/security/blocked-ips | Active IP blocks |
| GET /analytics/security/threat-intel/{ip} | Threat intel lookup |
| GET /analytics/security/report?days=30 | Generate report |
| GET /analytics/security/report/{id}/html | HTML report |
| GET /analytics/security/report/{id}/json | JSON report |

## Migration

Run in Supabase Dashboard:
```
supabase/migrations/20260619_019_phase11_13_tables.sql
```

## Environment Variables

```env
SECURITY_SCORE_INTERVAL_S=300    # 5 minutes
SECURITY_SCORE_ALERT=65          # Telegram alert threshold
SECURITY_SCORE_BREAKER=40        # Circuit breaker threshold
SECURITY_REPORTS_DIR=/reports/security
SECURITY_REPORT_INTERVAL_HOURS=24
SECURITY_MONTHLY_REPORT=true
```

## Performance Guarantees (Phase-13)

| Operation | Latency | Method |
|---|---|---|
| `security_score_engine.current_sync()` | < 1 µs | Memory read |
| `security_ai_agent.analyze_event()` | < 10 ms | Executor |
| IsolationForest inference | ~0.1 ms | numpy float32[12] |
| Training | Background | run_in_executor |
| DB writes | Fire-and-forget | asyncio.create_task |
| Self-heal | Fire-and-forget | asyncio.create_task |
| Dashboard metrics DB | < 3 s | asyncio.wait_for |
