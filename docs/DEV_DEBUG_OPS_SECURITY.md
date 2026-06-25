# بخش‌های ۱۷ تا ۲۵ — Galaxy Vast AI Trading Platform

---

# 17. Development Guide

> **برای چه کسی است؟** توسعه‌دهنده‌ای که می‌خواهد Agent، Gate، یا Route جدید اضافه کند.

## ۱۷.۱ راه‌اندازی محیط توسعه

```bash
# Clone و Setup
git clone https://github.com/sani13790000/bot12.git
cd bot12

# محیط مجازی Python
python -m venv .venv
source .venv/bin/activate         # Linux/Mac
# .venv\Scripts\activate          # Windows

# نصب وابستگی‌ها + dev tools
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov httpx ruff black isort mypy

# فایل ENV توسعه
cp .env.example .env
# ویرایش .env با مقادیر development

# اجرا در حالت توسعه
ENVIRONMENT=development uvicorn backend.api.main:app --reload --port 8000
```

## ۱۷.۲ استانداردهای کد

### قوانین اجباری

| قانون | ابزار | دستور |
|-------|-------|--------|
| Formatting | black | `black backend/` |
| Import sort | isort | `isort backend/` |
| Linting | ruff | `ruff check backend/` |
| Type check | mypy | `mypy backend/core/ backend/risk/ backend/execution/` |
| Security scan | bandit | `bandit -r backend/ -ll` |
| Tests | pytest | `pytest backend/tests/ -q` |

### یک‌جا همه چک‌ها

```bash
black backend/ && isort backend/ && ruff check backend/ && mypy backend/core/ && pytest backend/tests/ -q
```

### الگوی کد استاندارد

```python
# backend/risk/my_new_gate.py
"""backend/risk/my_new_gate.py — توضیح یک‌خطی."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..core.exceptions import AppError
from ..core.interfaces import IRiskGate
from ..core.logger import get_logger

logger = get_logger("risk.my_new_gate")


@dataclass
class MyGateConfig:
    """تنظیمات Gate جدید."""
    max_value: float = 1.0
    enabled:   bool  = True


class MyNewGate(IRiskGate):
    """Gate جدید با پیاده‌سازی IRiskGate."""

    def __init__(self, config: Optional[MyGateConfig] = None) -> None:
        self._config = config or MyGateConfig()
        self._lock: Optional[asyncio.Lock] = None
        logger.info("MyNewGate initialized", max_value=self._config.max_value)

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def check(self, **kwargs: Any) -> Dict[str, Any]:
        """بررسی اصلی Gate — باید پیاده‌سازی شود."""
        if not self._config.enabled:
            return {"approved": True, "reason": "gate_disabled"}

        value = kwargs.get("value", 0.0)
        if value > self._config.max_value:
            logger.warning("Gate blocked", value=value, max=self._config.max_value)
            return {"approved": False, "block_reason": f"value_{value}_exceeds_{self._config.max_value}"}

        return {"approved": True}
```

## ۱۷.۳ افزودن Agent جدید

### گام ۱ — ساخت Agent

```python
# backend/agents/my_agent.py
from __future__ import annotations
from typing import Any, Dict
from .base_agent import BaseAgent, VoteResult, VoteBias
from ..core.logger import get_logger

logger = get_logger("agents.my_agent")


class MyAgent(BaseAgent):
    """Agent جدید — توضیح هدف."""

    WEIGHT: float = 1.0
    HAS_VETO: bool = False

    async def analyze(self, context: Dict[str, Any]) -> VoteResult:
        symbol    = context.get("symbol", "")
        direction = context.get("direction", "BUY")
        confidence = 0.75
        bias       = VoteBias.BUY
        return VoteResult(
            agent_name  = self.__class__.__name__,
            bias        = bias,
            confidence  = confidence,
            weight      = self.WEIGHT,
            reasoning   = f"Analysis for {symbol}: confidence={confidence}",
            metadata    = {"symbol": symbol, "direction": direction},
        )
```

