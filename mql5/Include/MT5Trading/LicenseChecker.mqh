LicenseChecker.mqh Phase 7

P7-FIX-1: license key در GET URL → POST JSON body
P7-FIX-2: nonce در هر heartbeat (anti-replay)
P7-FIX-3: HMAC signature verify روی server response
P7-FIX-4: Verify() online fail → fail-closed (نه offline fallback)
P7-FIX-5: license.dat با HMAC MAC (integrity check)
P7-FIX-6: DeactivateDevice پیاده‌سازی کامل
P7-FIX-7: NeedsHeartbeat() — OnTimer integration
P7-FIX-8: device ID از AccountLogin+Number+Server+Path (server-side)
P7-FIX-9: DENY_REASON enum برای logging دقیق