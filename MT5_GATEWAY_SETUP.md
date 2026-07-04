# 🔌 راهنمای نصب MT5 Gateway Agent

## هدف
Gateway یک پل بین Python Backend (روی Linux/Mac/Windows) و MetaTrader 5 (روی Windows) است.

---

## پیش‌نیازها

- Windows VPS یا Wine روی Linux
- MetaTrader 5 نصب شده و login کرده
- Python 3.11+
- دسترسی به backend (IP یا domain)

لطفاً ابتدا `SETUP.md` را مطالعه کنید.

---

## نصب روی Windows

```powershell
# نصب dependencies
pip install MetaTrader5 fastapi uvicorn[standard] httpx python-dotenv

# Clone یا copy پوشه mt5_gateway
cd mt5_gateway
```

---

## تنظیم Environment

فایل `mt5_gateway/.env` را بسازید:

```env
# MT5 credentials
MT5_LOGIN=12345678
MT5_PASSWORD=your_broker_password
MT5_SERVER=BrokerName-Demo

# Gateway security
GATEWAY_API_KEY=CHANGE_ME_min_32_chars_random_hex
GATEWAY_ENV=production

# Mode
MT5_DEMO_MODE=false

# Port
GATEWAY_PORT=8080
```

---

## اجرا

```powershell
# اجرای مستقیم
python agent.py --login 12345678 --password "YourPass" --server "Broker-Demo"

# یا با env file
python agent.py
```

---

## تست اتصال

```powershell
# پینگ gateway
curl http://localhost:8080/ping
# انتظار: {"status":"ok","mt5_connected":true}

# وضعیت حساب
curl -H "X-Gateway-Key: your-api-key" http://localhost:8080/account
```

---

## تنظیم Backend

در فایل `.env` پروژه اصلی:

```env
MT5_GATEWAY_URL=http://<IP-Windows-VPS>:8080
MT5_GATEWAY_API_KEY=CHANGE_ME_min_32_chars_random_hex
MT5_DEMO_MODE=false
```

> ⚠️ اگر backend روی Linux است و gateway روی Windows VPS جداگانه:
> `MT5_GATEWAY_URL=http://<IP-Windows-VPS>:8080`
> پورت 8080 را در firewall Windows باز کنید (فقط برای IP سرور Linux)

---

## Checklist قبل از LIVE

- [ ] MetaTrader 5 login کرده و chart باز است
- [ ] `pip install MetaTrader5` موفق بوده
- [ ] `python agent.py` اجرا می‌شود
- [ ] `/ping` پاسخ `mt5_connected: true` می‌دهد
- [ ] `MT5_DEMO_MODE=false` در هر دو .env (gateway و backend)
- [ ] `GATEWAY_API_KEY` در هر دو .env یکسان است
- [ ] Lot size حداقل (0.01) برای تست اول
- [ ] Kill Switch (`/halt` در Telegram) تست شده

---

## عیب‌یابی

| مشکل | راه‌حل |
|------|--------|
| `mt5_connected: false` | MT5 را باز کنید و login کنید |
| `401 Unauthorized` | GATEWAY_API_KEY را در هر دو طرف یکسان کنید |
| `Connection refused` | پورت 8080 را در firewall باز کنید |
| `ModuleNotFoundError: MetaTrader5` | `pip install MetaTrader5` را اجرا کنید |
| EA سیگنال نمی‌گیرد | `InpApiBaseUrl` در EA را با IP gateway تنظیم کنید |
