# Galaxy Vast AI Trading Platform - Setup Guide

**Setup Time:** 15-20 minutes  
**Requirements:** Python 3.9+, Node.js 16+, MT5, PostgreSQL, Redis

---

## 📋 Prerequisites

Before starting, ensure you have:

1. **MetaTrader 5** - Download from [MetaQuotes](https://www.metatrader5.com)
2. **Python 3.9+** - [Download](https://www.python.org/downloads/)
3. **Node.js 16+** - [Download](https://nodejs.org/)
4. **PostgreSQL 14+** - [Download](https://www.postgresql.org/download/)
5. **Redis** - [Download](https://redis.io/download) or use Docker
6. **Docker** (optional but recommended)
7. **Git** - For cloning the repository

---

## 🚀 Quick Start (Docker)

### 1. Clone Repository

```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12-main
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```env
# Database
DATABASE_URL=postgresql://bot12:bot12pass@postgres:5432/bot12

# Redis
REDIS_URL=redis://redis:6379/0

# MT5
MT5_ACCOUNT=5052866922
MT5_PASSWORD=your_password
MT5_SERVER=MetaQuotes-Demo

# Telegram
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_USER_ID=your_user_id

# JWT
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_EXPIRE_MINUTES=30

# API
API_HOST=0.0.0.0
API_PORT=8000

# Frontend
REACT_APP_API_URL=http://localhost:8000/api
```

### 3. Start with Docker Compose

```bash
docker-compose up -d
```

Wait for all services to start:
- PostgreSQL on port 5432
- Redis on port 6379
- Backend API on http://localhost:8000
- Frontend on http://localhost:3000

### 4. Access Dashboard

Open browser:
```
http://localhost:3000
```

Login with default credentials:
```
Username: admin
Password: admin
```

⚠️ **CHANGE PASSWORD IMMEDIATELY IN PRODUCTION**

---

## 🔧 Manual Setup (Without Docker)

### 1. Backend Setup

#### 1.1 Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### 1.2 Install Dependencies

```bash
pip install -r requirements.txt
```

#### 1.3 Setup PostgreSQL

```bash
# Create database
createdb bot12
createuser bot12 -P  # Enter password: bot12pass

# Run migrations
psql bot12 < supabase/migrations/001_initial_schema.sql
psql bot12 < supabase/migrations/002_rls_policies.sql
```

#### 1.4 Start Redis

```bash
# On macOS
brew install redis
redis-server

# On Linux
redis-server

# Or using Docker
docker run -d -p 6379:6379 redis:latest
```

#### 1.5 Start Backend

```bash
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at `http://localhost:8000`

### 2. Frontend Setup

#### 2.1 Install Dependencies

```bash
cd frontend
npm install
```

#### 2.2 Configure Environment

Create `.env`:
```
REACT_APP_API_URL=http://localhost:8000/api
```

#### 2.3 Start Frontend

```bash
npm start
```

Frontend will open at `http://localhost:3000`

---

## 📊 MT5 Setup

### 1. Install MQL5 Expert Advisor

1. Open MetaTrader 5
2. Go to `File` → `Open Data Folder`
3. Navigate to `MQL5\Experts\`
4. Copy `GalaxyVast_EA.mq5` to this folder
5. In MT5: `File` → `Refresh` (F5)

### 2. Configure Expert Advisor

1. Right-click on chart → `Experts` → `GalaxyVast_EA`
2. In settings configure:
   - **LotSize:** 0.1
   - **BackendURL:** http://localhost:8000
   - **APIToken:** (Get from dashboard after login)
   - **DemoMode:** true (for testing)
   - **EnableTrading:** true

3. Click `OK` to attach to chart

### 3. Get API Token

1. Login to dashboard (http://localhost:3000)
2. Go to `Settings` → `API Keys`
3. Generate new API key
4. Copy token and paste in EA settings

---

## 🔐 Security Configuration

### 1. Change Default Credentials

```bash
# Login to dashboard
# Settings → Account → Change Password
```

### 2. Set Strong JWT Secret

```bash
# Generate random secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Update .env
JWT_SECRET_KEY=your-generated-secret
```

### 3. Enable HTTPS (Production)

```bash
# Install SSL certificate
# Update docker-compose.prod.yml with certificate paths
# Or use Let's Encrypt with certbot
```

### 4. Configure Firewall

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 3000/tcp    # Frontend (internal)
sudo ufw allow 8000/tcp    # Backend (internal)
```

---

## 📱 Telegram Configuration

### 1. Create Telegram Bot

1. Open Telegram
2. Search for `@BotFather`
3. Send `/newbot`
4. Follow instructions
5. Copy token

### 2. Get Your Telegram User ID

1. Search for `@userinfobot`
2. Send any message
3. Bot returns your numeric user ID (not @username)

### 3. Configure in Dashboard

1. Login to dashboard
2. Go to `Settings` → `Notifications` → `Telegram`
3. Enter:
   - **Bot Token:** (from BotFather)
   - **User ID:** (numeric, not @username)
4. Click `Test` to verify

---

## ✅ Verification Checklist

### Backend
- [ ] PostgreSQL connected
- [ ] Redis connected
- [ ] API running on port 8000
- [ ] Health check: `curl http://localhost:8000/api/health`

### Frontend
- [ ] Frontend running on port 3000
- [ ] Can login with default credentials
- [ ] Dashboard loads without errors

### MT5
- [ ] Expert Advisor attached to chart
- [ ] API token configured in EA
- [ ] No errors in MT5 journal

### Telegram
- [ ] Bot token valid
- [ ] User ID correct (numeric)
- [ ] Test notification received

---

## 🚨 Troubleshooting

### "Database connection failed"

```bash
# Check PostgreSQL is running
psql -U bot12 -d bot12 -c "SELECT NOW();"

# Check connection string in .env
DATABASE_URL=postgresql://bot12:bot12pass@localhost:5432/bot12
```

### "Redis connection failed"

```bash
# Check Redis is running
redis-cli ping  # Should return PONG

# Check connection string in .env
REDIS_URL=redis://localhost:6379/0
```

### "Expert Advisor won't connect"

```
1. Check BackendURL in EA settings
2. Ensure backend is running: http://localhost:8000/api/health
3. Check APIToken is not empty
4. Check firewall allows port 8000
```

### "Can't login to dashboard"

```bash
# Check backend logs
# Login should show: "User admin logged in"

# Reset admin password (database)
psql bot12
UPDATE users SET password_hash = '$2b$12...' WHERE username = 'admin';
```

---

## 📚 Next Steps

1. **Configure MT5 Account**
   - Add account in Settings → MT5
   - Test connection

2. **Enable Paper Trading**
   - Set `DemoMode=true` in EA
   - Run for 1-2 hours to test

3. **Review Signals**
   - Check Dashboard → Positions
   - Verify P&L calculations
   - Test Telegram notifications

4. **Live Trading** (Only after testing)
   - Change `DemoMode=false` in EA
   - Use small lot size initially
   - Monitor closely

---

## 🆘 Getting Help

- **Documentation:** See `README.md`, `docs/API.md`
- **Issues:** Report on [GitHub Issues](https://github.com/sani13790000/bot12/issues)
- **Email:** admin@galaxyvast.ai

---

**Last Updated:** 2026-07-10  
**Version:** 1.0.0
