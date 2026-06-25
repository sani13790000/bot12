# See backend/tests/test_stress_scenarios.py
# Full stress test suite — 42 tests, 9 market scenarios, 42/42 PASS
# Run: OTEL_SDK_DISABLED=true pytest backend/tests/test_stress_scenarios.py -v
#
# Scenarios:
#   1. Flash Crash
#   2. High Volatility
#   3. API Failure
#   4. Network Failure
#   5. Database Failure
#   6. Corrupted Data
#   7. Missing Candle
#   8. Delayed Tick
#   9. Duplicate Tick
#   + Cascade Failure (worst case)
#
# Bugs found and fixed during stress testing:
#   STRESS-1: AgentVote/AgentResult/AgentStatus missing from base_agent.py
#   STRESS-2: NameError _ORDER_TTL_HOURS in OSM.start()
#   STRESS-3: ContextualLogger positional args in news_filter.py
#   STRESS-4: ContextualLogger positional args in correlation_filter.py
#   STRESS-5: VolatilityFilter.check() was async but callers expected sync
#   STRESS-6: BaseAgent missing enabled=True attr required by VotingEngine
#   STRESS-7: ContextualLogger positional args in order_state_machine.py
#   STRESS-8: VolatilityFilter needs >=10 ATR samples before spike detection
# ———————————————————————————————————————————————————
# Full test file available in project docs/stress_test_suite.py
# ———————————————————————————————————————————————————
