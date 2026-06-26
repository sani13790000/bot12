backend/license/engine.py
Phase 6 — License, Subscription & Device Enforcement

GAPs FIXED:
  P6-FIX-1: raw license key never stored — only HMAC-SHA256 hash
  P6-FIX-2: heartbeat with nonce/timestamp/HMAC signed response
  P6-FIX-3: anti-replay — nonce single-use with 5 min TTL
  P6-FIX-4: device fingerprint server-side
  P6-FIX-5: subscription tier fully fail-closed
  P6-FIX-6: signed API response
  P6-FIX-7: device limit atomic check+increment
  P6-FIX-8: license lifecycle: PENDING->ACTIVE->SUSPENDED->EXPIRED->REVOKED
  P6-FIX-9: admin-only revoke with audit log
