# 🤖 Bot12 - AI-Powered Trading Bot with MCP

Bot12 is a **comprehensive, production-ready trading bot** with:
- ✅ **MCP Server Integration** - Claude AI integration via Model Context Protocol
- ✅ **Multiple AI Agents** - AI Prediction, ML, SMC, Execution, Risk Management
- ✅ **MT5 Integration** - MetaTrader 5 connection for live trading
- ✅ **FastAPI Backend** - High-performance REST API for trade management
- ✅ **Advanced Analytics** - Performance tracking, market analysis, decision engine
- ✅ **Security Hardened** - Encrypted credentials, secure configuration, audit logging

---

## 📋 Project Structure

```
bot12/
├── backend/
│   ├── agents/              # AI/ML agents for trading decisions
│   │   ├── ai_prediction_agent.py
│   │   ├── ml_agent.py
│   │   ├── smc_agent.py           # Smart Money Concepts
│   │   ├── execution_agent.py
│   │   ├── risk_agent.py
│   │   └── voting_engine.py        # Consensus mechanism
│   ├── ai_prediction/       # Machine learning pipeline
│   ├── routes/              # Flask API endpoints
│   ├── models/              # Pydantic data models
│   └── services/            # Core trading services
├── frontend/                # Web dashboard (optional)
├── bot12_mcp_template.py   # MCP Server entry point
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup Environment
```bash
cp .env.example .env
# Edit .env with your MT5 credentials and API keys
```

### 3. Run the Trading Bot
```bash
python bot12_mcp_template.py
```

### 4. Integrate with Claude Desktop (Optional)
Add to `~/.config/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "bot12": {
      "command": "python",
      "args": ["/path/to/bot12_mcp_template.py"]
    }
  }
}
```

---

## 🎯 Key Features

### AI Agents
- **AI Prediction Agent** - Uses LLMs for market predictions
- **ML Agent** - Machine learning models for pattern recognition
- **SMC Agent** - Smart Money Concepts for institutional order detection
- **Execution Agent** - Optimal trade execution
- **Risk Agent** - Position sizing and risk management
- **Voting Engine** - Consensus-based trade decisions

### Trading Capabilities
- Live market data from MT5
- Automated trade execution
- Position management
- Trade history tracking
- Performance analytics

### MCP Integration
- 9 pre-built trading tools
- Claude AI integration
- Safe command execution with security annotations
- Comprehensive logging

---

## 📊 Configuration

Create `.env` file with:
```
MT5_ACCOUNT=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=your_broker_server

CLAUDE_API_KEY=your_claude_key
TELEGRAM_BOT_TOKEN=your_telegram_token
```

---

## 🧪 Testing

Run unit tests:
```bash
pytest tests/ -v
```

Test MCP Server:
```bash
npx @modelcontextprotocol/inspector python bot12_mcp_template.py
```

---

## 📚 Documentation

- **QUICK_START.md** - 30-minute setup guide
- **BOT12_MCP_SETUP_GUIDE.md** - Comprehensive MCP integration guide
- **IMPLEMENTATION_FLOWCHART.txt** - System architecture diagram

---

## ⚠️ Risk Disclaimer

This is an **automated trading bot**. Use at your own risk:
- Always test with small amounts first
- Implement proper risk management
- Monitor trades regularly
- Never leave automated trading unattended

---

## 🔒 Security Notes

- Never commit `.env` files with real credentials
- Use environment variables for sensitive data
- Implement rate limiting for APIs
- Regularly audit MCP tool access

---

## 📞 Support

For issues and questions:
1. Check documentation files
2. Review logs in `logs/` directory
3. Test individual components with pytest

---

**Last Updated:** July 2026
**Version:** 1.2.0
**Status:** Production Ready
