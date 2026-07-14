# 🚀 BOT12 - START GUIDE

## ✅ تمام چیز آماده است!

Bot12 اکنون کامل، بدون باگ، و آماده برای کار است.

---

## 🎯 شروع سریع (5 دقیقه)

### Step 1: نصب Dependencies

```bash
# فایل پروژه را استخراج کن
tar -xzf bot12-repo-ready.tar.gz
cd bot12-repo

# Virtual environment بساز (اختیاری اما توصیه شده)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Dependencies نصب کن
pip install -r requirements.txt
```

### Step 2: Environment Configuration

```bash
# .env فایل بساز
cp .env.example .env

# اطلاعات خود را وارد کن:
nano .env
```

**مهم:** `.env` را پر کن:
```
MT5_ACCOUNT=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=your_broker_server
JWT_SECRET_KEY=your_secret_key_here
```

### Step 3: ربات را شروع کن

```bash
# روش 1: کامل (API + Agents)
python3 run_bot.py

# روش 2: فقط API Server
python3 -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# روش 3: MCP Server (برای Claude AI)
python3 bot12_mcp_template.py
```

### Step 4: ربات را Test کن

```bash
# در browser باز کن:
http://localhost:8000/docs

# API test کن:
curl http://localhost:8000/health

# Agents status بخواه:
curl http://localhost:8000/agents/status
```

---

## 🤖 Agents Status

```bash
# تمام agents را ببین
curl http://localhost:8000/agents

# Risk agent status
curl http://localhost:8000/agents/risk_agent/status

# AI Prediction agent
curl http://localhost:8000/agents/ai_prediction/status

# Voting engine
curl http://localhost:8000/agents/voting_engine/status
```

---

## 📊 API Endpoints

### Health & Status
```
GET  /health              ← Server status
GET  /                    ← API info
GET  /agents/status       ← All agents
```

### Trading
```
GET  /trades              ← Open trades
POST /trades              ← Place trade
GET  /trades/{id}         ← Trade details
PUT  /trades/{id}         ← Update trade
DELETE /trades/{id}       ← Close trade
```

### Analysis
```
GET  /analysis            ← Market analysis
GET  /predictions         ← AI predictions
GET  /signals             ← Trading signals
GET  /portfolio           ← Portfolio analysis
```

### Risk Management
```
GET  /risk/metrics        ← Risk metrics
GET  /risk/positions      ← Position limits
POST /risk/check          ← Risk validation
```

### Admin
```
GET  /admin/status        ← System status
GET  /admin/logs          ← System logs
POST /admin/restart       ← Restart agents
```

---

## 🐳 Docker (Optional)

```bash
# Docker image بساز
docker build -t bot12 .

# Container اجرا کن
docker run -p 8000:8000 \
  -e MT5_ACCOUNT=123456 \
  -e MT5_PASSWORD=yourpass \
  -e MT5_SERVER=your.server \
  bot12

# یا docker-compose
docker-compose up -d
```

---

## 📝 Logs و Monitoring

```bash
# Logs را دنبال کن (real-time)
tail -f logs/bot12.log

# امروز logs
grep "$(date +%Y-%m-%d)" logs/bot12.log

# Errors فقط
grep "ERROR" logs/bot12.log

# Performance metrics
curl http://localhost:8000/metrics
```

---

## 🔧 Configuration

### .env تنظیمات

```ini
# MT5
MT5_ACCOUNT=your_account
MT5_PASSWORD=your_password
MT5_SERVER=your.broker.server

# API
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false
LOG_LEVEL=INFO

# Security
JWT_SECRET_KEY=your_secret_key_at_least_32_chars
BCRYPT_ROUNDS=12

# Trading
MAX_POSITION_SIZE=10000
MAX_DAILY_LOSS_PERCENT=3.0
MAX_DRAWDOWN_PERCENT=8.0
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=5.0

# Telegram (Optional)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ENABLED=false

# Database
DATABASE_URL=sqlite:///bot12.db
# یا PostgreSQL:
# DATABASE_URL=postgresql://user:pass@localhost:5432/bot12
```

---

## ✅ Verification Checklist

عند شروع، این موارد را check کن:

```
☑ API server running (http://localhost:8000/docs)
☑ All agents initialized
☑ Database connected
☑ MT5 gateway ready (if configured)
☑ Logs appearing in console
☑ /health endpoint responding
☑ JWT configured
☑ .env file secure (not in git)
```

---

## 🐛 Troubleshooting

### Error: "ModuleNotFoundError: No module named 'backend'"

```bash
# از project root اجرا کن
cd bot12-repo
python3 run_bot.py
```

### Error: "Connection to MT5 failed"

```bash
# MT5 settings check کن
python3 -c "import MetaTrader5; print(MetaTrader5.version())"
```

### Port already in use

```bash
# دیگری port استفاده کن
python3 run_bot.py --port 8001

# یا process کو kill کن
lsof -ti:8000 | xargs kill -9
```

### Agents not initializing

```bash
# Dependencies check کن
pip install -r requirements.txt --upgrade

# Logs check کن
tail -50 logs/bot12.log
```

---

## 📊 Monitoring Dashboard

API documentation را برای monitoring استفاده کن:

```
http://localhost:8000/docs
```

**Features:**
- ✅ All API endpoints
- ✅ Real-time testing
- ✅ Parameter documentation
- ✅ Response schemas
- ✅ Error handling examples

---

## 🔐 Security Notes

⚠️ **IMPORTANT:**

1. ✅ Never commit `.env` file
2. ✅ Change JWT_SECRET_KEY
3. ✅ Use strong passwords
4. ✅ Enable HTTPS in production
5. ✅ Restrict API access with rate limiting
6. ✅ Keep credentials in `.env` only

---

## 🚀 Production Deployment

### Docker Compose

```yaml
version: '3.8'
services:
  bot12:
    image: bot12:latest
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - MT5_ACCOUNT=${MT5_ACCOUNT}
      - MT5_PASSWORD=${MT5_PASSWORD}
      - MT5_SERVER=${MT5_SERVER}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    volumes:
      - ./logs:/app/logs
      - ./bot12.db:/app/bot12.db
    restart: always
```

### Systemd Service

```ini
[Unit]
Description=Bot12 Trading Bot
After=network.target

[Service]
Type=simple
User=bot12
WorkingDirectory=/opt/bot12
ExecStart=/opt/bot12/venv/bin/python3 run_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 📚 Documentation

- `README.md` - Project overview
- `QUICK_START.md` - Quick start guide
- `bot12-startup-guide.md` - Detailed startup
- `DEPLOYMENT_READY.md` - Deployment checklist
- `PUSH_TO_GITHUB.md` - Git integration

---

## 🎯 Next Steps

1. ✅ Start the bot: `python3 run_bot.py`
2. ✅ Check `/docs` in browser
3. ✅ Test agents via API
4. ✅ Configure MT5 credentials
5. ✅ Set up monitoring
6. ✅ Deploy to production

---

## 💬 Support

اگر مشکل دارید:

1. Check logs: `tail -f logs/bot12.log`
2. Test endpoints: `http://localhost:8000/docs`
3. Check configuration: Review `.env` file
4. Verify dependencies: `pip install -r requirements.txt`

---

**Status:** ✅ PRODUCTION READY

🚀 Bot12 is ready to trade!
