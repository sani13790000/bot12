# Galaxy Vast AI Trading Platform — Deployment Guide

## Pre-flight Checklist

### 1. Environment Variables (required)
```bash
cp .env.example .env
# Fill in all values:
# SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
# JWT_SECRET_KEY (min 32 chars)
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# LICENSE_KEY, LICENSE_SALT
# ENVIRONMENT=production
# ALLOWED_ORIGINS=https://yourdomain.com
```

### 2. Database Migrations
Run migrations in order in Supabase SQL editor:
```
supabase/migrations/20260612155742_001_initial_schema.sql
supabase/migrations/20260618_002_partitioning.sql
... (003 through 013)
supabase/migrations/014_users_table.sql
```

### 3. MQL5 EA Setup
1. Open `mql5/Config.mqh`
2. Set `API_BASE_URL` to your server URL (e.g. `https://api.yourdomain.com`)
3. Set `API_TOKEN` to a valid JWT token from `/api/v1/auth/login`
4. Compile and attach EA to chart

### 4. Docker Deploy
```bash
python3 startup_check.py
docker compose up -d --build
docker compose ps  # all services should be healthy
```

### 5. Verify
```bash
curl https://api.yourdomain.com/health
# Expected: {"status": "healthy", "database": {"connected": true}}

curl https://api.yourdomain.com/docs
# Expected: Swagger UI with 22+ endpoints
```

### 6. Resource Limits (per service)
| Service | Memory Limit | CPU Limit |
|---|---|---|
| redis | 600MB | 0.5 core |
| api | 3GB | 2.0 core |
| telegram_bot | 512MB | 0.5 core |
| dashboard | 1GB | 1.0 core |
| frontend | 256MB | 0.5 core |

### 7. Rollback
If migration needs rollback:
```bash
# Run down migration in Supabase SQL editor:
supabase/migrations/down/014_users_table_down.sql
```

## Security Checklist
- [ ] `ENVIRONMENT=production` in .env
- [ ] `ALLOWED_ORIGINS` set to exact domain (no wildcard)
- [ ] `JWT_SECRET_KEY` at least 32 random chars
- [ ] `LICENSE_SALT` set to random value
- [ ] `API_TOKEN` set in MQL5 Config.mqh
- [ ] HTTPS enabled on server
- [ ] Redis not exposed to public internet
- [ ] Supabase RLS enabled on all tables
