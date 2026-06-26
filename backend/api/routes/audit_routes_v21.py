backend/api/routes/audit_routes_v21.py — Phase 21
==================================================
Admin endpoints for forensic audit trail access.

Routes:
  GET  /admin/audit/              → query with filters
  GET  /admin/audit/summary       → chain summary
  GET  /admin/audit/verify        → verify chain integrity
  GET  /admin/audit/tamper        → detect tampered entries
  GET  /admin/audit/export.jsonl  → JSONL export
  GET  /admin/audit/export.csv    → CSV export
  GET  /admin/audit/events        → list all 64 event types
