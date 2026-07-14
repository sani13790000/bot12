# ⚡ Bot12 MCP Server - Quick Start (30 Minutes)

## What You're Getting

✅ **bot12_mcp_template.py** - Complete MCP server template with 9 pre-built tools  
✅ **BOT12_MCP_SETUP_GUIDE.md** - Detailed 7-step customization guide  
✅ **mcp_requirements.txt** - All dependencies  
✅ **QUICK_START.md** - This file (30-minute getting started)

---

## 5-Minute Summary

### What is MCP?
MCP = Model Context Protocol. It lets AI assistants (like Claude) call functions from your applications.

**In plain English:**
- You expose your bot12 as callable "tools"
- Claude can ask your bot12 questions
- Claude can execute trades through your bot12
- All through a standardized protocol

### What's in the Template?

**9 Pre-Built Tools:**
1. `get_account_balance()` - Get your balance
2. `get_active_positions()` - See open trades
3. `get_market_price(symbol)` - Get current prices
4. `execute_trade(...)` - Place a trade
5. `close_position(id)` - Close a trade
6. `get_trade_history()` - See past trades
7. `generate_performance_report()` - Get stats
8. `get_system_status()` - Bot health check
9. `get_bot_logs()` - See recent logs

---

## 🚀 30-Minute Quick Start

### Step 1: Install (5 min)
```bash
pip install -r mcp_requirements.txt
```

### Step 2: Customize (15 min)
Open `bot12_mcp_template.py` and find these 4 functions:

```python
1. get_account_from_bot()        # Line ~230
2. get_positions_from_bot()       # Line ~260
3. get_market_data_from_bot()     # Line ~285
4. [Helper functions in tools]    # Throughout
```

Replace the "TODO" comments with your actual bot12 code.

**Example:**
```python
# BEFORE (placeholder):
def get_account_from_bot() -> AccountInfo:
    return AccountInfo(balance=10000.0, ...)

# AFTER (real code):
def get_account_from_bot() -> AccountInfo:
    from backend.account_manager import AccountManager
    data = AccountManager().get_balance()
    return AccountInfo(
        balance=data['balance'],
        equity=data['equity'],
        # ... rest of fields
    )
```

### Step 3: Test (10 min)

**Option A: Quick Python Test**
```bash
python bot12_mcp_template.py
# Should start without errors
```

**Option B: MCP Inspector (Best for debugging)**
```bash
npx @modelcontextprotocol/inspector python bot12_mcp_template.py
# Opens web UI where you can test each tool
```

---

## 📋 Minimal Customization (What You MUST Do)

These 4 functions MUST be customized for your bot12:

### Function 1: `get_account_from_bot()`
```python
# Find this section around line 230:
def get_account_from_bot() -> AccountInfo:
    # TODO: Replace with actual bot12 call
    # client = get_bot_client()
    # data = client.get_account_info()
    
    return AccountInfo(
        balance=10000.0,  # Replace with actual
        equity=9950.0,    # Replace with actual
        # ... etc
    )
```

**What to do:**
- Replace placeholder values with real bot12 calls
- Use your actual bot12 Python modules

### Function 2: `get_positions_from_bot()`
```python
# Find around line 260
def get_positions_from_bot() -> List[Position]:
    # TODO: Replace with actual bot12 call
    return [
        Position(
            position_id=1,
            symbol="EURUSD",
            # ... replace with real data from bot12
        )
    ]
```

### Function 3: `get_market_data_from_bot(symbol)`
```python
# Find around line 285
def get_market_data_from_bot(symbol: str) -> MarketData:
    # TODO: Replace with actual bot12 call
    return MarketData(
        symbol=symbol,
        bid=1.0870,  # Replace with real data
        # ... replace with real data
    )
```

### Function 4: Tools that call helper functions
```python
# Each @server.tool() function has a "TODO" comment
# Replace with actual bot12 calls
# Example around line 365:

@server.tool()
def execute_trade(...) -> Dict[str, Any]:
    # TODO: Replace with actual bot12 call:
    # client = get_bot_client()
    # order = client.execute_trade(...)
    
    return { ... }  # Replace with real response
```

---

## 🎯 After Customization: How to Use

### Option 1: Direct Python Testing
```python
from bot12_mcp_template import (
    get_account_balance,
    get_active_positions
)

# Test it
balance = get_account_balance()
print(f"Balance: {balance.balance}")

positions = get_active_positions()
print(f"Open positions: {len(positions)}")
```

### Option 2: MCP Inspector (Recommended)
```bash
# Start the interactive inspector
npx @modelcontextprotocol/inspector python bot12_mcp_template.py

# Then in the web UI:
# - Click each tool
# - Enter sample inputs
# - See the response
# - Debug any issues
```

