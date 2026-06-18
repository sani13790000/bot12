"""
================================================================================
Galaxy Vast AI Trading Platform
ماژول تحقیق و بررسی — Research Module
================================================================================
این پوشه شامل موتورهای Backtest، Replay و Walk-Forward Analysis است.

ساختار:
  backtest/engine.py        ← موتور بک‌تست tick-level
  backtest/monte_carlo.py   ← شبیه‌سازی مونت کارلو
  replay/engine.py          ← موتور Replay بازار تاریخی
  replay/controller.py      ← کنترلر Replay (pause/resume/speed)
  walk_forward/analyzer.py  ← آنالیز Walk-Forward
  walk_forward/optimizer.py ← بهینه‌ساز پنجره rolling
================================================================================
"""