### گام ۲ — ثبت در VotingEngine

```python
# backend/agents/voting_engine.py — در __init__ اضافه کن:
from .my_agent import MyAgent

self._agents: List[BaseAgent] = [
    ...,
    MyAgent(),
]
```

### گام ۳ — تست Agent

```python
# backend/tests/test_my_agent.py
import pytest
from backend.agents.my_agent import MyAgent

@pytest.mark.asyncio
async def test_my_agent_buy():
    agent = MyAgent()
    result = await agent.analyze({"symbol": "EURUSD", "direction": "BUY"})
    assert result.confidence >= 0.0
    assert result.bias in ("BUY", "SELL", "NEUTRAL")
```

## ۱۷.۴ افزودن Route جدید

```python
# backend/api/routes/my_feature.py
from __future__ import annotations
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from ...core.deps import get_current_user
from ...core.logger import get_logger

logger = get_logger("api.my_feature")
router = APIRouter(prefix="/my-feature", tags=["My Feature"])


class MyRequest(BaseModel):
    value: float
    symbol: str


class MyResponse(BaseModel):
    result: str
    processed: bool


@router.post("", response_model=MyResponse, status_code=status.HTTP_200_OK)
async def my_endpoint(
    req:          MyRequest,
    current_user: dict = Depends(get_current_user),
) -> MyResponse:
    """توضیح endpoint."""
    logger.info("my_endpoint called", user=current_user.get("id"), symbol=req.symbol)
    return MyResponse(result="ok", processed=True)
```

```python
# backend/api/main.py — اضافه کردن router:
from .routes.my_feature import router as my_feature_router
app.include_router(my_feature_router, prefix=settings.API_PREFIX)
```

## ۱۷.۵ Git Workflow

```bash
# شروع feature جدید
git checkout develop
git pull origin develop
git checkout -b feature/my-new-feature

# توسعه و commit
git add backend/agents/my_agent.py backend/tests/test_my_agent.py
git commit -m "feat(agents): add MyAgent with confidence scoring"

# Push و PR
git push origin feature/my-new-feature
```

### Commit Message Convention

```
feat(module):     قابلیت جدید
fix(module):      رفع bug
refactor(module): بازنویسی بدون تغییر رفتار
test(module):     اضافه کردن یا ویرایش تست
docs(module):     تغییر مستندات
perf(module):     بهبود عملکرد
chore:            کارهای نگهداری
```

---

# 18. Debugging Guide

## ۱۸.۱ فعال‌سازی Debug Mode

```bash
# .env
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

# اجرا با reload
ENVIRONMENT=development LOG_LEVEL=DEBUG uvicorn backend.api.main:app --reload --port 8000
```

## ۱۸.۲ خواندن لاگ‌ها

### محل لاگ‌ها

| محیط | محل | فرمت |
|------|-----|-------|
| Development | stdout (terminal) | human-readable |
| Production Docker | `docker logs galaxyvast-api` | JSON |
| فایل | `/var/log/galaxyvast/app.log` | JSON |

### دستورات خواندن لاگ

```bash
# لاگ‌های real-time
docker logs -f galaxyvast-api-1

# فقط خطاها
docker logs galaxyvast-api-1 2>&1 | grep '"level":"ERROR"'

# لاگ یک signal خاص
docker logs galaxyvast-api-1 2>&1 | grep '"signal_id":"SIG-001"'

# لاگ‌های ۱ ساعت اخیر
docker logs --since 1h galaxyvast-api-1
```

### فرمت JSON لاگ

```json
{
  "ts":        "2026-06-25T16:45:00.123Z",
  "level":     "ERROR",
  "logger":    "execution.service",
  "msg":       "Submission failed",
  "signal_id": "SIG-001",
  "symbol":    "EURUSD",
  "error":     "MT5 connection timeout",
  "request_id":"req_abc123"
}
```

## ۱۸.۳ Debug یک Signal مشکل‌دار