### Option 3: Claude Desktop Integration
1. Find your Claude config file:
   - **Mac/Linux:** `~/.config/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

2. Add this:
```json
{
  "mcpServers": {
    "bot12": {
      "command": "python",
      "args": ["/absolute/path/to/bot12_mcp_template.py"]
    }
  }
}
```

3. Restart Claude Desktop

4. Ask Claude:
```
"What's my account balance using bot12?"
```

---

## 🔧 Minimal Setup Example

If your bot12 has this structure:

```
bot12/
├── backend/
│   ├── account.py          # Has get_balance() function
│   ├── positions.py        # Has get_positions() function
│   └── market.py           # Has get_price(symbol) function
```

Then customize like this:

```python
# At top of bot12_mcp_template.py, add:
from backend.account import get_balance
from backend.positions import get_positions
from backend.market import get_price

# Then replace helper functions:
def get_account_from_bot() -> AccountInfo:
    data = get_balance()
    return AccountInfo(
        balance=data['balance'],
        equity=data['equity'],
        currency="USD",
        margin_used=data['margin_used'],
        free_margin=data['free_margin'],
        margin_level=data['margin_level'],
        account_number=data['account_number']
    )

def get_positions_from_bot() -> List[Position]:
    positions = get_positions()
    return [
        Position(
            position_id=p['id'],
            symbol=p['symbol'],
            quantity=p['size'],
            entry_price=p['entry_price'],
            current_price=p['current_price'],
            pnl=p['pnl'],
            pnl_percent=p['pnl_percent'],
            stop_loss=p.get('sl'),
            take_profit=p.get('tp'),
            open_time=p['open_time']
        )
        for p in positions
    ]

def get_market_data_from_bot(symbol: str) -> MarketData:
    data = get_price(symbol)
    return MarketData(
        symbol=symbol,
        bid=data['bid'],
        ask=data['ask'],
        spread=data['spread'],
        timestamp=data['timestamp'],
        high_24h=data.get('high_24h'),
        low_24h=data.get('low_24h')
    )
```

---

## ⚠️ Common Issues & Fixes

### "ImportError: No module named backend"
```bash
# Fix: Add bot12 to Python path
export PYTHONPATH="/path/to/bot12:$PYTHONPATH"
python bot12_mcp_template.py
```

### "TypeError: expected AccountInfo, got dict"
```python
# Fix: Make sure you're returning the Pydantic model, not dict
return AccountInfo(  # ← Use model class
    balance=data['balance'],
    ...
)
# NOT:
return {            # ← Wrong
    'balance': data['balance'],
    ...
}
```

### "Tool not showing in Claude"
- Restart Claude Desktop completely
- Check claude_desktop_config.json syntax (valid JSON)
- Use absolute path to bot12_mcp_template.py
- Make sure Python file is in PYTHONPATH

### "Module has no attribute 'get_balance'"
- Check your actual bot12 function names
- Print available functions: `dir(module)`
- Look at your bot12 code for the actual function names

---

## 📚 Full Documentation

For complete details, see:
- **Setup Guide**: `BOT12_MCP_SETUP_GUIDE.md` (7 detailed phases)
- **Template Code**: `bot12_mcp_template.py` (with inline comments)
- **Official MCP Docs**: https://modelcontextprotocol.io/

---

## ✅ Success Checklist (Before You're Done)

- [ ] Installed requirements: `pip install -r mcp_requirements.txt`
- [ ] Found your bot12 functions to wrap
- [ ] Customized 4 helper functions in template
- [ ] Ran template directly: `python bot12_mcp_template.py` (no errors)
- [ ] Tested with MCP Inspector: `npx @modelcontextprotocol/inspector python bot12_mcp_template.py`
- [ ] All tools show in Inspector web UI
- [ ] Can click tools and see responses
- [ ] Integrated with Claude Desktop (optional but recommended)

---

## 🎓 Learning Path

1. **This Quick Start** (you are here) - 30 min overview
2. **Run the template** - 15 min to get it working
3. **Customize for bot12** - 1-2 hours depending on complexity
4. **Test thoroughly** - 30 min with MCP Inspector
5. **Integrate with Claude** - 10 min for Claude Desktop setup
6. **Full Setup Guide** - Deep dive into production details

---

## 🤔 Questions?

**Q: Do I need to change the schema?**
A: Usually no. The schemas are generic for most trading bots. Customize only if you have different field names.

**Q: Can I add more tools?**
A: Yes! Copy one of the existing `@server.tool()` functions and modify it.

**Q: Is this secure for live trading?**
A: The template has security annotations. Review the full guide for production security hardening.

**Q: Can I use this with other AI assistants?**
A: Yes! Any MCP-compatible client can use it (Claude, Cursor, Windsurf, etc.)

---

## 🚀 You're Ready!

That's it. You have everything you need to:
1. Wrap your bot12 as MCP tools
2. Test with MCP Inspector
3. Use with Claude
4. Deploy for production

**Next step:** Open `bot12_mcp_template.py` and start customizing!

---

**Time investment:**
- Quick setup: 30 minutes
- Full customization: 2-3 hours
- Production ready: 1 week (including testing & hardening)

**You've got this!** 🚀
