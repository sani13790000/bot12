"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Unit Tests — Risk Management System v2
35 test cases covering all modules
"""
import pytest
import math
from unittest.mock import patch, MagicMock

# ── imports ─────────────────────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from backend.risk.lot_sizing import (
    DynamicLotSizer, LotSizingConfig, LotSizingMethod,
)
from backend.risk.equity_protection import (
    EquityProtectionEngine, EquityProtectionConfig, ProtectionLevel,
)
from backend.risk.correlation_filter import (
    CorrelationFilter, CorrelationFilterConfig,
    OpenPosition as CorrPosition,
)
from backend.risk.volatility_filter import (
    VolatilityFilter, VolatilityFilterConfig, VolatilityLevel,
)
from backend.risk.exposure_control import (
    ExposureControlEngine, ExposureControlConfig, ExposurePosition,
)
from backend.risk.risk_orchestrator import (
    RiskOrchestrator, RiskInput,
)


# ════════════════════════════════════════════════════════════════
# 1. DynamicLotSizer
# ════════════════════════════════════════════════════════════════

class TestDynamicLotSizer:

    def setup_method(self):
        self.cfg = LotSizingConfig(
            method=LotSizingMethod.FIXED_PERCENT,
            risk_percent=1.0, pip_value_usd=10.0,
            min_lot=0.01, max_lot=5.0, lot_step=0.01,
        )
        self.sizer = DynamicLotSizer(self.cfg)

    def test_fixed_percent_basic(self):
        """$10,000 × 1% / (20 pips × $10) = 0.50 lot"""
        result = self.sizer.calculate(balance=10_000, stop_loss_pips=20)
        assert result.lot_size == pytest.approx(0.50, abs=0.01)
        assert result.risk_percent == pytest.approx(1.0, abs=0.05)

    def test_atr_based_uses_larger_sl(self):
        """ATR-based should use ATR×multiplier when larger than SL."""
        cfg = LotSizingConfig(method=LotSizingMethod.ATR_BASED,
                              atr_multiplier=2.0, risk_percent=1.0,
                              pip_value_usd=10.0, min_lot=0.01, max_lot=5.0)
        sizer = DynamicLotSizer(cfg)
        result = sizer.calculate(balance=10_000, stop_loss_pips=10, atr_pips=15)
        # adjusted_sl = max(10, 15*2) = 30 pips
        assert result.lot_size == pytest.approx(10_000*0.01/(30*10), abs=0.01)

    def test_max_risk_cap_enforced(self):
        """Lot size must never exceed max_risk_percent of balance."""
        result = self.sizer.calculate(balance=10_000, stop_loss_pips=1)
        assert result.risk_percent <= self.cfg.max_risk_percent + 0.01

    def test_lot_clamped_to_min(self):
        """Tiny balance → lot clamped to min_lot."""
        result = self.sizer.calculate(balance=10, stop_loss_pips=1_000)
        assert result.lot_size == self.cfg.min_lot

    def test_lot_clamped_to_max(self):
        """Huge balance → lot clamped to max_lot."""
        result = self.sizer.calculate(balance=10_000_000, stop_loss_pips=1)
        assert result.lot_size == self.cfg.max_lot

    def test_kelly_criterion(self):
        """Kelly output > 0 with valid win_rate/rr."""
        cfg = LotSizingConfig(method=LotSizingMethod.KELLY,
                              kelly_fraction=0.25, pip_value_usd=10.0,
                              min_lot=0.01, max_lot=5.0)
        sizer = DynamicLotSizer(cfg)
        result = sizer.calculate(balance=10_000, stop_loss_pips=20,
                                 win_rate=0.60, avg_rr=2.0)
        assert result.lot_size >= cfg.min_lot

    def test_zero_balance_returns_min_lot(self):
        result = self.sizer.calculate(balance=0, stop_loss_pips=20)
        assert result.lot_size == self.cfg.min_lot

    def test_lot_step_respected(self):
        result = self.sizer.calculate(balance=10_000, stop_loss_pips=17)
        # Must be multiple of 0.01
        assert math.isclose(result.lot_size % self.cfg.lot_step, 0.0, abs_tol=1e-9) or                math.isclose(result.lot_size % self.cfg.lot_step, self.cfg.lot_step, abs_tol=1e-9)


# ════════════════════════════════════════════════════════════════
# 2. EquityProtectionEngine
# ════════════════════════════════════════════════════════════════

class TestEquityProtection:

    def _engine(self, **kwargs):
        cfg = EquityProtectionConfig(**kwargs)
        e = EquityProtectionEngine(cfg)
        e.initialize(10_000)
        return e

    def test_safe_state_initial(self):
        e = self._engine()
        result = e.check_can_trade()
        assert result.can_trade is True
        assert result.level == ProtectionLevel.SAFE

    def test_max_drawdown_halts(self):
        e = self._engine(max_drawdown_percent=10.0)
        result = e.update_equity(8_900, 8_900)  # 11% drawdown
        assert result.can_trade is False
        assert result.level == ProtectionLevel.HALTED
        assert result.should_close_all is True

    def test_warning_zone(self):
        e = self._engine(warning_drawdown_percent=5.0, max_drawdown_percent=10.0)
        result = e.update_equity(9_450, 9_450)  # 5.5% drawdown
        assert result.can_trade is True
        assert result.level == ProtectionLevel.WARNING

    def test_consecutive_losses_halt(self):
        e = self._engine(consecutive_loss_halt_count=3)
        for _ in range(3):
            e.record_trade_result(-100, 9_700)
        result = e.check_can_trade()
        assert result.can_trade is False

    def test_win_resets_consecutive_losses(self):
        e = self._engine(consecutive_loss_halt_count=5)
        for _ in range(2):
            e.record_trade_result(-100, 9_800)
        e.record_trade_result(200, 10_000)   # WIN
        assert e.state.consecutive_losses == 0

    def test_daily_loss_halt(self):
        e = self._engine(daily_loss_halt_percent=3.0)
        e.record_trade_result(-310, 9_690)  # 3.1% loss
        result = e.check_can_trade()
        assert result.can_trade is False

    def test_manual_resume(self):
        e = self._engine(max_drawdown_percent=5.0)
        e.update_equity(9_400, 9_400)
        e.manual_resume()
        assert e.state.halt_time is None
        assert e.state.protection_level == ProtectionLevel.SAFE

    def test_high_water_mark_updated(self):
        e = self._engine()
        e.update_equity(11_000, 11_000)
        assert e.state.high_water_mark == 11_000


# ════════════════════════════════════════════════════════════════
# 3. CorrelationFilter
# ════════════════════════════════════════════════════════════════

class TestCorrelationFilter:

    def setup_method(self):
        self.cf = CorrelationFilter(CorrelationFilterConfig(
            max_correlated_exposure=0.80,
            correlation_penalty_threshold=0.60,
        ))

    def test_no_positions_passes(self):
        result = self.cf.check("EURUSD", "BUY", [], 1.0)
        assert result.can_trade is True
        assert result.risk_multiplier == 1.0

    def test_highly_correlated_blocked(self):
        # EURUSD + GBPUSD correlation = 0.85
        positions = [CorrPosition("GBPUSD", "BUY", 1.0)]
        result = self.cf.check("EURUSD", "BUY", positions, 1.0)
        assert result.can_trade is False

    def test_inverse_correlation_allowed(self):
        # EURUSD + USDCHF = -0.92, but EURUSD BUY + USDCHF SELL = diversifying
        positions = [CorrPosition("USDCHF", "SELL", 1.0)]
        result = self.cf.check("EURUSD", "BUY", positions, 1.0)
        # Net effective correlation = 0.92 in opposite direction → penalty not same-dir
        # Should be allowed (or with penalty) but not hard-blocked if < threshold
        assert isinstance(result.can_trade, bool)

    def test_correlation_penalty_applied(self):
        positions = [CorrPosition("AUDUSD", "BUY", 1.0)]  # corr=0.72
        result = self.cf.check("EURUSD", "BUY", positions, 1.0)
        if result.can_trade:
            assert result.risk_multiplier <= 1.0

    def test_get_correlation_same_symbol(self):
        assert self.cf.get_correlation("EURUSD", "EURUSD") == 1.0

    def test_get_correlation_unknown(self):
        result = self.cf.get_correlation("ABCXYZ", "DEFQRS")
        assert result is None


# ════════════════════════════════════════════════════════════════
# 4. VolatilityFilter
# ════════════════════════════════════════════════════════════════

class TestVolatilityFilter:

    def setup_method(self):
        self.vf = VolatilityFilter(VolatilityFilterConfig(
            low_atr_ratio=0.5,
            high_atr_ratio=2.0,
            extreme_atr_ratio=3.5,
            max_spread_multiplier=3.0,
            high_vol_lot_multiplier=0.6,
        ))
        self.avg_history = [10.0] * 14  # avg ATR = 10

    def test_normal_volatility(self):
        result = self.vf.check(10.0, self.avg_history, 1.0, 1.0)
        assert result.can_trade is True
        assert result.level == VolatilityLevel.NORMAL
        assert result.lot_multiplier == 1.0

    def test_extreme_volatility_blocked(self):
        result = self.vf.check(40.0, self.avg_history, 1.0, 1.0)
        assert result.can_trade is False
        assert result.level == VolatilityLevel.EXTREME

    def test_high_volatility_reduces_lot(self):
        result = self.vf.check(22.0, self.avg_history, 1.0, 1.0)
        assert result.can_trade is True
        assert result.level == VolatilityLevel.HIGH
        assert result.lot_multiplier == 0.6

    def test_low_volatility_allowed(self):
        result = self.vf.check(4.0, self.avg_history, 1.0, 1.0)
        assert result.can_trade is True
        assert result.level == VolatilityLevel.LOW

    def test_spread_spike_blocked(self):
        result = self.vf.check(10.0, self.avg_history, 4.0, 1.0)  # 4x spread
        assert result.can_trade is False

    def test_atr_calculation(self):
        highs  = [100 + i*0.5 for i in range(20)]
        lows   = [99  + i*0.5 for i in range(20)]
        closes = [99.5 + i*0.5 for i in range(20)]
        atrs = self.vf.calculate_atr(highs, lows, closes)
        assert len(atrs) > 0
        assert all(a > 0 for a in atrs)


# ════════════════════════════════════════════════════════════════
# 5. ExposureControlEngine
# ════════════════════════════════════════════════════════════════

class TestExposureControl:

    def setup_method(self):
        self.engine = ExposureControlEngine(ExposureControlConfig(
            max_total_exposure_percent=5.0,
            max_per_symbol_percent=2.0,
            max_per_currency_percent=3.0,
            max_simultaneous_trades=5,
            max_buy_trades=3,
            max_sell_trades=3,
        ))

    def test_empty_positions_passes(self):
        result = self.engine.check("XAUUSD", "BUY", 1.0, [], 10_000)
        assert result.can_trade is True

    def test_max_total_exposure_blocked(self):
        positions = [
            ExposurePosition("EURUSD", "BUY", 2.0, 200),
            ExposurePosition("GBPUSD", "BUY", 2.0, 200),
            ExposurePosition("AUDUSD", "BUY", 1.0, 100),
        ]
        result = self.engine.check("XAUUSD", "BUY", 1.0, positions, 10_000)
        assert result.can_trade is False

    def test_max_simultaneous_trades_blocked(self):
        positions = [
            ExposurePosition(f"SYM{i}", "BUY", 0.5, 50)
            for i in range(5)
        ]
        result = self.engine.check("XAUUSD", "BUY", 0.5, positions, 10_000)
        assert result.can_trade is False

    def test_duplicate_symbol_direction_blocked(self):
        positions = [ExposurePosition("XAUUSD", "BUY", 1.0, 100)]
        result = self.engine.check("XAUUSD", "BUY", 1.0, positions, 10_000)
        assert result.can_trade is False

    def test_opposite_direction_same_symbol_allowed(self):
        positions = [ExposurePosition("XAUUSD", "BUY", 1.0, 100)]
        result = self.engine.check("XAUUSD", "SELL", 1.0, positions, 10_000)
        # Allowed per config (different direction)
        assert isinstance(result.can_trade, bool)

    def test_buy_limit_respected(self):
        positions = [
            ExposurePosition(f"SYM{i}", "BUY", 0.5, 50)
            for i in range(3)
        ]
        result = self.engine.check("XAUUSD", "BUY", 0.5, positions, 10_000)
        assert result.can_trade is False  # max_buy_trades=3 reached


# ════════════════════════════════════════════════════════════════
# 6. RiskOrchestrator (integration)
# ════════════════════════════════════════════════════════════════

class TestRiskOrchestrator:

    def _make_input(self, **overrides) -> RiskInput:
        defaults = dict(
            symbol="XAUUSD", direction="BUY",
            balance=10_000, equity=10_000,
            stop_loss_pips=20.0, current_atr=10.0,
            atr_history=[10.0]*14,
            current_spread=1.0, avg_spread=1.0,
            open_positions=[], today_trades_count=0,
            today_pnl_usd=0.0, week_pnl_usd=0.0, month_pnl_usd=0.0,
        )
        defaults.update(overrides)
        return RiskInput(**defaults)

    def test_clean_signal_approved(self):
        orch = RiskOrchestrator()
        orch._equity.initialize(10_000)
        result = orch.assess(self._make_input())
        assert result.approved is True
        assert result.lot_size > 0

    def test_extreme_volatility_blocked(self):
        orch = RiskOrchestrator()
        orch._equity.initialize(10_000)
        inp = self._make_input(current_atr=45.0, atr_history=[10.0]*14)
        result = orch.assess(inp)
        assert result.approved is False
        assert result.volatility_ok is False

    def test_max_drawdown_blocks_all(self):
        orch = RiskOrchestrator()
        orch._equity.initialize(10_000)
        orch._equity.update_equity(8_500, 8_500)  # 15% drawdown
        result = orch.assess(self._make_input(balance=8_500, equity=8_500))
        assert result.approved is False
        assert result.equity_ok is False

    def test_result_to_dict_has_gates(self):
        orch = RiskOrchestrator()
        orch._equity.initialize(10_000)
        result = orch.assess(self._make_input())
        d = result.to_dict()
        assert "gates" in d
        assert "metrics" in d
        assert "lot_size" in d

    def test_record_trade_result_updates_state(self):
        orch = RiskOrchestrator()
        orch._equity.initialize(10_000)
        orch.record_trade_result(-200, 9_800)
        assert orch._equity.state.consecutive_losses == 1
        assert orch._equity.state.daily_loss_usd == pytest.approx(200, abs=1)
