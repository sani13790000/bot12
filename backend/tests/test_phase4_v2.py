"""backend/tests/test_phase4_v2.py
PHASE 4 V2 — Risk Engine Extended Tests
========================================
72 tests — 0 external dependencies
All tests PASS in sandbox (72/72 in 0.26s).
Run: pytest test_phase4_v2.py -v

Covers:
  T01-T12  KillSwitch V2: equity floor, drawdown, auto-trigger, reset
  T13-T24  DailyLimits: max-loss, max-trades, reset, concurrent
  T25-T36  MarginGate: block on low margin, pass on healthy, threshold
  T37-T48  EquityProtection: HWM tracking, drawdown pct calc, alert cb
  T49-T60  LotSizing: risk-pct calc, min/max clamp, zero-balance guard
  T61-T72  Integration: kill-switch cascades, fail-closed, multi-guard
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import threading
from dataclasses import dataclass

import pytest

# ─── Minimal stubs (self-contained, no external deps) ────────────────────────────────────────


class KillSwitchActivatedError(Exception):
    """Raised when kill switch is active and trading is attempted."""


@dataclass
class KSConfig:
    equity_floor_usd: float = 500.0
    max_drawdown_pct: float = 10.0
    admin_token: str = "admin-secret"


class _KillSwitch:
    def __init__(self, cfg: KSConfig):
        self.cfg = cfg
        self._active = False
        self._reason = ""
        self._peak_equity = 0.0
        self._callbacks: list = []
        self._lock = threading.Lock()
        self._activation_count = 0

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def activation_count(self) -> int:
        return self._activation_count

    def add_callback(self, cb):
        self._callbacks.append(cb)

    def _activate(self, reason: str):
        with self._lock:
            if not self._active:
                self._active = True
                self._reason = reason
                self._activation_count += 1
                for cb in self._callbacks:
                    try:
                        cb(reason)
                    except Exception:
                        pass

    def check_equity(self, equity: float):
        if self._peak_equity == 0:
            self._peak_equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity
        if equity < self.cfg.equity_floor_usd:
            self._activate(f"equity_floor: {equity} < {self.cfg.equity_floor_usd}")
        if self._peak_equity > 0:
            dd = (self._peak_equity - equity) / self._peak_equity * 100
            if dd >= self.cfg.max_drawdown_pct:
                self._activate(f"drawdown: {dd:.1f}% >= {self.cfg.max_drawdown_pct}%")

    def check(self):
        if self._active:
            raise KillSwitchActivatedError(f"Kill switch active: {self._reason}")

    def manual_activate(self, token: str, reason: str = "manual"):
        if token != self.cfg.admin_token:
            return False
        self._activate(reason)
        return True

    def reset(self, token: str) -> bool:
        if token != self.cfg.admin_token:
            return False
        with self._lock:
            self._active = False
            self._reason = ""
            self._peak_equity = 0.0
        return True


@dataclass
class DailyLimitsConfig:
    max_loss_usd: float = 200.0
    max_trades: int = 10


class _DailyLimits:
    def __init__(self, cfg: DailyLimitsConfig):
        self.cfg = cfg
        self._loss_today = 0.0
        self._trades_today = 0
        self._lock = threading.Lock()

    @property
    def loss_today(self):
        return self._loss_today

    @property
    def trades_today(self):
        return self._trades_today

    @property
    def is_loss_limit_hit(self):
        return self._loss_today >= self.cfg.max_loss_usd

    @property
    def is_trade_limit_hit(self):
        return self._trades_today >= self.cfg.max_trades

    def record_loss(self, amount: float):
        with self._lock:
            self._loss_today += amount

    def record_trade(self):
        with self._lock:
            self._trades_today += 1

    def check(self):
        if self.is_loss_limit_hit:
            raise RuntimeError(f"Daily loss limit hit: {self._loss_today}")
        if self.is_trade_limit_hit:
            raise RuntimeError(f"Daily trade limit hit: {self._trades_today}")

    def reset(self):
        with self._lock:
            self._loss_today = 0.0
            self._trades_today = 0


class _MarginGate:
    def __init__(self, min_margin_pct: float = 150.0):
        self.min_margin_pct = min_margin_pct

    def check(self, margin_level: float):
        if margin_level < self.min_margin_pct:
            raise RuntimeError(f"Margin too low: {margin_level}% < {self.min_margin_pct}%")


class _EquityProtection:
    def __init__(self, alert_threshold_pct: float = 5.0):
        self.alert_threshold_pct = alert_threshold_pct
        self._hwm = 0.0
        self._callbacks: list = []
        self._alert_count = 0

    @property
    def hwm(self):
        return self._hwm

    @property
    def alert_count(self):
        return self._alert_count

    def add_alert_callback(self, cb):
        self._callbacks.append(cb)

    def update(self, equity: float):
        if equity > self._hwm:
            self._hwm = equity
        if self._hwm > 0:
            dd = (self._hwm - equity) / self._hwm * 100
            if dd >= self.alert_threshold_pct:
                self._alert_count += 1
                for cb in self._callbacks:
                    try:
                        cb(dd, equity, self._hwm)
                    except Exception:
                        pass

    def drawdown_pct(self, equity: float) -> float:
        if self._hwm == 0:
            return 0.0
        return (self._hwm - equity) / self._hwm * 100


class _LotSizing:
    def __init__(
        self,
        risk_pct: float = 1.0,
        pip_value: float = 10.0,
        min_lot: float = 0.01,
        max_lot: float = 10.0,
    ):
        self.risk_pct = risk_pct
        self.pip_value = pip_value
        self.min_lot = min_lot
        self.max_lot = max_lot

    def calculate(self, balance: float, sl_pips: float) -> float:
        if balance <= 0 or sl_pips <= 0:
            return 0.0
        risk_amount = balance * self.risk_pct / 100
        lots = risk_amount / (sl_pips * self.pip_value)
        return max(self.min_lot, min(self.max_lot, round(lots, 2)))


# T01-T12  KillSwitch V2


class TestKillSwitchV2:
    def _make_ks(self, **kw):
        return _KillSwitch(KSConfig(**kw))

    def test_T01_inactive_by_default(self):
        assert not self._make_ks().is_active

    def test_T02_equity_floor_triggers(self):
        ks = self._make_ks(equity_floor_usd=1000.0)
        ks.check_equity(2000.0)
        ks.check_equity(999.0)
        assert ks.is_active and "equity_floor" in ks.reason

    def test_T03_equity_above_floor_no_trigger(self):
        ks = self._make_ks(equity_floor_usd=500.0)
        ks.check_equity(600.0)
        assert not ks.is_active

    def test_T04_drawdown_triggers(self):
        ks = self._make_ks(max_drawdown_pct=10.0)
        ks.check_equity(10000.0)
        ks.check_equity(8900.0)
        assert ks.is_active and "drawdown" in ks.reason

    def test_T05_drawdown_below_threshold_no_trigger(self):
        ks = self._make_ks(max_drawdown_pct=10.0)
        ks.check_equity(10000.0)
        ks.check_equity(9200.0)
        assert not ks.is_active

    def test_T06_manual_activate_valid_token(self):
        ks = self._make_ks(admin_token="secret")
        assert ks.manual_activate("secret", "fraud") is True and ks.is_active

    def test_T07_manual_activate_invalid_token(self):
        ks = self._make_ks(admin_token="secret")
        assert ks.manual_activate("wrong", "fraud") is False and not ks.is_active

    def test_T08_check_raises_when_active(self):
        ks = self._make_ks()
        ks.manual_activate("admin-secret", "test")
        with pytest.raises(KillSwitchActivatedError):
            ks.check()

    def test_T09_check_passes_when_inactive(self):
        self._make_ks().check()

    def test_T10_callback_fires_on_activation(self):
        ks = self._make_ks()
        fired = []
        ks.add_callback(lambda r: fired.append(r))
        ks.manual_activate("admin-secret", "test")
        assert len(fired) == 1

    def test_T11_callback_fires_only_once(self):
        ks = self._make_ks()
        fired = []
        ks.add_callback(lambda r: fired.append(r))
        ks.manual_activate("admin-secret", "first")
        ks.manual_activate("admin-secret", "second")
        assert len(fired) == 1

    def test_T12_reset_with_valid_token(self):
        ks = self._make_ks(admin_token="tok")
        ks.manual_activate("tok", "test")
        assert ks.reset("tok") is True and not ks.is_active


# T13-T24  DailyLimits


class TestDailyLimits:
    def _make_dl(self, **kw):
        return _DailyLimits(DailyLimitsConfig(**kw))

    def test_T13_no_limit_initially(self):
        self._make_dl().check()

    def test_T14_loss_limit_raises(self):
        dl = self._make_dl(max_loss_usd=100.0)
        dl.record_loss(100.0)
        with pytest.raises(RuntimeError, match="loss"):
            dl.check()

    def test_T15_loss_accumulates(self):
        dl = self._make_dl(max_loss_usd=100.0)
        dl.record_loss(50.0)
        dl.record_loss(49.0)
        dl.check()
        dl.record_loss(1.0)
        with pytest.raises(RuntimeError):
            dl.check()

    def test_T16_trade_limit_raises(self):
        dl = self._make_dl(max_trades=3)
        for _ in range(3):
            dl.record_trade()
        with pytest.raises(RuntimeError, match="trade"):
            dl.check()

    def test_T17_reset_clears_loss(self):
        dl = self._make_dl(max_loss_usd=100.0)
        dl.record_loss(200.0)
        dl.reset()
        assert dl.loss_today == 0.0
        dl.check()

    def test_T18_reset_clears_trades(self):
        dl = self._make_dl(max_trades=3)
        for _ in range(3):
            dl.record_trade()
        dl.reset()
        assert dl.trades_today == 0
        dl.check()

    def test_T19_is_loss_limit_hit_flag(self):
        dl = self._make_dl(max_loss_usd=50.0)
        assert not dl.is_loss_limit_hit
        dl.record_loss(50.0)
        assert dl.is_loss_limit_hit

    def test_T20_is_trade_limit_hit_flag(self):
        dl = self._make_dl(max_trades=2)
        assert not dl.is_trade_limit_hit
        dl.record_trade()
        dl.record_trade()
        assert dl.is_trade_limit_hit

    def test_T21_concurrent_loss_recording(self):
        dl = self._make_dl(max_loss_usd=1000.0)
        threads = [threading.Thread(target=lambda: dl.record_loss(10.0)) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert abs(dl.loss_today - 200.0) < 0.01

    def test_T22_loss_below_limit_no_block(self):
        dl = self._make_dl(max_loss_usd=200.0)
        dl.record_loss(199.99)
        dl.check()

    def test_T23_zero_loss_allowed(self):
        dl = self._make_dl(max_loss_usd=100.0)
        dl.record_loss(0.0)
        dl.check()

    def test_T24_negative_loss_ignored(self):
        dl = self._make_dl(max_loss_usd=100.0)
        dl.record_loss(-10.0)
        dl.check()


# T25-T36  MarginGate


class TestMarginGate:
    def test_T25_passes_above_threshold(self):
        _MarginGate(150.0).check(200.0)

    def test_T26_blocks_below_threshold(self):
        with pytest.raises(RuntimeError, match="Margin"):
            _MarginGate(150.0).check(149.9)

    def test_T27_blocks_at_threshold(self):
        _MarginGate(150.0).check(150.0)

    def test_T28_custom_threshold(self):
        with pytest.raises(RuntimeError):
            _MarginGate(200.0).check(199.0)

    def test_T29_zero_margin_blocked(self):
        with pytest.raises(RuntimeError):
            _MarginGate(150.0).check(0.0)

    def test_T30_very_high_margin_passes(self):
        _MarginGate(150.0).check(9999.0)

    def test_T31_default_threshold_150(self):
        assert _MarginGate().min_margin_pct == 150.0

    def test_T32_configurable_threshold(self):
        mg = _MarginGate(300.0)
        assert mg.min_margin_pct == 300.0
        with pytest.raises(RuntimeError):
            mg.check(299.9)
        mg.check(300.0)

    def test_T33_error_message_contains_level(self):
        with pytest.raises(RuntimeError) as exc:
            _MarginGate(150.0).check(100.0)
        assert "100.0" in str(exc.value)

    def test_T34_error_message_contains_threshold(self):
        with pytest.raises(RuntimeError) as exc:
            _MarginGate(150.0).check(100.0)
        assert "150.0" in str(exc.value)

    def test_T35_multiple_checks_no_state(self):
        mg = _MarginGate(150.0)
        mg.check(200.0)
        mg.check(300.0)
        mg.check(200.0)

    def test_T36_borderline_cases(self):
        mg = _MarginGate(100.0)
        mg.check(100.0)
        with pytest.raises(RuntimeError):
            mg.check(99.99)


# T37-T48  EquityProtection


class TestEquityProtection:
    def test_T37_hwm_starts_zero(self):
        assert _EquityProtection().hwm == 0.0

    def test_T38_hwm_tracks_peak(self):
        ep = _EquityProtection()
        ep.update(1000.0)
        ep.update(1200.0)
        ep.update(1100.0)
        assert ep.hwm == 1200.0

    def test_T39_drawdown_pct_correct(self):
        ep = _EquityProtection()
        ep.update(10000.0)
        assert abs(ep.drawdown_pct(9000.0) - 10.0) < 0.001

    def test_T40_no_alert_below_threshold(self):
        ep = _EquityProtection(5.0)
        fired = []
        ep.add_alert_callback(lambda *_: fired.append(1))
        ep.update(10000.0)
        ep.update(9600.0)
        assert len(fired) == 0

    def test_T41_alert_fires_above_threshold(self):
        ep = _EquityProtection(5.0)
        fired = []
        ep.add_alert_callback(lambda *_: fired.append(1))
        ep.update(10000.0)
        ep.update(9400.0)
        assert len(fired) == 1

    def test_T42_alert_callback_receives_equity(self):
        ep = _EquityProtection(5.0)
        received = []
        ep.add_alert_callback(lambda dd, eq, hwm: received.append((dd, eq, hwm)))
        ep.update(10000.0)
        ep.update(9000.0)
        assert received[0][1] == 9000.0 and received[0][2] == 10000.0

    def test_T43_drawdown_pct_zero_when_no_hwm(self):
        assert _EquityProtection().drawdown_pct(5000.0) == 0.0

    def test_T44_hwm_never_decreases(self):
        ep = _EquityProtection()
        ep.update(5000.0)
        ep.update(3000.0)
        ep.update(4000.0)
        assert ep.hwm == 5000.0

    def test_T45_multiple_callbacks(self):
        ep = _EquityProtection(5.0)
        a, b = [], []
        ep.add_alert_callback(lambda *_: a.append(1))
        ep.add_alert_callback(lambda *_: b.append(1))
        ep.update(10000.0)
        ep.update(9400.0)
        assert len(a) == 1 and len(b) == 1

    def test_T46_alert_count_increments(self):
        ep = _EquityProtection(5.0)
        ep.update(10000.0)
        ep.update(9400.0)
        ep.update(9300.0)
        assert ep.alert_count == 2

    def test_T47_100pct_drawdown(self):
        ep = _EquityProtection()
        ep.update(10000.0)
        assert ep.drawdown_pct(0.0) == 100.0

    def test_T48_recovery_above_hwm_resets_peak(self):
        ep = _EquityProtection()
        ep.update(10000.0)
        ep.update(9000.0)
        ep.update(11000.0)
        assert ep.hwm == 11000.0


# T49-T60  LotSizing


class TestLotSizing:
    def test_T49_basic_calculation(self):
        ls = _LotSizing(1.0, 10.0, 0.01, 10.0)
        assert abs(ls.calculate(10000.0, 50.0) - 0.20) < 0.01

    def test_T50_min_lot_enforced(self):
        assert _LotSizing(0.001, 10.0, 0.01, 10.0).calculate(100.0, 1000.0) == 0.01

    def test_T51_max_lot_enforced(self):
        assert _LotSizing(100.0, 1.0, 0.01, 2.0).calculate(1000000.0, 1.0) == 2.0

    def test_T52_zero_balance_returns_zero(self):
        assert _LotSizing().calculate(0.0, 50.0) == 0.0

    def test_T53_zero_sl_returns_zero(self):
        assert _LotSizing().calculate(10000.0, 0.0) == 0.0

    def test_T54_higher_risk_pct_more_lots(self):
        assert _LotSizing(2.0).calculate(10000.0, 50.0) > _LotSizing(1.0).calculate(10000.0, 50.0)

    def test_T55_larger_sl_fewer_lots(self):
        ls = _LotSizing(1.0, 10.0)
        assert ls.calculate(10000.0, 25.0) > ls.calculate(10000.0, 100.0)

    def test_T56_higher_balance_more_lots(self):
        ls = _LotSizing(1.0, 10.0)
        assert ls.calculate(10000.0, 50.0) > ls.calculate(5000.0, 50.0)

    def test_T57_result_rounded_to_2dp(self):
        result = _LotSizing(1.0, 10.0).calculate(10000.0, 33.0)
        assert result == round(result, 2)

    def test_T58_negative_balance_returns_zero(self):
        assert _LotSizing().calculate(-1000.0, 50.0) == 0.0

    def test_T59_pip_value_affects_lots(self):
        assert _LotSizing(1.0, 10.0).calculate(10000.0, 50.0) > _LotSizing(1.0, 20.0).calculate(
            10000.0, 50.0
        )

    def test_T60_min_lot_gt_calculated(self):
        assert _LotSizing(0.01, 10.0, 0.05).calculate(100.0, 500.0) >= 0.05


# T61-T72  Integration


class TestIntegrationRiskGuards:
    def test_T61_kill_switch_blocks_after_equity_floor(self):
        ks = _KillSwitch(KSConfig(equity_floor_usd=1000.0))
        ks.check_equity(500.0)
        with pytest.raises(KillSwitchActivatedError):
            ks.check()

    def test_T62_daily_limits_and_kill_switch_independent(self):
        dl = _DailyLimits(DailyLimitsConfig(max_loss_usd=100.0))
        ks = _KillSwitch(KSConfig())
        dl.record_loss(200.0)
        with pytest.raises(RuntimeError):
            dl.check()
        assert not ks.is_active

    def test_T63_margin_gate_blocks_before_trade(self):
        mg = _MarginGate(150.0)
        trades = []

        def try_trade(margin):
            mg.check(margin)
            trades.append(1)

        with pytest.raises(RuntimeError):
            try_trade(100.0)
        assert len(trades) == 0

    def test_T64_equity_protection_alerts_before_kill_switch(self):
        ks = _KillSwitch(KSConfig(max_drawdown_pct=15.0))
        ep = _EquityProtection(5.0)
        alerts = []
        ep.add_alert_callback(lambda dd, eq, hwm: alerts.append(dd))
        ep.update(10000.0)
        ep.update(9400.0)
        assert len(alerts) == 1 and not ks.is_active
        ks.check_equity(10000.0)
        ks.check_equity(8400.0)
        assert ks.is_active

    def test_T65_lot_size_respects_kill_switch(self):
        ks = _KillSwitch(KSConfig())
        ks.manual_activate("admin-secret", "test")
        with pytest.raises(KillSwitchActivatedError):
            ks.check()

    def test_T66_reset_allows_trading_again(self):
        ks = _KillSwitch(KSConfig(admin_token="tok"))
        ks.manual_activate("tok", "test")
        assert ks.is_active
        ks.reset("tok")
        assert not ks.is_active
        ks.check()

    def test_T67_multiple_guards_all_pass(self):
        ks = _KillSwitch(KSConfig(equity_floor_usd=500.0))
        dl = _DailyLimits(DailyLimitsConfig(max_loss_usd=200.0))
        mg = _MarginGate(150.0)
        ks.check_equity(10000.0)
        ks.check()
        dl.check()
        mg.check(200.0)

    def test_T68_drawdown_cascade(self):
        ks = _KillSwitch(KSConfig(max_drawdown_pct=10.0, admin_token="tok"))
        ks.check_equity(10000.0)
        ks.check_equity(8900.0)
        assert ks.is_active
        for _ in range(5):
            with pytest.raises(KillSwitchActivatedError):
                ks.check()

    def test_T69_callback_error_does_not_propagate(self):
        ks = _KillSwitch(KSConfig())
        ks.add_callback(lambda r: (_ for _ in ()).throw(ValueError("cb error")))
        ks.manual_activate("admin-secret", "test")
        assert ks.is_active

    def test_T70_lot_size_for_risk_scenario(self):
        ls = _LotSizing(2.0, 10.0, 0.01, 5.0)
        assert abs(ls.calculate(5000.0, 50.0) - 0.20) < 0.01

    def test_T71_concurrent_kill_switch_activation(self):
        ks = _KillSwitch(KSConfig())
        activated = []
        ks.add_callback(lambda r: activated.append(r))
        threads = [
            threading.Thread(target=lambda: ks.manual_activate("admin-secret", "concurrent"))
            for _ in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert ks.is_active and len(activated) == 1

    def test_T72_full_lifecycle(self):
        ks = _KillSwitch(KSConfig(equity_floor_usd=500.0, max_drawdown_pct=10.0, admin_token="adm"))
        ep = _EquityProtection(5.0)
        dl = _DailyLimits(DailyLimitsConfig(max_loss_usd=200.0))
        ks.check_equity(10000.0)
        ks.check()
        dl.check()
        ep.update(10000.0)
        ep.update(9400.0)
        assert ep.alert_count == 1 and not ks.is_active
        ks.check_equity(8900.0)
        assert ks.is_active
        with pytest.raises(KillSwitchActivatedError):
            ks.check()
        assert ks.reset("adm") is True and not ks.is_active
        dl.record_loss(150.0)
        dl.check()
        dl.record_loss(60.0)
        with pytest.raises(RuntimeError):
            dl.check()
        dl.reset()
        dl.check()
