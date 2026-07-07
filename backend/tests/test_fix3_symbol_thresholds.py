"""
backend/tests/test_fix3_symbol_thresholds.py
============================================
FIX #3 - Symbol-Specific Volatility Thresholds
Senior Quant Developer - Surgical Refactor

Covers:
  1.  Default table covers EURUSD / XAUUSD / BTCUSD with correct values
  2.  Unknown symbol falls back to global config thresholds
  3.  Case-insensitive lookup
  4.  add_symbol_threshold() overrides at runtime
  5.  remove_symbol_threshold() removes entry (falls back to config globals)
  6.  remove_symbol_threshold() on unknown symbol returns False
  7.  get_thresholds() public inspector returns correct tuple
  8.  list_symbol_thresholds() returns snapshot (immutable)
  9.  SymbolThresholds validation: low >= high raises ValueError
 10.  SymbolThresholds validation: high >= extreme raises ValueError
 11.  SymbolThresholds validation: low <= 0 raises ValueError
 12.  Partial config override merges with defaults (does not erase them)
 13.  XAUUSD tight thresholds block EXTREME before EURUSD does
 14.  BTCUSD tightest thresholds - extreme=2.2 fires before EURUSD extreme=3.5
 15.  Forex major: HIGH correctly classified
 16.  Gold: HIGH at ratio that is NORMAL for EURUSD
 17.  Crypto: HIGH at ratio that is NORMAL for EURUSD
 18.  Alias GOLD resolves to XAUUSD thresholds
 19.  Alias BTC resolves to BTCUSD thresholds
 20.  Alias DAX resolves to GER40 thresholds
 21.  Broker suffix XAUUSDm resolves to XAUUSD
 22.  Broker suffix EURUSDpro resolves to EURUSD
 23.  get_thresholds on unknown returns config globals
 24.  Full check() EURUSD - EXTREME at ratio 4.0
 25.  Full check() BTCUSD - EXTREME at ratio 2.5
 26.  Full check() BTCUSD - HIGH at ratio 1.8
 27.  Full check() XAUUSD - not EXTREME at ratio 2.5
 28.  add_symbol_threshold() with invalid type raises TypeError
 29.  SymbolThresholds.as_tuple() returns correct 3-tuple
 30.  Two instances are independent
"""

from __future__ import annotations

import pytest

from backend.risk.volatility_filter import (
    _DEFAULT_SYMBOL_THRESHOLDS,
    SymbolThresholds,
    VolatilityFilter,
    VolatilityFilterConfig,
    VolatilityLevel,
)

# -- helpers -----------------------------------------------------------------


def _make_filter(symbol_thresholds=None, low=0.5, high=2.0, extreme=3.5):
    cfg = VolatilityFilterConfig(
        low_atr_ratio=low,
        high_atr_ratio=high,
        extreme_atr_ratio=extreme,
        symbol_thresholds=symbol_thresholds,
        enable_news_filter=False,
        atr_estimator="mean",
    )
    return VolatilityFilter(cfg)


def _check(vf, symbol, ratio):
    """Check with current_atr=ratio, flat history -> avg_atr=1.0."""
    return vf.check(ratio, [1.0] * 14, 0.0, 0.0, symbol)


# ============================================================================
# 1-2: Default table + unknown fallback
# ============================================================================
class TestDefaultTable:
    def test_eurusd_defaults(self):
        t = _DEFAULT_SYMBOL_THRESHOLDS["EURUSD"]
        assert (t.low, t.high, t.extreme) == (0.5, 2.0, 3.5)

    def test_xauusd_defaults(self):
        t = _DEFAULT_SYMBOL_THRESHOLDS["XAUUSD"]
        assert (t.low, t.high, t.extreme) == (0.7, 1.8, 3.0)

    def test_btcusd_defaults(self):
        t = _DEFAULT_SYMBOL_THRESHOLDS["BTCUSD"]
        assert (t.low, t.high, t.extreme) == (0.8, 1.5, 2.2)

    def test_unknown_symbol_fallback_to_config_globals(self):
        vf = _make_filter(low=0.4, high=1.9, extreme=3.1)
        assert vf.get_thresholds("UNKNOWN_PAIR") == (0.4, 1.9, 3.1)


