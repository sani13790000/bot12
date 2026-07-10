"""Unit tests for backend/telegram/utils.py message formatting helpers."""
from __future__ import annotations

from backend.telegram.utils import (
    escape_html,
    format_analysis_result,
    format_error_message,
    format_report_summary,
    format_signal_card,
    format_trade_detail,
    format_trade_list,
    format_welcome_message,
)


class TestWelcome:
    def test_includes_username(self):
        msg = format_welcome_message("Ali")
        assert "Ali" in msg
        assert "<b>Ali</b>" in msg


class TestAnalysisResult:
    def test_buy_direction_and_entry_allowed(self):
        result = {
            "decision": {
                "symbol": "EURUSD",
                "timeframe": "H1",
                "direction": "buy",
                "total_score": 82,
                "entry_allowed": True,
                "levels": {"entry": 1.085, "tp": 1.09, "sl": 1.08},
                "filters_passed": ["trend", "session"],
            },
            "smc": {"structure": {"trend": "bullish", "bos": True, "choch": False},
                    "liquidity": {"type": "sweep"}},
            "price_action": {"patterns": [{"name": "PinBar", "bias": "bull"}]},
        }
        text = format_analysis_result(result)
        assert "EURUSD" in text
        assert "🟢 خرید" in text
        assert "82/100" in text
        assert "✅" in text
        assert "PinBar" in text
        assert "sweep" in text
        assert "trend" in text

    def test_sell_direction_and_blocked(self):
        text = format_analysis_result({"decision": {"direction": "sell", "entry_allowed": False}})
        assert "🔴 فروش" in text
        assert "❌" in text

    def test_neutral_with_empty_result(self):
        text = format_analysis_result({})
        assert "⚪ خنثی" in text
        assert "---" in text


class TestTradeList:
    def test_empty_list(self):
        text = format_trade_list([], title="Open")
        assert "Open" in text
        assert "یافت نشد" in text

    def test_populated_and_capped_at_ten(self):
        trades = [{"symbol": f"S{i}", "direction": "buy", "profit_money": 5.0, "status": "open"}
                  for i in range(15)]
        text = format_trade_list(trades, title="History")
        assert "History" in text
        assert text.count("🟢") == 10  # capped

    def test_loss_uses_loss_emoji(self):
        text = format_trade_list([{"symbol": "X", "direction": "sell", "profit_money": -3.2}])
        assert "🔴" in text
        assert "📉" in text
        assert "-3.20" in text


class TestTradeDetail:
    def test_contains_key_fields(self):
        trade = {
            "symbol": "XAUUSD", "direction": "buy", "status": "open",
            "volume": 0.1, "entry_price": 2000.0, "current_price": 2010.0,
            "profit_money": 100.0, "stop_loss": 1990.0, "take_profit": 2050.0,
            "opened_at": "2026-01-01", "closed_at": "---",
        }
        text = format_trade_detail(trade)
        assert "XAUUSD" in text
        assert "🟢 خرید" in text
        assert "$100.00" in text
        assert "2000.0" in text

    def test_none_sl_tp_fall_back_to_dash(self):
        text = format_trade_detail({"symbol": "X", "direction": "sell",
                                    "stop_loss": None, "take_profit": None,
                                    "profit_money": None})
        assert "---" in text
        assert "$0.00" in text


class TestSignalCard:
    def test_star_rating_and_levels(self):
        signal = {"symbol": "GBPUSD", "direction": "buy", "total_score": 80,
                  "entry_price": 1.25, "stop_loss": 1.24, "take_profit": 1.27,
                  "valid_until": "2026-01-02"}
        text = format_signal_card(signal)
        assert "GBPUSD" in text
        assert "80/100" in text
        assert "⭐" * 4 in text  # int(80/20) = 4 stars
        assert "1.25" in text

    def test_star_rating_capped_at_five(self):
        text = format_signal_card({"symbol": "X", "direction": "buy", "total_score": 100})
        assert "⭐" * 5 in text
        assert "⭐" * 6 not in text


class TestReportSummary:
    def test_profitable_report(self):
        text = format_report_summary({"summary": {"total_trades": 10, "win_rate": 60.0,
                                                   "net_profit": 250.0}})
        assert "10" in text
        assert "60.0%" in text
        assert "$250.00" in text
        assert "سودده" in text
        assert "✅" in text

    def test_losing_report(self):
        text = format_report_summary({"summary": {"net_profit": -50.0}})
        assert "زیان‌ده" in text
        assert "📉" in text


class TestErrorMessage:
    def test_known_error_type(self):
        assert format_error_message("not_found") == "❌ اطلاعات یافت نشد"

    def test_unknown_error_type_falls_back(self):
        assert format_error_message("does_not_exist") == "❌ خطای ناشناخته رخ داد"

    def test_appends_details(self):
        text = format_error_message("server", details="timeout")
        assert "خطا در ارتباط با سرور" in text
        assert "<i>timeout</i>" in text


class TestEscapeHtml:
    def test_escapes_special_characters(self):
        assert escape_html("<a> & </a>") == "&lt;a&gt; &amp; &lt;/a&gt;"

    def test_ampersand_escaped_first(self):
        # ensure "&lt;" is not double-escaped into "&amp;lt;"
        assert escape_html("<") == "&lt;"

    def test_plain_text_unchanged(self):
        assert escape_html("hello world") == "hello world"
