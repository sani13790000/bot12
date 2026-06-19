# Galaxy Vast AI Trading Platform — Setup Guide

> Complete step-by-step setup from zero to live trading

---

## What does this bot do?

Galaxy Vast is an **institutional-grade AI trading system** for XAUUSD (Gold) and Forex pairs.

```
Market Data
    ↓
7 AI Agents (parallel)
├── SMC Agent          ← Order Block, FVG, BOS, CHoCH, Liquidity
├── Price Action Agent  ← Pin Bar, Engulfing, Fakey, Breakout
├── ML Agent            ← XGBoost + Walk-Forward + Drift Detection
├── Risk Agent          ← 1% risk per trade, daily loss limit
├── News Agent          ← High-impact news avoidance
├── Liquidity Agent     ← Liquidity sweeps and traps
└── Execution Agent     ← Execution conditions
    ↓
Voting Engine (weighted scoring)
    ↓
Decision Engine (BUY / SELL / NO_TRADE)
    ↓
Risk Orchestrator (lot size calculation)
    ↓
MT5 Connector → Live Trade Execution
    ↓
Telegram Notification + Supabase DB
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Ubuntu/Debian VPS | 22.04+ | Minimum 2 CPU, 4GB RAM, 20GB disk |
| Python | 3.11+ | Required |
| Docker + Docker Compose | Latest | For easy deployment |
| Git | Any | To clone the repo |
| Supabase account | Free | Database and auth |
| Telegram account | Any | For bot control |
| MetaTrader 5 | Latest | Windows VPS or Wine (for live trading) |

---

## Step 1 — Install System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl wget python3.11 python3.11-venv python3-pip

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

# Verify
python3.11 --version   # Python 3.11.x
docker --version        # Docker 24.x+
git --version
```

---

## Step 2 — Clone the Repository

```bash
git clone https://github.com/sani13790000/bot12.git galaxy-vast
cd galaxy-vast
ls -la  # You should see: backend/ dashboard/ frontend/ mql5/ supabase/ docker-compose.yml
```

---

## Step 3 — Set Up Supabase (Free Database)