# ============================================================================
# 3: Case-insensitive
# ============================================================================
class TestCaseInsensitive:
    def test_lowercase_resolves_same_as_uppercase(self):
        vf = _make_filter()
        assert vf.get_thresholds("eurusd") == vf.get_thresholds("EURUSD")

    def test_mixed_case_resolves(self):
        vf = _make_filter()
        assert vf.get_thresholds("EurUsd") == vf.get_thresholds("EURUSD")


# ============================================================================
# 4-6: Runtime add / remove
# ============================================================================
class TestRuntimeAddRemove:
    def test_add_symbol_threshold_overrides(self):
        vf = _make_filter()
        vf.add_symbol_threshold("EURUSD", SymbolThresholds(0.3, 1.5, 2.8))
        assert vf.get_thresholds("EURUSD") == (0.3, 1.5, 2.8)

    def test_remove_symbol_then_falls_back_to_globals(self):
        vf = _make_filter(low=0.4, high=1.7, extreme=3.0)
        vf.add_symbol_threshold("EURUSD", SymbolThresholds(0.3, 1.5, 2.5))
        assert vf.remove_symbol_threshold("EURUSD") is True
        assert vf.get_thresholds("EURUSD") == (0.4, 1.7, 3.0)

    def test_remove_custom_symbol_falls_back_to_globals(self):
        vf = _make_filter(low=0.4, high=1.7, extreme=3.0)
        vf.add_symbol_threshold("CUSTOM_FX", SymbolThresholds(0.3, 1.5, 2.5))
        vf.remove_symbol_threshold("CUSTOM_FX")
        assert vf.get_thresholds("CUSTOM_FX") == (0.4, 1.7, 3.0)

    def test_remove_unknown_returns_false(self):
        assert _make_filter().remove_symbol_threshold("ZZZNOT_REAL") is False


# ============================================================================
# 7-8: Inspectors
# ============================================================================
class TestPublicInspectors:
    def test_get_thresholds_xauusd(self):
        assert _make_filter().get_thresholds("XAUUSD") == (0.7, 1.8, 3.0)

    def test_list_snapshot_immutable(self):
        vf = _make_filter()
        snap = vf.list_symbol_thresholds()
        snap["EURUSD"] = SymbolThresholds(0.1, 0.2, 0.3)
        assert vf.get_thresholds("EURUSD") == (0.5, 2.0, 3.5)

    def test_list_contains_all_defaults(self):
        snap = _make_filter().list_symbol_thresholds()
        for sym in _DEFAULT_SYMBOL_THRESHOLDS:
            assert sym in snap


# ============================================================================
# 9-11: Validation
# ============================================================================
class TestSymbolThresholdsValidation:
    def test_low_ge_high_raises(self):
        with pytest.raises(ValueError, match="low < high < extreme"):
            SymbolThresholds(low=2.0, high=2.0, extreme=3.5)

    def test_high_ge_extreme_raises(self):
        with pytest.raises(ValueError, match="low < high < extreme"):
            SymbolThresholds(low=0.5, high=3.5, extreme=3.5)

    def test_low_zero_raises(self):
        with pytest.raises(ValueError, match="low < high < extreme"):
            SymbolThresholds(low=0.0, high=2.0, extreme=3.5)

    def test_valid_no_error(self):
        assert SymbolThresholds(0.4, 1.9, 3.1).low == 0.4

    def test_as_tuple(self):
        assert SymbolThresholds(0.5, 2.0, 3.5).as_tuple() == (0.5, 2.0, 3.5)


# ============================================================================
# 12: Partial merge
# ============================================================================
class TestPartialConfigMerge:
    def test_partial_override_preserves_other_defaults(self):
        vf = _make_filter(symbol_thresholds={"EURUSD": SymbolThresholds(0.4, 1.8, 3.2)})
        assert vf.get_thresholds("EURUSD") == (0.4, 1.8, 3.2)
        assert vf.get_thresholds("XAUUSD") == (0.7, 1.8, 3.0)
        assert vf.get_thresholds("BTCUSD") == (0.8, 1.5, 2.2)