```bash
# دریافت token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_pass"}' | jq -r '.access_token')

# ارسال signal test
curl -X POST http://localhost:8000/api/v1/signals/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol":         "EURUSD",
    "direction":      "BUY",
    "entry_price":    1.0850,
    "stop_loss":      1.0820,
    "take_profit":    1.0910,
    "balance":        10000,
    "stop_loss_pips": 30,
    "signal_id":      "DEBUG-001"
  }'
```

## ۱۸.۴ Debug با Python مستقیم

```python
# debug_signal.py
import asyncio, sys
sys.path.insert(0, ".")

async def debug():
    from backend.risk.risk_orchestrator import get_risk_orchestrator, RiskInput

    orch = await get_risk_orchestrator()
    inp = RiskInput(
        symbol="EURUSD", direction="BUY",
        balance=10000.0, stop_loss_pips=30.0,
        atr_pips=25.0, spread_pips=1.2, current_equity=9850.0,
    )
    result = await orch.assess(inp)
    print("APPROVED:", result.approved)
    print("BLOCK:",    result.block_reason)
    print("LOT SIZE:", result.lot_size)
    for gate, r in result.gate_results.items():
        print(f"  {gate}: {r}")

asyncio.run(debug())
```

```bash
ENVIRONMENT=development python debug_signal.py
```

## ۱۸.۵ رفع مشکل FastAPI Startup

```bash
# بررسی import errors
python -c "from backend.api.main import app; print('OK')"

# بررسی config validation
python -c "from backend.core.config import settings; print(settings.APP_NAME)"

# بررسی database
python -c "
import asyncio
from backend.database.connection import get_db
async def t():
    async for db in get_db():
        r = await db.execute('SELECT 1')
        print('DB OK:', r)
asyncio.run(t())
"
```

## ۱۸.۶ خطاهای رایج Startup و راه‌حل

| خطا | علت | راه‌حل |
|-----|-----|--------|
| `RuntimeError: no running event loop` | asyncio.Lock() در module level | فایل circuit_breaker.py lazy init دارد — update کنید |
| `ValidationError: SUPABASE_URL` | .env ناقص | مقدار SUPABASE_URL را در .env تنظیم کنید |
| `Connection refused redis:6379` | Redis down | `docker compose start redis` |
| `ModuleNotFoundError` | venv فعال نیست | `source .venv/bin/activate` |
| `Address already in use :8000` | Port اشغال | `lsof -i :8000 && kill -9 <PID>` |

---

# 19. Backup & Recovery Guide

> **قانون ۳-۲-۱:** ۳ نسخه backup، روی ۲ نوع media مختلف، ۱ نسخه خارج از site.

## ۱۹.۱ چه چیزی Backup بگیریم؟

| داده | اهمیت | فرکانس | محل |
|------|--------|---------|-----|
| Supabase Database | 🔴 Critical | هر ۶ ساعت | S3 + local |
| Redis State | 🟠 High | هر ۱ ساعت | local |
| ML Models | 🟠 High | بعد از هر retrain | S3 |
| فایل‌های `.env` | 🔴 Critical | بعد از هر تغییر | Vault encrypted |
| لاگ‌ها | 🟡 Medium | روزانه rotate | local + S3 |
| Grafana Dashboards | 🟡 Medium | هفتگی | Git |

## ۱۹.۲ اسکریپت Backup خودکار