1. Go to **[supabase.com](https://supabase.com)** and sign up
2. Click **New Project** → Name: `galaxy-vast` → Region: Frankfurt
3. Wait ~2 minutes for the project to initialize
4. Go to **Settings → API** and copy:
   - `Project URL` → this is your `SUPABASE_URL`
   - `anon public` key → this is your `SUPABASE_ANON_KEY`
   - `service_role secret` key → this is your `SUPABASE_SERVICE_ROLE_KEY`
5. Go to **Settings → Database** and copy the **Connection string** (URI format) → `SUPABASE_DB_URL`

### Run Migrations

In Supabase dashboard → **SQL Editor**, run these files in order:

```bash
# Or run from terminal:
for f in supabase/migrations/*.sql; do
  echo "Running: $f"
  psql "$SUPABASE_DB_URL" -f "$f"
done
```

---

## Step 4 — Create Telegram Bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Choose a name and username (e.g., `GalaxyVastBot`)
4. Copy the **token** → this is your `TELEGRAM_BOT_TOKEN`
5. Search **@userinfobot** → send `/start` → copy the numeric **Id** → this is your `TELEGRAM_ADMIN_IDS`

---

## Step 5 — Configure Environment

```bash
cp .env.example .env
nano .env   # or: vim .env
```

Fill in all **REQUIRED** fields:

```env
# Supabase (from Step 3)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_DB_URL=postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres

# Security keys (generate 3 separate keys)
JWT_SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_hex(32))">
LICENSE_ENCRYPTION_KEY=<run again>
LICENSE_SIGNATURE_KEY=<run again>

# Telegram (from Step 4)
TELEGRAM_BOT_TOKEN=1234567890:ABCdef...
TELEGRAM_ADMIN_IDS=123456789
```

### Generate security keys

```bash
# Run this 3 times, use each output for a different key:
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 6 — MetaTrader 5 Setup (for Live Trading)

> Skip this step if you only want backtesting and paper trading.

1. Install MetaTrader 5 on **Windows** (VPS recommended)
2. Open MT5 → **Tools → Options → Expert Advisors**:
   - ✔️ Allow automated trading
   - ✔️ Allow WebRequest for listed URL
   - Add `http://YOUR_SERVER_IP:8000`
3. Copy `mql5/Experts/MTTrading/` to your MT5 `MQL5/Experts/MTTrading/`
4. Copy `mql5/Include/MTTrading/` to your MT5 `MQL5/Include/MTTrading/`
5. Open MetaEditor → Compile the EA
6. Add the EA to an XAUUSD chart
7. Fill in MT5 credentials in `.env`:
   ```env
   MT5_LOGIN=12345678
   MT5_PASSWORD=your_password
   MT5_SERVER=YourBroker-Server
   ```

---

## Step 7 — Pre-flight Check

```bash
python3 startup_check.py
```

All checks should pass before running Docker.

---

## Step 8 — Launch

```bash
docker compose up -d --build
```

First build takes 5–10 minutes (downloading packages). Subsequent starts take ~30 seconds.

### Check status

```bash
docker compose ps           # All services should be "Up (healthy)"
docker compose logs api -f  # Watch API logs
curl http://localhost:8000/health  # Should return: {"status": "healthy"}
```

---

## Services & Ports

| Service | Port | URL | Purpose |
|---|---|---|---|
| FastAPI Backend | 8000 | http://localhost:8000 | REST API |
| API Documentation | 8000 | http://localhost:8000/docs | Swagger UI |
| Streamlit Dashboard | 8501 | http://localhost:8501 | Trading dashboard |
| React Frontend | 3000 | http://localhost:3000 | Main UI |
| Redis | 6379 | internal | Cache |

---

## Telegram Bot Commands

```
/start          → Welcome message
/start_bot      → Start automated trading
/stop_bot       → Stop trading
/status         → Current bot status
/report_daily   → Today's performance report
/winrate        → Win rate statistics
/open_trades    → Currently open positions
/balance        → Account balance
/add_user ID ROLE  → Add user (admin only)
/remove_user ID    → Remove user (admin only)
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `docker compose up` fails | Run `python3 startup_check.py` first |
| API not starting | Check `.env` — all REQUIRED vars must be set |
| "JWT_SECRET_KEY too short" | Must be 64 hex chars: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| Supabase connection error | Check `SUPABASE_DB_URL` includes the password |
| Telegram bot not responding | Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_IDS` |
| MT5 not connecting | Check MT5 WebRequest is enabled and URL is whitelisted |
| Dashboard not loading | Wait 30s after `docker compose up`, then open http://localhost:8501 |
| Port already in use | `sudo lsof -i :8000` then kill the process |

---

## Architecture

```
┌───────────────────────────────────────────────────────┐
│              Docker Network (galaxy_net)              │
│                                                       │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  │
│  │ FastAPI │  │Streamlit│  │ React  │  │  Redis │  │
│  │  :8000  │  │  :8501  │  │  :3000  │  │  :6379  │  │
│  └───┬───┘  └───┬───┘  └───┬───┘  └───┬───┘  │
│        │             │            │           │    │
└────────┼─────────────┼────────────┼───────────┘
                ↓             ↓            ↓
         Supabase DB      MetaTrader 5   Telegram
         (PostgreSQL)     (Windows VPS)   Bot API
```

---

## Performance

| Metric | Value |
|---|---|
| AI Agents | 7 parallel agents |
| Analysis Engine | SMC + Price Action + ML |
| ML Model | XGBoost with 15+ features |
| Backtest Speed | ~10,000 candles/sec |
| Max Drawdown Target | < 10% |
| Risk per Trade | 1% (configurable) |
| Supported Symbols | XAUUSD + all Forex pairs |
| Timeframes | M1, M5, M15, H1, H4, D1 |

---

*Galaxy Vast AI Trading Platform — Built for institutional performance.*
