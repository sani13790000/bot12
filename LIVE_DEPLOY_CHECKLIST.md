# Galaxy Vast AI Trading Platform — LIVE Deployment Checklist
## Phase Q Final — Production Ready

---

## ✅ Pre-Deploy Checks

### 1. Environment Variables
```env
# Required
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your_service_role_key
SECRET_KEY=your_32char_secret
MT5_ACCOUNT=your_mt5_account_number
MT5_PASSWORD=your_mt5_password
MT5_SERVER=your_mt5_broker_server

# Telegram
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ADMIN_IDS=comma_separated_admin_ids  # e.g. 123456,789012

# Security
ADMIN_API_KEY=your_admin_api_key
LICENSE_SECRET=your_license_secret

# ML / Storage
MODEL_DIR=/data/models  # must be a persistent volume
ANALYTICS_PAGE_SIZE=100
SMC_MAX_CANDLES=1000
BACKTEST_MAX_WORKERS=4
BACKTEST_TIMEOUT=300
METRICS_MIN_TRADES_FOR_SHARPE=30
SECURITY_MODEL_RETRAIN_INTERVAL_S=3600
```

---

### 2. Database Migrations
```bash
# Verify migration order before running
ls -la supabase/migrations/ | sort  # must be sequential, no gaps

# Check for conflicts (must return 0 duplicate prefixes)
ls supabase/migrations/*.sql | sed 's/.*\/[0-9T_]*_\([0-9]*\)_.*/\1/' | sort | uniq -d

# Run migrations
supabase db push

# Verify key tables exist
supabase db remote commit  # or check in Supabase dashboard
```

---

### 3. Docker Build & Start
```bash
docker-compose build
docker-compose up -d

# Verify all services healthy
docker-compose ps
# Expected: api, telegram-bot, redis, supabase (all Up)
```

---

### 4. Unit Tests
```bash
pytest tests/ -m unit -v --tb=short
# Expected: all unit tests pass

pytest tests/ -m phase_q -v
# Expected: all 22 Phase Q tests pass
```

---

### 5. Integration Tests (DEMO MT5)
```bash
# Run integration tests with DEMO account
# These require MT5 terminal running with DEMO account
MT5_GATEWAY_MODE=DEMO pytest tests/ -m integration -v --tb=short

# Verify full pipeline:
pytest tests/test_e2e_demo_phase_h.py -v
# Expected: pipeline signal -> context enricher -> voting -> risk gate

# Verify analytics:
pytest tests/test_phase_q_final.py::TestAnalyticsSummaryQ -v
```

---

### 6. API Health Check
```bash
# Cold start
curl http://localhost:8000/health
# Expected: {"status": "ok"}

# Ready check (all 5 components)
curl http://localhost:8000/health/ready
# Expected: {"status": "ready", "checks": {"redis": "ok", "database": "ok", "mt5": "connected", "license": "ok", "ml_model": "loaded"}}

# Trade history endpoint (BUG-Q1 fix)
curl http://localhost:8000/trades/history?limit=10&offset=0
# Expected: {"trades": [...], "total": N, "limit": 10, "offset": 0}

# Analytics summary (BUG-Q2 fix)
curl http://localhost:8000/analytics/summary
# Expected: {"data_source": "live_db", "total_trades": N, ...}
```

---

### 7. Telegram Bot Verification
```bash
# Send commands in Telegram:
/start       # bot responds
/status      # system status
/positions   # open positions (must not crash with KeyError)
/help        # command list
```

---

### 8. Switch to LIVE Account
```bash
# In .env:
MT5_GATEWAY_MODE=LIVE

# In MQL5 EA:
# DemoMode = false  (set in MT5 Inputs panel)
# ServerURL = http://your_vps_ip:8000

# Restart API
docker-compose restart api

# Verify kill switch armed
curl -X POST http://localhost:8000/admin/kill \
  -H 'X-Admin-Key: your_admin_api_key' \
  -d '{"reason": "pre-live safety check"}'
# Then resume:
curl -X POST http://localhost:8000/admin/resume \
  -H 'X-Admin-Key: your_admin_api_key' \
  -d '{"reason": "LIVE deployment authorized"}'
```

---

### 9. Final Pre-Flight
- [ ] All environment variables set
- [ ] TELEGRAM_ADMIN_IDS configured (not just TELEGRAM_CHAT_ID)
- [ ] Migrations run in order, no gaps, no conflicts
- [ ] Unit tests pass (`pytest -m unit`)
- [ ] Integration tests pass with DEMO MT5 (`pytest -m integration`)
- [ ] Phase Q tests pass (`pytest -m phase_q`)
- [ ] `/health/ready` returns all 5 components OK
- [ ] `/trades/history` returns 200 (not 404)
- [ ] `/analytics/summary` returns `data_source: live_db`
- [ ] Telegram `/positions` does not crash
- [ ] MODEL_DIR is a persistent volume (not /tmp)
- [ ] Kill switch tested: activate + resume
- [ ] DemoMode=false set in MT5 EA Inputs
