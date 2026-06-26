MT5TradingEA_Complete.mq5 Phase 7

v3.20:
- OnInit: Validate() fail → INIT_FAILED (هیچ fallback نیست)
- OnTimer: NeedsHeartbeat() → Heartbeat() → fail → halt
- OnDeinit: DeactivateDevice() در clean shutdown
- Feature gate: FEATURE_AUTO_TRADE چک قبل از trading
- g_license_valid و g_emergency_stop از heartbeat update می‌شوند