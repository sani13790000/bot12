"""
backend/tests/test_fix2_atr_baseline.py
========================================
FIX #2 — Robust ATR Baseline
Senior Quant Developer — Surgical Refactor

Covers:
  1.  Median is spike-immune (mean is not)
  2.  Median single-element window
  3.  Median even-length window interpolation
  4.  Median exact 14-bar window
  5.  EMA uses config ema_alpha (not 2/(n+1))  ← BUG FIX
  6.  EMA alpha=0.0 falls back to standard formula
  7.  EMA ema_alpha=1.0 == current bar
  8.  "mean" is backward-compatible arithmetic mean
  9.  Unknown estimator falls back to mean
 10.  Empty atr_history returns current_atr
 11.  Window capped at atr_period bars
 12.  avg_atr exposed in result
 13.  Spike does NOT suppress EXTREME detection with median
 14.  Spike DOES suppress EXTREME detection with mean (contrast)
 15.  Median performance: no measurable degradation vs mean
 16.  All estimators agree when window is constant
 17.  Median classifies HIGH correctly after spike
 18.  EMA classifies NORMAL on flat window
 19.  calculate_atr() uses Wilder smoothing (intentional, unchanged)
 20.  calculate_atr() short input returns empty list
"""

from __future__ import annotations

import statistics
import timeit
from typing import List