```bash
#!/bin/bash
# scripts/backup.sh

set -euo pipefail

BACKUP_DIR="/var/backups/galaxyvast"
DATE=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$BACKUP_DIR/backup_$DATE.log"

mkdir -p "$BACKUP_DIR/db" "$BACKUP_DIR/redis" "$BACKUP_DIR/models"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }

log "=== Galaxy Vast Backup Started: $DATE ==="

# 1. Supabase Database Backup
log "Backing up Supabase..."
source /opt/galaxyvast/.env

pg_dump "$DATABASE_URL" \
  --format=custom \
  --compress=9 \
  --file="$BACKUP_DIR/db/supabase_$DATE.dump" 2>>"$LOG_FILE"

log "Database backup: $(du -sh $BACKUP_DIR/db/supabase_$DATE.dump | cut -f1)"

# 2. Redis Backup
log "Backing up Redis..."
docker exec galaxyvast-redis-1 \
  redis-cli -a "${REDIS_PASSWORD:-changeme_redis}" BGSAVE

sleep 5

docker cp galaxyvast-redis-1:/data/dump.rdb \
  "$BACKUP_DIR/redis/dump_$DATE.rdb" 2>>"$LOG_FILE"

log "Redis backup: $(du -sh $BACKUP_DIR/redis/dump_$DATE.rdb | cut -f1)"

# 3. ML Models Backup
log "Backing up ML models..."
if [ -d "/opt/galaxyvast/models" ]; then
  tar -czf "$BACKUP_DIR/models/models_$DATE.tar.gz" \
    -C /opt/galaxyvast models/ 2>>"$LOG_FILE"
  log "Models backup: $(du -sh $BACKUP_DIR/models/models_$DATE.tar.gz | cut -f1)"
fi

# 4. آپلود به S3 (اختیاری)
if command -v aws &>/dev/null && [ -n "${S3_BACKUP_BUCKET:-}" ]; then
  log "Uploading to S3..."
  aws s3 sync "$BACKUP_DIR" "s3://$S3_BACKUP_BUCKET/backups/" \
    --exclude "*.log" \
    --storage-class STANDARD_IA 2>>"$LOG_FILE"
  log "S3 upload complete"
fi

# 5. حذف Backup های قدیمی (نگه‌دار ۷ روز)
find "$BACKUP_DIR/db"     -name "*.dump"   -mtime +7  -delete
find "$BACKUP_DIR/redis"  -name "*.rdb"    -mtime +7  -delete
find "$BACKUP_DIR/models" -name "*.tar.gz" -mtime +30 -delete

log "=== Backup Complete: $DATE ==="
```

### فعال‌سازی Cron

```bash
sudo cp scripts/backup.sh /usr/local/bin/galaxyvast-backup
sudo chmod +x /usr/local/bin/galaxyvast-backup

# هر ۶ ساعت
sudo crontab -e
# اضافه کن:
0 */6 * * * /usr/local/bin/galaxyvast-backup >> /var/log/galaxyvast-backup.log 2>&1
```

## ۱۹.۳ بازیابی (Recovery)

### بازیابی Database

```bash
# گام ۱ — توقف سرویس API
docker compose stop api telegram_bot

# گام ۲ — بازیابی از آخرین dump
pg_restore \
  --dbname="$DATABASE_URL" \
  --clean \
  --if-exists \
  --format=custom \
  /var/backups/galaxyvast/db/supabase_20260625_060000.dump

# گام ۳ — راه‌اندازی مجدد
docker compose start api telegram_bot

# گام ۴ — تأیید
curl -s http://localhost:8000/health/deep | jq .database
```

### بازیابی Redis

```bash
docker compose stop redis
docker cp /var/backups/galaxyvast/redis/dump_20260625.rdb \
  galaxyvast-redis-1:/data/dump.rdb
docker exec galaxyvast-redis-1 chown redis:redis /data/dump.rdb
docker compose start redis
docker exec galaxyvast-redis-1 redis-cli -a "${REDIS_PASSWORD}" DBSIZE
```

### بازیابی ML Models

```bash
tar -xzf /var/backups/galaxyvast/models/models_20260625.tar.gz \
  -C /opt/galaxyvast/
docker compose restart api
curl -s http://localhost:8000/api/v1/agents/status \
  -H "Authorization: Bearer $TOKEN" | jq .ml_engine
```

---

# 20. Update & Upgrade Guide

## ۲۰.۱ انواع Update

