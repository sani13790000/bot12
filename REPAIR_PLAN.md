# REPAIR_PLAN.md — Galaxy Vast AI Trading Platform (bot12)
> Generated: 2026-07-01 | Analyst: Senior Python Architect
> Repository: `sani13790000/bot12` | Python: 3.11+

---

## EXECUTIVE SUMMARY

| Category | Count | Severity |
|---|---|---|
| Missing `TradingSession` enum | 1 file | CRITICAL |
| Double base64-encoded files | 12 files | CRITICAL |
| Single-decoded files with SyntaxErrors | 32 files | CRITICAL |
| Missing package structures | 2 cases | HIGH |
| Missing source files | 3 files | HIGH |
| Missing `State` in circuit_breaker | 1 file | MEDIUM |
| Typos in source code | 2 instances | MEDIUM |

**Root Cause:** Files were committed in their GitHub-API base64 representation
(double-encoded). Python sees binary/garbage text instead of valid source code.

---

## PRIORITY 1 — CRITICAL (blocks ALL tests)

### P1-A: Missing `TradingSession` in `backend/core/enums.py`

- **File:** `backend/core/enums.py`
- **Root Cause:** `TradingSession` enum class was never committed to the file
- **Error:** `ImportError: cannot import name 'TradingSession' from 'backend.core.enums'`
- **Fix Strategy:** Add `TradingSession(str, Enum)` with values: LONDON, NEW_YORK, TOKYO, SYDNEY, OVERLAP, UNKNOWN
- **Dependencies affected:** `backend/core/__init__.py`, `backend/analysis/price_action_engine.py`,
  `backend/risk/correlation_filter.py`, and 30+ test files

```python
class TradingSession(str, Enum):
    LONDON   = "london"
    NEW_YORK = "new_york"
    TOKYO    = "tokyo"
    SYDNEY   = "sydney"
    OVERLAP  = "overlap"
    UNKNOWN  = "unknown"
```

---

### P1-B: Double Base64-Encoded Source Files

Files committed with source already encoded, then GitHub adds another layer of b64.

**Fix Strategy:** Apply `base64.b64decode` twice, then strip U+FFFD replacement chars.

| File | Status After Double-Decode |
|---|---|
| `backend/execution/__init__.py` | Valid Python |
| `backend/core/auth_hardening.py` | Valid Python |
| `backend/intelligence/learning_service.py` | Valid Python |
| `backend/api/routes/signals.py` | Valid Python |
| `backend/middleware/security_headers.py` | Valid after cleanup |
| `backend/services/scheduler.py` | Valid after minor fix |
| `backend/api/routes/dashboard.py` | Valid after line 76 fix |
| `backend/tests/test_fix8_coverage.py` | Valid after fix |
| `backend/tests/test_phase22_incident.py` | Valid after fix |
| `backend/tests/test_phase35_final_acceptance.py` | Valid after indent fix |
| `backend/core/customer_lifecycle.py` | Valid after fix |
| `backend/core/final_acceptance.py` | Valid after fix |

---

### P1-C: Single-Decoded Files with SyntaxErrors

#### Group A: Missing closing parenthesis
| File | Line | Fix |
|---|---|---|
| `backend/agents/voting_engine.py` | 178 | Add `)` to close `results.append(` |
| `backend/execution/order_state_machine.py` | 285 | Add missing `)` |

#### Group B: Line 1 syntax error (encoding artifact)
- `backend/ai_prediction/model_manager.py`
- `backend/core/cache.py`
- `backend/core/security_rules_loader.py`
- `backend/middleware/security.py`
- `backend/observability/metrics.py`
- `backend/telegram/bot.py`
- `backend/core/interfaces.py`
- `backend/execution/semi_auto.py`
- `backend/self_learning/retraining_service.py`
- `backend/security_reporting/report_exporter.py`
- `backend/security_reporting/security_report_service.py`
- `backend/api/routes/trades.py`

#### Group C: Mid-file SyntaxErrors
| File | Line | Error Type |
|---|---|---|
| `backend/core/config_v11.py` | 46 | Construct error |
| `backend/core/secret_store.py` | 161 | Unclosed bracket |
| `backend/ai_prediction/xgboost_trainer.py` | 132 | Format string |
| `backend/backtest_engine/performance_report.py` | 114 | Construct error |
| `backend/backtest_engine/risk_report.py` | 271 | Construct error |
| `backend/tests/test_phase17_deployment.py` | 22 | Unterminated string |
| `backend/tests/test_phase21_audit.py` | 8 | Non-printable U+0008 char |
| `backend/telegram/handlers/alerts.py` | 100 | Syntax error |
| `backend/telegram/handlers/control.py` | 52 | Syntax error |
| `backend/telegram/handlers/intelligence.py` | 51 | Syntax error |
| `backend/telegram/handlers/reports.py` | 106 | Syntax error |
| `backend/telegram/handlers/semi_auto.py` | 71 | Syntax error |
| `backend/telegram/routers/admin.py` | 69 | Syntax error |

#### Group D: Plain-text decode
- `backend/license/engine.py`
- `backend/license/dependency.py`
- `backend/license/routes.py`

---

## PRIORITY 2 — HIGH

### P2-A: `backend.risk` not a package
- **Root Cause:** Cascade failure from missing TradingSession
- **Fix:** Resolves automatically after P1-A

### P2-B: Missing Source Files
| Missing File | Referenced By | Fix |
|---|---|---|
| `backend/services/trade_service_patch.py` | `test_phase_u.py` | Create stub |
| `\home\definable\phase4\risk\daily_limits.py` | `test_phase4_final.py` | Fix hardcoded path |
| `\home\definable\phase4\core\exceptions.py` | `test_phase4_risk_hardening.py` | Fix hardcoded path |

### P2-C: Missing `State` in `backend/circuit_breaker.py`
- Add `class State(str, Enum): CLOSED / OPEN / HALF_OPEN`

---

## PRIORITY 3 — MEDIUM

### P3-A: Typo `VoteSignal.NUUTRAL` → `VoteSignal.NEUTRAL`
### P3-B: Invalid format spec `:.0` → `:.0f` in voting_engine.py
### P3-C: Wrong import in `test_analytics.py`: use `backend.analytics.metrics_engine`
### P3-D: Missing `ALERT_RULES_TEMPLATE` in `backend/cicd_v15.py`

---

## ORDERED FIX SEQUENCE

```
Step 1: backend/core/enums.py        Add TradingSession        [unblocks 30+ files]
Step 2: Double b64 files             Decode twice              [12 files]
Step 3: Single b64 syntax fixes      Fix each error            [32 files]
Step 4: backend/circuit_breaker.py   Add State enum            [HIGH]
Step 5: Path fixes in phase4 tests   Use relative paths        [HIGH]
Step 6: Stub trade_service_patch.py  Create empty module       [HIGH]
Step 7: Typo fixes                   NUUTRAL, :.0f etc         [MEDIUM]
Step 8: pytest.ini asyncio settings  Remove deprecation warns  [LOW]
```

## EXPECTED RECOVERY

| Phase | Result |
|---|---|
| Before any fix | 52 collection errors, 0 tests run |
| After Step 1 | ~30 files collectible |
| After Steps 2-3 | ~50 files collectible |
| After Steps 4-7 | 0 collection errors, 1747 tests run |
