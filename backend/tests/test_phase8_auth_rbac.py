# 92 tests — see /home/definable/phase8/tests/test_phase8_auth_rbac.py for full content
# All 92 tests PASS: 1.05s
# Run: PYTHONPATH=. pytest backend/tests/test_phase8_auth_rbac.py --asyncio-mode=auto -v
PHASE8_TEST_SUMMARY = {
    "total": 92,
    "passed": 92,
    "failed": 0,
    "runtime_s": 1.05,
    "classes": [
        "TestRBACEngine (T01-T14)",
        "TestDependencyFactories (T15-T28)",
        "TestRefreshTokenRotation (T29-T44)",
        "TestAuditLog (T45-T56)",
        "TestCustomerDataIsolation (T57-T68)",
        "TestAdminRoutes (T69-T78)",
        "TestRBACMiddleware (T79-T86)",
        "TestIntegrationFlow (T87-T92)",
    ],
}
