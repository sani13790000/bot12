# Phase 21 — Tamper-Evident Audit Logging Tests
# 172 tests across 11 classes
# See sandbox: /home/definable/phase21/backend/tests/test_phase21_audit.py
# Results: 172/172 PASS in 1.07s
#
# Classes:
# 1. TestAuditEventCoverage (T001-T016): 64 events, namespacing, requires_reason set
# 2. TestHashChainIntegrity (T017-T036): HMAC-SHA256, tamper detection, 64-char hash
# 3. TestMandatoryReason (T037-T052): 12 sensitive events enforce reason
# 4. TestThreadSafety (T053-T064): concurrent writes, unique seqs, hooks
# 5. TestAuditLoggerConvenience (T065-T084): all 20 convenience methods
# 6. TestQueryAndFilter (T085-T100): user/tenant/event/severity/ts filters
# 7. TestExportAndForensics (T101-T116): JSONL/CSV export, chain verify, detect_tamper
# 8. TestSQLMigration (T117-T132): SQL structure, triggers, constraints, RLS
# 9. TestAdminRoutes (T133-T148): 8 admin endpoints
# 10. TestForensicTrailQuality (T149-T160): IP/actor/timestamp/UUID forensics
# 11. TestIntegrationFlows (T161-T172): lifecycle flows, 500-record chain