| نوع | تعریف | مثال | روش |
|-----|--------|------|-----|
| **Patch** | Bug fix | `2.0.0 → 2.0.1` | Rolling restart |
| **Minor** | Feature | `2.0.x → 2.1.0` | Blue/Green |
| **Major** | Breaking | `2.x → 3.0.0` | Full migration |
| **Hotfix** | Critical fix | هر نسخه | Emergency restart |

## ۲۰.۲ روتین Update

```bash
# مرحله ۱ — آماده‌سازی
/usr/local/bin/galaxyvast-backup
curl -s http://localhost:8000/health/deep | jq .status

# مرحله ۲ — دریافت آپدیت
cd /opt/galaxyvast
git fetch origin main
git log HEAD..origin/main --oneline
git diff HEAD..origin/main -- supabase/migrations/

# مرحله ۳ — اعمال آپدیت
git pull origin main
supabase db push      # اگر migration جدید دارد
docker compose build api telegram_bot
docker compose up -d --no-deps api
docker compose up -d --no-deps telegram_bot

# مرحله ۴ — تأیید
sleep 30
curl -s http://localhost:8000/health/deep | jq .
```

## ۲۰.۳ Rollback

```bash
# برگشت به commit قبلی
cd /opt/galaxyvast
PREV_COMMIT=$(git log --oneline -2 | tail -1 | awk '{print $1}')
git checkout "$PREV_COMMIT"
docker compose build api
docker compose up -d --no-deps api
curl -s http://localhost:8000/health | jq .version
```

---

# 21. Troubleshooting Guide

## ۲۱.۱ جدول خطاهای رایج

| خطا | علت | راه‌حل |
|-----|-----|--------|
| `Connection refused :8000` | API down | `docker compose ps` + `docker compose up -d api` |
| `401 Unauthorized` | Token منقضی شده | `POST /auth/refresh` با refresh_token |
| `422 Unprocessable Entity` | فیلد اشتباه | بررسی `detail` در response |
| `503 Service Unavailable` | Circuit Breaker باز | `POST /risk/circuit-breaker/reset` |
| `MT5 connection failed` | MT5 terminal خاموش | راه‌اندازی MT5 + بررسی credentials |
| `Risk blocked: equity_protection` | Drawdown زیاد | صبر برای بازیابی یا reset دستی |
| `signal_inflight` | Signal تکراری | صبر ۱۰ ثانیه یا signal_id جدید |
| `Redis connection error` | Redis down | `docker compose restart redis` |
| `Database timeout` | Supabase overloaded | بررسی Supabase dashboard |
| `Model not loaded` | ML model آماده نیست | `POST /api/v1/agents/reload` |

## ۲۱.۲ Circuit Breaker باز است

```bash
# بررسی وضعیت
curl -s http://localhost:8000/api/v1/risk/circuit-breaker \
  -H "Authorization: Bearer $TOKEN" | jq .

# Reset
curl -X POST http://localhost:8000/api/v1/risk/circuit-breaker/reset \
  -H "Authorization: Bearer $TOKEN"
```

## ۲۱.۳ کدهای خطای MT5

| کد | توضیح | راه‌حل |
|----|--------|--------|
| 10004 | Requote | افزایش slippage |
| 10006 | Request rejected | بررسی margin |
| 10013 | Invalid request | بررسی lot size |
| 10018 | Market closed | بررسی trading hours |
| 10019 | Not enough money | کمبود margin |
| 10031 | Not connected | راه‌اندازی MT5 terminal |

## ۲۱.۴ توقف اضطراری

```bash
# روش ۱ — API
curl -X POST http://localhost:8000/api/v1/risk/halt \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"reason": "emergency"}'

# روش ۲ — Telegram: /halt

# روش ۳ — اگر API down است
docker compose stop api telegram_bot
```

---

# 22. FAQ

**Q: Galaxy Vast برای چه حساب‌هایی مناسب است?**
A: حداقل $5,000. برای حساب‌های $1,000 تا $1,000,000+ طراحی شده.

**Q: با کدام بروکرها کار می‌کند?**
A: هر بروکر با MT5. توصیه: IC Markets، Pepperstone، FP Markets.

