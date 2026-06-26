"""backend/tests/test_phase3_execution_safety.py
PHASE 3 — Real Trading Execution Safety
=======================================
Tests:
  - Double-trading prevention (idempotency layers 1+2)
  - Order timeout (execution pipeline timeout)
  - OSM transition whitelist (bypass prevention)
  - Slippage recording
  - Requote → failure recovery
  - Partial fill → OSM PARTIAL state
  - MT5 timeout retcode handling
  - Reconciliation: pre-submit duplicate position check
  - Journal: every event recorded
  - Signal inflight guard
  - OSM fll lifecycle with audit trail
  - OSM watchdog detects hung orders
  - FailureRecovery dead-letter after max retries
  - Reconciliation run_once
  - Concurrent double-submit race condition
"