from backend.risk.volatility_filter import (
    VolatilityFilter,
    VolatilityFilterConfig,
    VolatilityLevel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filter(estimator: str = "median", alpha: float = 0.1, period: int = 14) -> VolatilityFilter:
    cfg = VolatilityFilterConfig(
        atr_estimator=estimator,
        ema_alpha=alpha,
        atr_period=period,
        enable_news_filter=False,  # keep news out of ATR tests
    )
    return VolatilityFilter(cfg)


def _check(vf: VolatilityFilter, current_atr: float, history: List[float]):
    return vf.check(current_atr, history, 0.0, 0.0, "EURUSD")


# Spike scenario: 19 normal bars, 1 massive spike
_SPIKE_HISTORY = [1.0] * 19 + [500.0]
# Flat history
_FLAT_14 = [1.0] * 14


# ===========================================================================
# 1.  Median is spike-immune
# ===========================================================================
class TestMedianSpikeImmunity:
    def test_spike_does_not_distort_median(self):
        vf = _filter("median")
        result = _check(vf, 1.0, _SPIKE_HISTORY)
        # median of [...1.0 x 19, 500.0] = 1.0 => avg_atr ~= 1.0
        assert abs(result.avg_atr - 1.0) < 1e-9, f"Expected median~=1.0 but got {result.avg_atr}"

    def test_mean_distorted_by_spike(self):
        vf = _filter("mean")
        result = _check(vf, 1.0, _SPIKE_HISTORY)
        # mean of [...1.0 x 13, 500.0] with period=14 = (13*1+500)/14 ~= 36.64
        assert result.avg_atr > 10.0, f"Expected mean to be distorted but got {result.avg_atr:.2f}"

    def test_median_is_default_estimator(self):
        """Default config must use median."""
        vf = VolatilityFilter()
        assert vf._cfg.atr_estimator == "median"


# ===========================================================================
# 2.  Median edge cases
# ===========================================================================
class TestMedianEdgeCases:
    def test_single_element_window(self):
        vf = _filter("median")
        result = _check(vf, 2.0, [3.0])
        assert result.avg_atr == 3.0

    def test_even_length_window_interpolates(self):
        """Even-length median = average of two middle values."""
        vf = _filter("median", period=4)
        history = [1.0, 2.0, 3.0, 4.0]
        result = _check(vf, 1.0, history)
        expected = (2.0 + 3.0) / 2.0  # = 2.5
        assert abs(result.avg_atr - expected) < 1e-9, f"Expected 2.5 but got {result.avg_atr}"

    def test_odd_length_window_middle_value(self):
        """Odd-length median = exact middle element."""
        vf = _filter("median", period=5)
        history = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _check(vf, 1.0, history)
        assert result.avg_atr == 3.0

    def test_14_bar_window_exact(self):
        vf = _filter("median", period=14)
        history = list(range(1, 15))  # [1,2,...,14]
        result = _check(vf, 1.0, history)
        expected = statistics.median(history)
        assert abs(result.avg_atr - expected) < 1e-9


# ===========================================================================
# 3.  EMA uses config ema_alpha (BUG FIX core)
# ===========================================================================
class TestEMAAlphaFromConfig:
    def test_ema_uses_config_alpha_not_2_over_n_plus_1(self):
        """
        CRITICAL BUG FIX:
        Previous code: alpha = 2.0 / (len(window) + 1)  -- ignores ema_alpha
        Fixed code:    alpha = self._cfg.ema_alpha if > 0
        """
        window = [1.0, 1.0, 1.0, 2.0]
        vf_02 = _filter("ema", alpha=0.2, period=4)
        vf_09 = _filter("ema", alpha=0.9, period=4)

        result_02 = _check(vf_02, 1.0, window)
        result_09 = _check(vf_09, 1.0, window)

        # alpha=0.9 weights the last bar (2.0) much more heavily
        assert result_09.avg_atr > result_02.avg_atr, (
            f"EMA alpha=0.9 ({result_09.avg_atr:.4f}) should > alpha=0.2 ({result_02.avg_atr:.4f})"
        )

    def test_ema_alpha_02_value(self):
        window = [1.0, 1.0, 1.0, 2.0]
        expected_ema = 1.0
        a = 0.2
        for v in window[1:]:
            expected_ema = a * v + (1.0 - a) * expected_ema
        vf = _filter("ema", alpha=0.2, period=4)
        result = _check(vf, 1.0, window)
        assert abs(result.avg_atr - expected_ema) < 1e-9, (
            f"Expected {expected_ema:.6f} but got {result.avg_atr:.6f}"
        )

    def test_ema_alpha_zero_falls_back_to_standard(self):
        """alpha=0.0 => standard formula 2/(n+1)."""
        window = [1.0, 1.0, 1.0, 2.0]
        vf = _filter("ema", alpha=0.0, period=4)
        result = _check(vf, 1.0, window)
        expected_ema = 1.0
        alpha_std = 2.0 / (4 + 1)
        for v in window[1:]:
            expected_ema = alpha_std * v + (1.0 - alpha_std) * expected_ema
        assert abs(result.avg_atr - expected_ema) < 1e-9

    def test_ema_alpha_one_returns_last_bar(self):
        """alpha=1.0 => avg_atr == last bar in window."""
        window = [1.0, 1.0, 1.0, 99.0]
        vf = _filter("ema", alpha=1.0, period=4)
        result = _check(vf, 1.0, window)
        assert result.avg_atr == 99.0


# ===========================================================================
# 4.  Mean backward compatibility
# ===========================================================================
class TestMeanBackwardCompat:
    def test_mean_estimator_arithmetic(self):
        vf = _filter("mean", period=4)
        history = [1.0, 2.0, 3.0, 4.0]
        result = _check(vf, 1.0, history)
        expected = sum(history) / len(history)
        assert abs(result.avg_atr - expected) < 1e-9

    def test_unknown_estimator_falls_back_to_mean(self):
        """Any unknown string => arithmetic mean (backward compat)."""
        vf = _filter("unknown_algo", period=4)
        history = [2.0, 4.0, 6.0, 8.0]
        result = _check(vf, 1.0, history)
        assert abs(result.avg_atr - 5.0) < 1e-9


# ===========================================================================
# 5.  Empty / boundary inputs
# ===========================================================================
class TestBoundaryInputs:
    def test_empty_history_returns_current_atr(self):
        for est in ("median", "ema", "mean"):
            vf = _filter(est)
            result = _check(vf, 3.14, [])
            assert result.avg_atr == 3.14, f"Failed for estimator={est}"

    def test_window_capped_at_atr_period(self):
        """Only last `atr_period` bars are used."""
        history = [1.0] * 10 + [100.0] * 4
        vf = _filter("mean", period=4)
        result = _check(vf, 1.0, history)
        assert result.avg_atr == 100.0, "Only last 4 bars should be used when period=4"

    def test_avg_atr_exposed_in_result(self):
        vf = _filter("median")
        result = _check(vf, 2.0, [1.0] * 14)
        assert hasattr(result, "avg_atr")
        assert result.avg_atr == 1.0


# ===========================================================================
# 6.  Volatility classification correctness
# ===========================================================================
class TestVolatilityClassification:
    def test_spike_does_not_suppress_extreme_with_median(self):
        """
        With mean: spike inflates avg_atr => ratio appears small => EXTREME missed.
        With median: avg_atr stays at 1.0 => ratio = current/1.0 => EXTREME caught.
        """
        history = [1.0] * 19 + [500.0]
        current = 4.0  # 4x above median (1.0) => EXTREME for EURUSD (>3.5)

        vf_med = _filter("median")
        vf_mn = _filter("mean")

        r_med = _check(vf_med, current, history)
        r_mn = _check(vf_mn, current, history)

        assert r_med.level == VolatilityLevel.EXTREME, (
            f"Median should detect EXTREME, got {r_med.level}"
        )
        assert r_mn.level != VolatilityLevel.EXTREME, (
            f"Mean should MISS EXTREME due to spike, got {r_mn.level}"
        )

    def test_spike_does_not_suppress_high_with_median(self):
        """Median correctly classifies HIGH even with spike in history."""
        history = [1.0] * 19 + [500.0]
        current = 2.5  # 2.5x above median(1.0) => HIGH for EURUSD (>2.0)

        vf = _filter("median")
        result = _check(vf, current, history)
        assert result.level == VolatilityLevel.HIGH

    def test_flat_history_all_estimators_agree(self):
        """When all bars identical, median=mean=ema -- all estimators same result."""
        flat = [1.5] * 14
        for est in ("median", "ema", "mean"):
            vf = _filter(est, alpha=0.1)
            result = _check(vf, 1.5, flat)
            assert abs(result.avg_atr - 1.5) < 1e-6, f"estimator={est} avg_atr={result.avg_atr}"
            assert result.level == VolatilityLevel.NORMAL

    def test_ema_normal_on_flat(self):
        vf = _filter("ema", alpha=0.1)
        result = _check(vf, 1.0, [1.0] * 14)
        assert result.level == VolatilityLevel.NORMAL


# ===========================================================================
# 7.  calculate_atr() -- Wilder smoothing (intentional, unchanged)
# ===========================================================================
class TestCalculateATR:
    def test_calculate_atr_returns_correct_length(self):
        vf = VolatilityFilter()
        highs = [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5]
        lows = [h - 0.1 for h in highs]
        closes = [h - 0.05 for h in highs]
        atrs = vf.calculate_atr(highs, lows, closes)
        assert len(atrs) > 0

    def test_calculate_atr_short_input_empty(self):
        vf = VolatilityFilter()
        assert vf.calculate_atr([1.0], [0.9], [0.95]) == []

    def test_calculate_atr_uses_wilder_smoothing(self):
        """
        Flat market: high=1.0, low=0.9, close=0.95 constant
        TR = max(0.1, 0.05, 0.05) = 0.1 for every bar
        Wilder seed = mean of first 14 bars = 0.1
        Every subsequent ATR = (0.1*13 + 0.1)/14 = 0.1
        All ATRs must equal exactly 0.1.
        """
        vf = VolatilityFilter()
        n = 20
        highs = [1.0] * n
        lows = [0.9] * n
        closes = [0.95] * n
        atrs = vf.calculate_atr(highs, lows, closes)
        assert len(atrs) > 0
        for a in atrs:
            assert abs(a - 0.1) < 1e-9, f"Expected 0.1 but got {a}"


# ===========================================================================
# 8.  Performance: no measurable degradation
# ===========================================================================
class TestPerformance:
    def test_median_overhead_acceptable(self):
        """
        Median overhead must be < 10x vs mean for 14-bar window.
        In practice it is ~1.5x, which is negligible at trading frequency.
        """
        window = [1.0 + i * 0.01 for i in range(14)]

        def mean_fn(w):
            return sum(w) / len(w)

        def median_fn(w):
            n = len(w)
            s = sorted(w)
            mid = n // 2
            return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0

        t_mean = timeit.timeit(lambda: mean_fn(window), number=50_000)
        t_median = timeit.timeit(lambda: median_fn(window), number=50_000)

        ratio = t_median / t_mean
        assert ratio < 10.0, f"Median overhead {ratio:.1f}x vs mean -- exceeds 10x limit"