**Q: آیا VPS لازم است?**
A: بله. VPS هم‌DC با بروکر برای latency پایین توصیه می‌شود.

**Q: تفاوت development و production چیست?**

| ویژگی | development | production |
|--------|-------------|------------|
| /docs Swagger | ✅ فعال | ❌ غیرفعال |
| Debug logs | ✅ verbose | فقط WARNING+ |
| CORS | بازتر | فقط ALLOWED_ORIGINS |
| Hot reload | ✅ | ❌ |

**Q: Circuit Breaker چه زمانی فعال می‌شود?**
A: پس از ۵ failure در ۶۰ ثانیه. بعد ۳۰ ثانیه HALF_OPEN می‌شود.

**Q: Self-Learning چه زمانی Retrain می‌کند?**
A: ۱) هر ۲۴ ساعت، ۲) accuracy < 55%، ۳) ۱۰۰ trade جدید.

**Q: آیا می‌توان بدون MT5 استفاده کرد?**
A: بله برای backtest و تحلیل. MT5 فقط برای live trading لازم است.

**Q: وقتی Redis down است چه اتفاقی می‌افتد?**
A: سیستم graceful degradation دارد. Rate limiting در حافظه، Sessions از JWT. Trading ادامه می‌دهد.

**Q: لاگ‌های Audit کجا ذخیره می‌شوند?**
A: جدول `audit_logs` در Supabase. Retention: ۹۰ روز.

**Q: چطور Agent جدید ایمن اضافه کنم?**
A: WEIGHT=0.5 و HAS_VETO=False. یک هفته shadow mode. تدریجی وزن را افزایش دهید.

---

# 23. Production Deployment Guide

## ۲۳.۱ مشخصات سرور توصیه‌شده

| اندازه | CPU | RAM | SSD | مناسب برای |
|--------|-----|-----|-----|-------------|
| **Small** | 2 vCPU | 4 GB | 40 GB | حساب < $10K |
| **Medium** | 4 vCPU | 8 GB | 80 GB | حساب $10K-$100K |
| **Large** | 8 vCPU | 16 GB | 160 GB | حساب > $100K |
| **Enterprise** | 16 vCPU | 32 GB | 320 GB | Multi-account |

**OS توصیه‌شده:** Ubuntu 22.04 LTS یا Debian 12

## ۲۳.۲ نصب اولیه سرور

```bash
apt update && apt upgrade -y
apt install -y git curl wget python3.11 python3.11-venv python3-pip \
  docker.io docker-compose-v2 nginx certbot python3-certbot-nginx \
  redis-tools postgresql-client ufw fail2ban

# Firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh && ufw allow 80/tcp && ufw allow 443/tcp
ufw enable

# کاربر غیر-root
useradd -m -s /bin/bash -G docker galaxyvast
```

## ۲۳.۳ نصب پروژه

```bash
git clone https://github.com/sani13790000/bot12.git /opt/galaxyvast
cd /opt/galaxyvast
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
vim .env    # ویرایش با مقادیر واقعی
```

