# Galaxy Vast AI Trading Platform - API Reference

**Version:** 1.0  
**Base URL:** `http://localhost:8000/api`  
**Authentication:** JWT Bearer Token  

---

## 📋 Table of Contents

1. [Authentication](#authentication)
2. [Trading Endpoints](#trading-endpoints)
3. [Position Management](#position-management)
4. [Trade History](#trade-history)
5. [Alerts](#alerts)
6. [Analytics](#analytics)
7. [Health Check](#health-check)

---

## Authentication

### Login

**POST** `/auth/login`

Request:
```json
{
  "username": "admin",
  "password": "password"
}
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "full_name": "Admin User",
    "is_active": true
  }
}
```

### Refresh Token

**POST** `/auth/refresh`

Request:
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### Logout

**POST** `/auth/logout`

Headers:
```
Authorization: Bearer {access_token}
```

Response:
```json
{
  "message": "Successfully logged out"
}
```

---

## Trading Endpoints

### Get Signal

**GET** `/trading/signal/{symbol}`

Parameters:
- `symbol` (string): Currency pair (e.g., EURUSD)

Headers:
```
Authorization: Bearer {access_token}
```

Response:
```json
{
  "signal": "BUY",
  "confidence": 0.85,
  "entry_price": 1.2500,
  "stop_loss": 1.2400,
  "take_profit": 1.2650,
  "timestamp": 1720699200
}
```

### Execute Trade

**POST** `/trading/execute`

Request:
```json
{
  "symbol": "EURUSD",
  "signal": "BUY",
  "volume": 0.1,
  "stop_loss": 1.2400,
  "take_profit": 1.2650
}
```

Response:
```json
{
  "ticket": 123456,
  "symbol": "EURUSD",
  "signal": "BUY",
  "volume": 0.1,
  "entry_price": 1.2500,
  "status": "open",
  "created_at": "2026-07-10T13:40:00Z"
}
```

### Trade Notification

**POST** `/trading/notify`

Request:
```json
{
  "ticket": 123456,
  "symbol": "EURUSD",
  "signal": "BUY",
  "timestamp": 1720699200
}
```

Response:
```json
{
  "success": true,
  "message": "Notification received"
}
```

---

## Position Management

### Get Open Positions

**GET** `/trading/positions`

Headers:
```
Authorization: Bearer {access_token}
```

Response:
```json
{
  "positions": [
    {
      "id": 1,
      "ticket": 123456,
      "symbol": "EURUSD",
      "position_type": "buy",
      "volume": 0.1,
      "entry_price": 1.2500,
      "current_price": 1.2520,
      "stop_loss": 1.2400,
      "take_profit": 1.2650,
      "profit": 20.00,
      "pnl_percent": 0.80,
      "status": "open",
      "opened_at": "2026-07-10T13:30:00Z"
    }
  ]
}
```

### Get Position Details

**GET** `/trading/positions/{id}`

Response:
```json
{
  "id": 1,
  "ticket": 123456,
  "symbol": "EURUSD",
  "position_type": "buy",
  "volume": 0.1,
  "entry_price": 1.2500,
  "current_price": 1.2520,
  "stop_loss": 1.2400,
  "take_profit": 1.2650,
  "profit": 20.00,
  "pnl_percent": 0.80,
  "status": "open",
  "opened_at": "2026-07-10T13:30:00Z"
}
```

### Close Position

**POST** `/trading/positions/{id}/close`

Response:
```json
{
  "id": 1,
  "ticket": 123456,
  "status": "closed",
  "exit_price": 1.2550,
  "profit": 50.00,
  "pnl_percent": 2.00,
  "closed_at": "2026-07-10T14:00:00Z"
}
```

---

## Trade History

### Get Trades

**GET** `/trading/trades?limit=50&offset=0`

Query Parameters:
- `limit` (int): Number of trades to return (default: 50)
- `offset` (int): Offset for pagination (default: 0)

Response:
```json
{
  "trades": [
    {
      "id": 1,
      "symbol": "EURUSD",
      "entry_price": 1.2500,
      "exit_price": 1.2550,
      "volume": 0.1,
      "profit_loss": 50.00,
      "pnl_percent": 2.00,
      "status": "closed",
      "entry_time": "2026-07-10T13:30:00Z",
      "exit_time": "2026-07-10T14:00:00Z",
      "strategy": "SMC + Price Action"
    }
  ],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

---

## Alerts

### Get Alerts

**GET** `/alerts?unread_only=false`

Query Parameters:
- `unread_only` (bool): Only return unread alerts (default: false)

Response:
```json
{
  "alerts": [
    {
      "id": 1,
      "alert_type": "trade",
      "level": "info",
      "title": "Trade Executed",
      "message": "BUY EURUSD at 1.2500",
      "is_read": false,
      "sent_via_telegram": true,
      "created_at": "2026-07-10T13:40:00Z"
    }
  ]
}
```

### Mark Alert as Read

**POST** `/alerts/{id}/read`

Response:
```json
{
  "id": 1,
  "is_read": true,
  "updated_at": "2026-07-10T14:00:00Z"
}
```

---

## Analytics

### Portfolio Stats

**GET** `/analytics/portfolio`

Response:
```json
{
  "equity": 10500.00,
  "balance": 10000.00,
  "profit": 500.00,
  "profit_percent": 5.00,
  "drawdown_percent": 2.50,
  "total_trades": 25,
  "winning_trades": 18,
  "losing_trades": 7,
  "win_rate": 72.00,
  "average_profit": 27.78,
  "average_loss": -28.57
}
```

### Trade Statistics

**GET** `/analytics/trades?period=30d`

Query Parameters:
- `period` (string): Time period (1d, 7d, 30d, 90d, 1y)

Response:
```json
{
  "period": "30d",
  "trades": 25,
  "winning_trades": 18,
  "losing_trades": 7,
  "win_rate": 72.00,
  "total_profit": 500.00,
  "average_profit_per_trade": 20.00,
  "best_trade": 150.00,
  "worst_trade": -75.00,
  "profit_factor": 2.14
}
```

### P&L Chart Data

**GET** `/analytics/pnl?period=30d`

Response:
```json
{
  "data": [
    {
      "date": "2026-06-10",
      "cumulative_profit": 100.00,
      "daily_profit": 100.00
    },
    {
      "date": "2026-06-11",
      "cumulative_profit": 150.00,
      "daily_profit": 50.00
    }
  ]
}
```

---

## Health Check

### Health Status

**GET** `/health`

Response:
```json
{
  "status": "ok",
  "database": "connected",
  "redis": "connected",
  "mt5": "connected",
  "telegram": "connected",
  "timestamp": "2026-07-10T14:00:00Z"
}
```

---

## Error Responses

All error responses follow this format:

```json
{
  "success": false,
  "error": "Error message",
  "code": "ERROR_CODE",
  "timestamp": "2026-07-10T14:00:00Z"
}
```

### Common Error Codes

- `UNAUTHORIZED` - Missing or invalid token
- `FORBIDDEN` - Insufficient permissions
- `NOT_FOUND` - Resource not found
- `VALIDATION_ERROR` - Invalid request parameters
- `RATE_LIMITED` - Too many requests
- `INTERNAL_ERROR` - Server error

---

## Rate Limiting

- **Free Tier:** 60 requests/minute
- **Premium Tier:** 1000 requests/minute

Rate limit headers:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1720699260
```

---

## Webhooks (Coming Soon)

Subscribe to webhooks for real-time trade notifications.

---

**Last Updated:** 2026-07-10  
**API Version:** 1.0
