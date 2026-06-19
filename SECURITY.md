# Security Policy

## Reporting a Vulnerability

Do NOT open a public GitHub issue for security vulnerabilities.

Email: security@galaxyvast.com

We will respond within 48 hours.

---

## Security Architecture

### Authentication
- JWT in HttpOnly + Secure + SameSite=Strict cookie
- Refresh token rotation with jti revocation in DB
- bcrypt password hashing (12 rounds)
- Account lockout: 5 failed attempts → 15 min lockout
- No user enumeration: same error for bad user/pass

### Authorization
- Role-based: `user` | `admin`
- Every endpoint requires `get_current_user` dependency
- Admin endpoints require `require_admin` dependency
- JWT revocation checked on every request

### Transport
- HTTPS enforced in production (Secure cookie flag)
- HSTS: max-age=63072000
- All WebSocket connections require valid JWT

### Input Validation
- Symbol/timeframe whitelist on all trading endpoints
- Pydantic v2 validation on all request bodies
- SQL injection patterns blocked at middleware level
- XSS patterns blocked at middleware level
- Command injection patterns blocked at middleware level
- Path traversal blocked at middleware level
- Request body size limit: 1 MB

### Headers
- Content-Security-Policy
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: geolocation=(), microphone=(), camera=()

### Rate Limiting
- /auth/login: 5 req/min per IP
- /auth/register: 3 req/min per IP
- All endpoints: 60 req/min per IP
- Redis-backed with in-memory fallback

### Database
- Row Level Security (RLS) on all tables
- service_role key only — never anon key in backend
- Parameterized queries only (Supabase client)
- No raw SQL from user input

### MQL5 EA
- Bearer token auth on all API calls
- SSRF protection: private IP ranges blocked
- Symbol whitelist enforced
- Token configured as input (not hardcoded)

### Secrets Management
- All secrets from environment variables
- No hardcoded secrets in code
- .env file in .gitignore
- Required secrets validated at startup (sys.exit if missing)

---

## Dependency Security

```bash
# Check for vulnerabilities:
pip audit

# Update dependencies:
pip-compile --upgrade requirements.in
```

## Security Checklist (before every deployment)

- [ ] `.env` not committed to git
- [ ] All REQUIRED env vars set
- [ ] ENVIRONMENT=production
- [ ] ALLOWED_ORIGINS does not contain `*`
- [ ] JWT_SECRET_KEY is 64+ chars random hex
- [ ] Supabase RLS enabled on all tables
- [ ] HTTPS configured (reverse proxy / load balancer)
- [ ] Docker resource limits set
- [ ] Telegram ADMIN_IDS configured
- [ ] MQL5_API_TOKEN set and configured in MT5