## ۲۳.۴ تنظیم Nginx + SSL

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
    add_header X-Content-Type-Options    nosniff;
    add_header X-Frame-Options           DENY;

    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade     $http_upgrade;
        proxy_set_header   Connection  "upgrade";
        proxy_set_header   Host        $host;
        proxy_set_header   X-Real-IP   $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /health { proxy_pass http://127.0.0.1:8000; }
    location /       { proxy_pass http://127.0.0.1:3000; }
}
```

```bash
ln -s /etc/nginx/sites-available/galaxyvast /etc/nginx/sites-enabled/
certbot --nginx -d yourdomain.com
nginx -t && systemctl reload nginx
```

## ۲۳.۵ چک‌لیست استقرار Production

```
PRE-DEPLOYMENT:
[ ] Backup کامل گرفته شده
[ ] .env با مقادیر واقعی تنظیم شده
[ ] JWT_SECRET_KEY قوی است (>= 64 کاراکتر)
[ ] REDIS_PASSWORD تنظیم شده
[ ] ALLOWED_ORIGINS فقط domain واقعی است
[ ] DEBUG=false و ENVIRONMENT=production
[ ] Supabase RLS فعال است
[ ] Supabase migrations اعمال شده
[ ] MT5 terminal در حال اجرا است
[ ] Firewall فعال است

POST-DEPLOYMENT:
[ ] GET /health/live → {"status":"ok"}
[ ] GET /health/ready → {"status":"healthy"}
[ ] GET /health/deep → همه components healthy
[ ] POST /auth/login → token دریافت شد
[ ] POST /signals/execute با test signal → موفق
[ ] Telegram Bot پاسخ می‌دهد
[ ] لاگ‌ها بدون ERROR
[ ] Nginx SSL کار می‌کند
[ ] Backup اول production گرفته شده
```

---

# 24. Security Best Practices

## ۲۴.۱ مدیریت Secrets

```bash
# تولید secrets قوی
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"
echo "LICENSE_SECRET=$(openssl rand -hex 32)"
echo "LICENSE_SALT=$(openssl rand -hex 16)"
echo "REDIS_PASSWORD=$(openssl rand -base64 24)"
```

### چک‌لیست Secrets

```
[ ] JWT_SECRET_KEY: حداقل ۶۴ کاراکتر random
[ ] REDIS_PASSWORD: حداقل ۳۲ کاراکتر
[ ] .env در .gitignore است
[ ] Secrets در GitHub Actions Secrets ذخیره است
[ ] هر ۹۰ روز secrets rotate می‌شوند
```

## ۲۴.۲ تنظیمات امنیتی API

```bash
ALLOWED_ORIGINS=["https://yourdomain.com"]   # نه *
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

## ۲۴.۳ Supabase RLS

```sql
ALTER TABLE signals    ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades     ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_own_signals" ON signals
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "users_own_trades" ON trades
  FOR ALL USING (auth.uid() = user_id);
```

## ۲۴.۴ چک‌لیست امنیتی کامل

```
AUTHENTICATION:
[ ] bcrypt rounds=12 برای password hash
[ ] JWT با HS256 و secret >= 32 کاراکتر
[ ] JTI در هر token
[ ] Access token: 30 دقیقه
[ ] Refresh token: 7 روز

NETWORK:
[ ] HTTPS/TLS 1.2+ فقط
[ ] HSTS header فعال
[ ] CORS فقط به origin های شناخته‌شده
[ ] Firewall: فقط 80، 443، 22
[ ] Redis port از اینترنت بسته
[ ] API port مستقیم بسته (فقط از nginx)

DATA:
[ ] RLS در Supabase فعال
[ ] password_hash هرگز در API response نیست
[ ] SQL Injection: ORM/parameterized queries

MONITORING:
[ ] Login failures لاگ می‌شوند
[ ] Rate limit violations alert می‌فرستند
[ ] fail2ban برای SSH فعال
```

## ۲۴.۵ Fail2ban برای API

```ini
# /etc/fail2ban/filter.d/galaxyvast-api.conf
[Definition]
failregex = .*"client":"<HOST>".*"status":401.*
            .*"client":"<HOST>".*"status":429.*
```

```ini
# /etc/fail2ban/jail.d/galaxyvast.conf
[galaxyvast-api]
enabled  = true
filter   = galaxyvast-api
logpath  = /var/log/nginx/access.log
maxretry = 10
findtime = 300
bantime  = 3600
```

```bash
systemctl restart fail2ban
fail2ban-client status galaxyvast-api
```

---

# 25. Maintenance Guide

## ۲۵.۱ چک‌لیست روزانه

```bash
#!/bin/bash
# scripts/daily_check.sh

echo "=== Daily Health Check $(date) ==="

# وضعیت سرویس‌ها
docker compose ps

# Health API
curl -sf http://localhost:8000/health/deep | \
  jq '{status:.status, components:(.components|keys)}'

# Disk
df -h /opt/galaxyvast /var/backups

# Memory
free -h

# Docker Resources
docker stats --no-stream --format \
  "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# خطاهای اخیر
COUNT=$(docker logs --since 24h galaxyvast-api-1 2>&1 | \
  grep '"level":"ERROR"' | wc -l)
echo "$COUNT errors in last 24h"

# آخرین Backup
ls -la /var/backups/galaxyvast/db/ | tail -1
```

## ۲۵.۲ چک‌لیست هفتگی

```
[ ] بررسی لاگ‌های ERROR هفته گذشته
[ ] بررسی performance metrics در Grafana
[ ] بررسی ML model accuracy: GET /api/v1/agents/performance
[ ] تست backup recovery در staging
[ ] بررسی disk usage
[ ] بررسی security alerts
[ ] بررسی Supabase dashboard
[ ] Update بررسی: pip list --outdated
```

## ۲۵.۳ چک‌لیست ماهانه

```
[ ] Rotate secrets (JWT، Redis)
[ ] pip audit برای security vulnerabilities
[ ] docker images update
[ ] SSL certificate تاریخ انقضا: certbot renew --dry-run
[ ] Supabase plan بررسی
[ ] Performance review: P99 latency، error rate
[ ] Backup integrity test
[ ] ML model review و retrain اگر لازم
[ ] Code update: git pull + test + deploy
```

## ۲۵.۴ Monitoring Metrics کلیدی

| Panel | Metric | Alert Threshold |
|-------|--------|----------------|
| **API Error Rate** | `error_rate_5m` | > 1% |
| **P99 Latency** | `http_request_duration_p99` | > 2s |
| **Equity** | `account_equity` | < 90% initial |
| **Circuit Breaker** | `circuit_breaker_state` | = OPEN |
| **ML Accuracy** | `ml_model_accuracy_7d` | < 55% |
| **Redis Memory** | `redis_memory_used_mb` | > 400 |
| **Disk Usage** | `disk_usage_percent` | > 80% |

### Prometheus Queries نمونه

```promql
# Error rate در ۵ دقیقه
rate(http_requests_total{status=~"5.."}[5m]) /
rate(http_requests_total[5m]) * 100

# P99 latency
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Trade fill rate
rate(trades_filled_total[1h])

# Risk blocks per hour
rate(risk_blocks_total[1h])
```

## ۲۵.۵ Log Rotation

```bash
# /etc/logrotate.d/galaxyvast
/var/log/galaxyvast/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 galaxyvast galaxyvast
    postrotate
        docker compose -f /opt/galaxyvast/docker-compose.yml kill -s USR1 api
    endscript
}
```

## ۲۵.۶ Database Maintenance

```sql
-- هفتگی: VACUUM
VACUUM ANALYZE signals;
VACUUM ANALYZE trades;
VACUUM ANALYZE audit_logs;

-- پاکسازی audit_logs قدیمی (> 90 روز)
DELETE FROM audit_logs
WHERE created_at < NOW() - INTERVAL '90 days';

-- پاکسازی signals قدیمی
DELETE FROM signals
WHERE status IN ('executed', 'cancelled', 'expired')
  AND created_at < NOW() - INTERVAL '30 days';

-- بررسی table sizes
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

## ۲۵.۷ ML Model Health Check

```bash
# بررسی دستی model performance
curl -s http://localhost:8000/api/v1/agents/performance \
  -H "Authorization: Bearer $TOKEN" | jq '{
    accuracy:    .accuracy_7d,
    win_rate:    .win_rate_7d,
    total_trades:.total_trades_7d,
    last_retrain:.last_retrain_at
  }'

# Force retrain
curl -X POST http://localhost:8000/api/v1/agents/retrain \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"force": true, "reason": "manual_maintenance"}'
```

---

*آخرین به‌روزرسانی: ۲۰۲۶-۰۶-۲۵ | نسخه: 2.0.0 | Galaxy Vast AI Trading Platform*