# ============================================================================
# 13-17: Classifications differ by symbol
# ============================================================================
class TestThresholdDifferences:
    def test_xauusd_extreme_fires_before_eurusd(self):
        vf = _make_filter()
        assert _check(vf, "XAUUSD", 3.1).level == VolatilityLevel.EXTREME
        assert _check(vf, "EURUSD", 3.1).level == VolatilityLevel.HIGH

    def test_btcusd_extreme_fires_much_earlier(self):
        vf = _make_filter()
        assert _check(vf, "BTCUSD", 2.5).level == VolatilityLevel.EXTREME
        assert _check(vf, "EURUSD", 2.5).level == VolatilityLevel.HIGH

    def test_forex_high_classification(self):
        result = _check(_make_filter(), "EURUSD", 2.5)
        assert result.level == VolatilityLevel.HIGH
        assert result.can_trade is True

    def test_gold_high_where_eurusd_normal(self):
        vf = _make_filter()
        assert _check(vf, "EURUSD", 1.85).level == VolatilityLevel.NORMAL
        assert _check(vf, "XAUUSD", 1.85).level == VolatilityLevel.HIGH

    def test_crypto_high_where_eurusd_normal(self):
        vf = _make_filter()
        assert _check(vf, "BTCUSD", 1.6).level == VolatilityLevel.HIGH
        assert _check(vf, "EURUSD", 1.6).level == VolatilityLevel.NORMAL


# ============================================================================
# 18-22: Alias and suffix
# ============================================================================
class TestAliasAndSuffixResolution:
    def test_gold_alias(self):
        vf = _make_filter()
        assert vf.get_thresholds("GOLD") == vf.get_thresholds("XAUUSD")

    def test_btc_alias(self):
        vf = _make_filter()
        assert vf.get_thresholds("BTC") == vf.get_thresholds("BTCUSD")

    def test_dax_alias(self):
        vf = _make_filter()
        assert vf.get_thresholds("DAX") == vf.get_thresholds("GER40")

    def test_broker_suffix_xauusdm(self):
        vf = _make_filter()
        assert vf.get_thresholds("XAUUSDm") == vf.get_thresholds("XAUUSD")

    def test_broker_suffix_eurusdpro(self):
        vf = _make_filter()
        assert vf.get_thresholds("EURUSDpro") == vf.get_thresholds("EURUSD")


# ============================================================================
# 23: Unknown fallback
# ============================================================================
class TestUnknownFallback:
    def test_unknown_uses_config(self):
        vf = _make_filter(low=0.3, high=1.6, extreme=2.9)
        assert vf.get_thresholds("AAPL") == (0.3, 1.6, 2.9)


# ============================================================================
# 24-27: Full check() integration
# ============================================================================
class TestFullCheckIntegration:
    def test_eurusd_extreme_at_4(self):
        r = _check(_make_filter(), "EURUSD", 4.0)
        assert r.level == VolatilityLevel.EXTREME and r.can_trade is False

    def test_btcusd_extreme_at_2_5(self):
        r = _check(_make_filter(), "BTCUSD", 2.5)
        assert r.level == VolatilityLevel.EXTREME and r.can_trade is False

    def test_btcusd_high_at_1_8(self):
        r = _check(_make_filter(), "BTCUSD", 1.8)
        assert r.level == VolatilityLevel.HIGH and r.can_trade is True

    def test_xauusd_not_extreme_at_2_5(self):
        r = _check(_make_filter(), "XAUUSD", 2.5)
        assert r.level == VolatilityLevel.HIGH and r.can_trade is True


# ============================================================================
# 28: TypeError
# ============================================================================
class TestAddInvalidType:
    def test_tuple_raises_type_error(self):
        with pytest.raises(TypeError):
            _make_filter().add_symbol_threshold("EURUSD", (0.5, 2.0, 3.5))


# ============================================================================
# 29: as_tuple
# ============================================================================
class TestAsTuple:
    def test_values(self):
        assert SymbolThresholds(0.7, 1.8, 3.0).as_tuple() == (0.7, 1.8, 3.0)


# ============================================================================
# 30: Instance independence
# ============================================================================
class TestInstanceIndependence:
    def test_two_instances_independent(self):
        vf1, vf2 = _make_filter(), _make_filter()
        vf1.add_symbol_threshold("EURUSD", SymbolThresholds(0.1, 0.2, 0.3))
        assert vf2.get_thresholds("EURUSD") == (0.5, 2.0, 3.5)
