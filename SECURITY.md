# 🔒 SECURITY.md — Galaxy Vast AI Trading Platform

> **نسخه:** 3.0 | **آخرین به‌روزرسانی:** 2026-06-26

---

## گزارش Vulnerability

**هرگز** برای vulnerabilities امنیتی GitHub Issue باز نکنید.

📧 **Email:** security@galaxyvast.com
⏱️ **پاسخ:** حداکثر ۴۸ ساعت

| سطح | مثال | SLA رفع |
|-----|------|--------|
| Critical | RCE، auth bypass | ۲۴ ساعت |
| High | IDOR، privilege escalation | ۷۲ ساعت |
| Medium | XSS، rate limit bypass | ۱۴ روز |
| Low | معلومات غیرحساس leak | ۳۰ روز |

---

## معماری امنیتی — ۱۰ لایه

### لایه ۱: Transport
```
nginx → TLS 1.2+
  HSTS: max-age=63072000; includeSubDomains; preload
  SSL: TLSv1.2 TLSv1.3 only
```

### لایه ۲: HTTP Headers
```http
Content-Security-Policy: default-src 'self'; ...
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
```

### لایه ۳: Authentication
```
bcrypt (12 rounds) + JWT (15 min expiry)
Refresh Token: single-use + family revocation
Account lockout: 5 failed → 15 min
No user enumeration
```

### لایه ۴: Authorization (RBAC)
```
Roles: user | support | write_admin | admin | super_admin
Object-Level Auth: assert_owns(resource, current_user)
Admin bypass: فقط admin و super_admin
```

### لایه ۵: Secrets Management
```
SecretStore: AES-256-GCM + PBKDF2 (260000 iter)
Database: license_key → HMAC-SHA256
Database: sensitive_field → enc:v1:BASE64
Password: bcrypt — هرگز decrypt نمی‌شود
```

### لایه ۶: Input Validation
```
Middleware: SQL injection + XSS + Command + Path traversal
Pydantic v2: strict validation همه requests
Payload size: max 1MB
```

### لایه ۷: Rate Limiting
| Endpoint | محدودیت |
|----------|--------|
| `/auth/login` | 5 req/min per IP |
| `/api/v1/*` | 30 req/min per user |
| `/billing/webhook` | 60 req/min per IP |

### لایه ۸: Webhook Security
```
1. HMAC-SHA256 signature verify
2. timestamp tolerance ±5 min
3. event_id idempotency check
4. payload size cap 1MB
```

### لایه ۹: Log Redaction
```
JWT: eyJ... → [REDACTED:JWT]
password=xxx → [REDACTED:PASSWORD]
Bearer xxx → [REDACTED:BEARER]
```

### لایه ۱۰: Database RLS
```sql
ALTER TABLE licenses ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_sees_own" ON licenses
    FOR SELECT USING (auth.uid() = user_id);
```

---

## Kill Switch

```bash
# Telegram (فوری)
/halt

# API
curl -X POST https://api.yourdomain.com/api/v1/risk/halt \
     -H "Authorization: Bearer ADMIN_JWT"

# Resume
/resume
```

---

## Security Checklist قبل از Production

- [ ] همه CHANGE_ME در `.env` پر شده
- [ ] `ENVIRONMENT=production`
- [ ] `ALLOWED_ORIGINS` فقط exact domains (no wildcard)
- [ ] `JWT_SECRET_KEY` حداقل 64 hex char
- [ ] `SECRETS_MASTER_KEY` حداقل 64 hex char
- [ ] SSL/TLS فعال (Let's Encrypt)
- [ ] nginx rate limiting فعال
- [ ] Supabase RLS روی همه جداول
- [ ] `/openapi.json` و `/docs` در production غیرفعال
- [ ] `server_tokens off` در nginx
- [ ] Docker containers با non-root user
- [ ] `no-new-privileges` در docker-compose.prod.yml
- [ ] `mql5/` در .dockerignore

---

## Incident Response

```bash
# شناسایی
curl https://api.yourdomain.com/admin/health/deep \
     -H "Authorization: Bearer ADMIN_JWT"

# مهار — اگر trading
/halt

# بررسی
curl "https://api.yourdomain.com/admin/trace?level=CRITICAL&limit=100" \
     -H "Authorization: Bearer ADMIN_JWT" > incident.json

# Export CSV
curl "https://api.yourdomain.com/admin/trace/export.csv" \
     -H "Authorization: Bearer ADMIN_JWT" > incident.csv

# بازیابی
bash scripts/backup.sh production
docker compose -f docker-compose.prod.yml up -d
/resume
```
