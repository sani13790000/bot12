from __future__ import annotations
import asyncio
import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "risk"))
import portfolio_risk as pr
import lot_sizing   as ls

_get_pip_value           = pr._get_pip_value
_get_pip_value_with_src  = pr._get_pip_value_with_source
_get_pip_value_async     = pr._get_pip_value_async
_resolve_canonical       = pr._resolve_canonical
OpenTradeRisk            = pr.OpenTradeRisk
TradeDirection           = pr.TradeDirection
PortfolioRiskManager     = pr.PortfolioRiskManager
RiskLevel                = pr.RiskLevel
FailMode                 = pr.FailMode
PipValueSource           = pr.PipValueSource
_PIP_VALUE_TABLE         = pr._PIP_VALUE_TABLE
_UpdatedTradeProxy       = pr._UpdatedTradeProxy

LotSizer                 = ls.LotSizer
LotSizingConfig          = ls.LotSizingConfig
UnknownSymbolError       = ls.UnknownSymbolError
_LS_PIP_TABLE            = ls._PIP_VALUE_TABLE
_LS_ALIASES              = ls._SYMBOL_ALIASES


def _run(coro):
    return asyncio.run(coro)


def _trade(symbol, lot=1.0, entry=1.10000, sl=1.09000, balance=10_000.0, pip_override=None):
    return OpenTradeRisk(
        symbol=symbol, direction=TradeDirection.BUY,
        lot_size=lot, entry_price=entry, stop_loss=sl,
        account_balance=balance, pip_value_per_lot=pip_override,
    )


# ===========================================================================
# FIX #4-A: Gold pip value
# ===========================================================================
class TestGoldPipValue(unittest.TestCase):
    def test_xauusd_is_1_not_10(self):
        self.assertEqual(_get_pip_value("XAUUSD"), 1.0)
        self.assertNotEqual(_get_pip_value("XAUUSD"), 10.0)

    def test_xauusd_risk_amount_correct(self):
        # lot=1, entry=1900, SL=1895 -> distance=$5, pip_val=1.0 -> risk=$5
        t = _trade("XAUUSD", lot=1.0, entry=1900.00, sl=1895.00, balance=10_000.0)
        self.assertAlmostEqual(t.risk_amount,  5.00, places=4)
        self.assertAlmostEqual(t.risk_percent, 0.05, places=4)

    def test_xauusd_source_is_table(self):
        t = _trade("XAUUSD", entry=1900.0, sl=1895.0)
        self.assertIn(t.pip_value_source, (
            PipValueSource.TABLE, PipValueSource.ALIAS, PipValueSource.SUFFIX,
        ))


# ===========================================================================
# FIX #4-B: Silver pip value — CRITICAL FIX (was 5.0, now 50.0)
# ===========================================================================
class TestSilverPipValue(unittest.TestCase):
    def test_xagusd_is_50_not_5(self):
        """FIX #4: Silver pip_value MUST be 50.0, not 5.0."""
        self.assertEqual(_get_pip_value("XAGUSD"), 50.0)
        self.assertNotEqual(_get_pip_value("XAGUSD"), 5.0)

    def test_xagusd_risk_amount_correct(self):
        """lot=2, entry=25.00, SL=24.50 -> dist=$0.50, pip_val=50.0 -> risk=$50"""
        t = _trade("XAGUSD", lot=2.0, entry=25.00, sl=24.50, balance=10_000.0)
        # price_distance=0.50, lot=2.0, pip_value=50.0 -> 0.50*2.0*50.0 = $50
        self.assertAlmostEqual(t.risk_amount,  50.0, places=4)
        self.assertAlmostEqual(t.risk_percent,  0.5, places=4)

    def test_silver_alias_resolves_to_50(self):
        """'SILVER' alias must give 50.0"""
        self.assertEqual(_get_pip_value("SILVER"), 50.0)

    def test_xagusd_small_sl(self):
        """lot=1, SL=$0.10 -> dist=0.10, pip_val=50 -> risk=$5"""
        t = _trade("XAGUSD", lot=1.0, entry=25.00, sl=24.90, balance=10_000.0)
        self.assertAlmostEqual(t.risk_amount, 5.0, places=4)


# ===========================================================================
# FIX #4-C: Crypto pip value
# ===========================================================================
class TestCryptoPipValue(unittest.TestCase):
    def test_btcusd(self): self.assertEqual(_get_pip_value("BTCUSD"), 1.0)
    def test_ethusd(self): self.assertEqual(_get_pip_value("ETHUSD"), 1.0)
    def test_ltcusd(self): self.assertEqual(_get_pip_value("LTCUSD"), 1.0)
    def test_xrpusd(self): self.assertEqual(_get_pip_value("XRPUSD"), 1.0)

    def test_btc_risk_amount(self):
        # lot=0.1, entry=30000, SL=29500 -> dist=500, pip_val=1.0 -> risk=50
        t = _trade("BTCUSD", lot=0.1, entry=30_000.0, sl=29_500.0, balance=10_000.0)
        self.assertAlmostEqual(t.risk_amount, 50.0, places=4)
        self.assertAlmostEqual(t.risk_percent, 0.5, places=4)


# ===========================================================================
# FIX #4-D: Index pip value
# ===========================================================================
class TestIndexPipValue(unittest.TestCase):
    def test_us30(self):    self.assertEqual(_get_pip_value("US30"),   1.0)
    def test_nas100(self):  self.assertEqual(_get_pip_value("NAS100"), 1.0)
    def test_us500(self):   self.assertEqual(_get_pip_value("US500"),  1.0)
    def test_jpn225(self):  self.assertEqual(_get_pip_value("JPN225"), 0.1)
    def test_ger40(self):   self.assertEqual(_get_pip_value("GER40"),  1.0)
    def test_aus200(self):  self.assertEqual(_get_pip_value("AUS200"), 1.0)

    def test_index_risk_amount(self):
        # lot=1, entry=34000, SL=33950 -> dist=50, pip_val=1.0 -> risk=50
        t = _trade("US30", lot=1.0, entry=34_000.0, sl=33_950.0, balance=10_000.0)
        self.assertAlmostEqual(t.risk_amount, 50.0, places=4)


# ===========================================================================
# FIX #4-E: Forex pip value
# ===========================================================================
class TestForexPipValue(unittest.TestCase):
    def test_eurusd(self):  self.assertEqual(_get_pip_value("EURUSD"), 10.0)
    def test_gbpusd(self):  self.assertEqual(_get_pip_value("GBPUSD"), 10.0)
    def test_usdjpy(self):  self.assertAlmostEqual(_get_pip_value("USDJPY"), 6.7, places=1)
    def test_usdchf(self):  self.assertAlmostEqual(_get_pip_value("USDCHF"), 10.7, places=1)

    def test_eurusd_risk_amount(self):
        # lot=1, entry=1.10000, SL=1.09500 -> dist=0.005, pip_val=10.0 -> risk=0.05
        t = _trade("EURUSD", lot=1.0, entry=1.10000, sl=1.09500, balance=5_000.0)
        self.assertAlmostEqual(t.risk_amount, 0.05, places=4)


# ===========================================================================
# FIX #4-F: Broker suffix stripping
# ===========================================================================
class TestBrokerSuffixStripping(unittest.TestCase):
    def test_xauusdm_stripped(self):
        self.assertEqual(_get_pip_value("XAUUSDm"), 1.0)

    def test_xagusdm_stripped(self):
        """FIX #4: XAGUSDm must resolve to XAGUSD -> 50.0"""
        self.assertEqual(_get_pip_value("XAGUSDm"), 50.0)

    def test_eurusdpro_stripped(self):
        self.assertEqual(_get_pip_value("EURUSDpro"), 10.0)

    def test_btcusdn_stripped(self):
        self.assertEqual(_get_pip_value("BTCUSDn"), 1.0)

    def test_canonical_resolve_suffix(self):
        canonical, method = _resolve_canonical("XAUUSDm")
        self.assertEqual(canonical, "XAUUSD")
        self.assertEqual(method, "suffix")


# ===========================================================================
# FIX #4-G: Alias resolution
# ===========================================================================
class TestAliasResolution(unittest.TestCase):
    def test_gold_alias(self):   self.assertEqual(_get_pip_value("GOLD"),   1.0)
    def test_silver_alias(self): self.assertEqual(_get_pip_value("SILVER"), 50.0)  # FIX #4
    def test_btc_alias(self):    self.assertEqual(_get_pip_value("BTC"),    1.0)
    def test_dax_alias(self):    self.assertEqual(_get_pip_value("DAX"),    1.0)
    def test_nikkei_alias(self): self.assertEqual(_get_pip_value("NIKKEI"), 0.1)

    def test_canonical_resolve_alias(self):
        canonical, method = _resolve_canonical("GOLD")
        self.assertEqual(canonical, "XAUUSD")
        self.assertEqual(method, "alias")

    def test_canonical_resolve_silver_alias(self):
        canonical, method = _resolve_canonical("SILVER")
        self.assertEqual(canonical, "XAGUSD")
        self.assertEqual(method, "alias")


# ===========================================================================
# FIX #4-H: Case insensitive
# ===========================================================================
class TestCaseInsensitive(unittest.TestCase):
    def test_xauusd_lower(self):
        self.assertEqual(_get_pip_value("xauusd"), _get_pip_value("XAUUSD"))

    def test_xagusd_lower(self):
        """FIX #4: xagusd must give 50.0"""
        self.assertEqual(_get_pip_value("xagusd"), 50.0)

    def test_eurusd_mixed(self):
        self.assertEqual(_get_pip_value("EuRuSd"), _get_pip_value("EURUSD"))

    def test_btcusd_lower(self):
        self.assertEqual(_get_pip_value("btcusd"), _get_pip_value("BTCUSD"))


# ===========================================================================
# FIX #4-I: Injected pip value override
# ===========================================================================
class TestInjectedPipValue(unittest.TestCase):
    def test_injected_overrides_gold_table(self):
        val = _get_pip_value("XAUUSD", injected=2.5)
        self.assertEqual(val, 2.5)

    def test_injected_source_is_injected(self):
        pip_val, source = _get_pip_value_with_src("XAUUSD", injected=2.5)
        self.assertEqual(pip_val, 2.5)
        self.assertEqual(source, PipValueSource.INJECTED)

    def test_injected_in_open_trade_risk(self):
        t = _trade("XAUUSD", entry=1900.0, sl=1895.0, pip_override=2.5)
        self.assertEqual(t.pip_value_used, 2.5)
        self.assertEqual(t.pip_value_source, PipValueSource.INJECTED)
        self.assertAlmostEqual(t.risk_amount, 12.5, places=4)


# ===========================================================================
# FIX #4-J: Unknown symbol fallback
# ===========================================================================
class TestUnknownSymbolFallback(unittest.TestCase):
    def test_unknown_usd_pair_gets_10(self):
        val = _get_pip_value("ZZXUSD")
        self.assertEqual(val, 10.0)

    def test_unknown_non_usd_gets_1(self):
        val = _get_pip_value("UNKNOWN_ASSET_XYZ")
        self.assertEqual(val, 1.0)

    def test_unknown_does_not_raise(self):
        try:
            result = _get_pip_value("TOTALLYMADE_UP_SYM")
            self.assertIsInstance(result, float)
            self.assertGreater(result, 0)
        except Exception as e:
            self.fail(f"_get_pip_value raised unexpectedly: {e}")


# ===========================================================================
# FIX #4-K: LotSizer integration (portfolio_risk)
# ===========================================================================
class TestLotSizerIntegration(unittest.TestCase):
    def test_check_async_uses_lot_sizer(self):
        mock_lot_sizer = MagicMock()
        mock_lot_sizer.get_pip_value = AsyncMock(return_value=(2.0, "mt5_tick_value"))
        mgr   = PortfolioRiskManager(lot_sizer=mock_lot_sizer)
        trade = _trade("XAUUSD", lot=1.0, entry=1900.0, sl=1895.0, balance=10_000.0)
        snap  = _run(mgr.check_async(trade, []))
        mock_lot_sizer.get_pip_value.assert_called_once_with("XAUUSD")
        self.assertAlmostEqual(snap.total_risk_percent, 0.1, places=4)

    def test_check_async_lot_sizer_failure_falls_back(self):
        mock_lot_sizer = MagicMock()
        mock_lot_sizer.get_pip_value = AsyncMock(side_effect=RuntimeError("MT5 offline"))
        mgr   = PortfolioRiskManager(lot_sizer=mock_lot_sizer)
        trade = _trade("XAUUSD", lot=1.0, entry=1900.0, sl=1895.0, balance=10_000.0)
        snap  = _run(mgr.check_async(trade, []))
        self.assertAlmostEqual(snap.total_risk_percent, 0.05, places=4)
        self.assertNotEqual(snap.risk_level, RiskLevel.BLOCKED)

    def test_check_async_no_lot_sizer_uses_static(self):
        mgr        = PortfolioRiskManager()
        trade      = _trade("XAUUSD", lot=1.0, entry=1900.0, sl=1895.0, balance=10_000.0)
        snap_sync  = mgr.check(trade, [])
        snap_async = _run(mgr.check_async(trade, []))
        self.assertAlmostEqual(
            snap_sync.total_risk_percent, snap_async.total_risk_percent, places=6
        )

    def test_check_async_same_value_no_rebuild(self):
        mock_lot_sizer = MagicMock()
        mock_lot_sizer.get_pip_value = AsyncMock(return_value=(1.0, "static_table"))
        mgr   = PortfolioRiskManager(lot_sizer=mock_lot_sizer)
        trade = _trade("XAUUSD", lot=1.0, entry=1900.0, sl=1895.0, balance=10_000.0)
        snap  = _run(mgr.check_async(trade, []))
        self.assertAlmostEqual(snap.total_risk_percent, 0.05, places=4)


# ===========================================================================
# FIX #4-L: Sync check backward compatibility
# ===========================================================================
class TestSyncCheckBackwardCompat(unittest.TestCase):
    def test_sync_check_signature_unchanged(self):
        mgr  = PortfolioRiskManager()
        t1   = _trade("EURUSD", lot=1.0, entry=1.10, sl=1.09, balance=10_000.0)
        t2   = _trade("GBPUSD", lot=0.5, entry=1.25, sl=1.24, balance=10_000.0)
        snap = mgr.check(t1, [t2])
        self.assertIsInstance(snap.risk_level,         RiskLevel)
        self.assertIsInstance(snap.can_add_new,        bool)
        self.assertIsInstance(snap.total_risk_percent, float)

    def test_fail_closed_on_internal_error(self):
        mgr   = PortfolioRiskManager(fail_mode=FailMode.FAIL_CLOSED)
        trade = _trade("EURUSD", lot=1.0, entry=1.10, sl=1.09)
        with patch.object(mgr, "_check_inner", side_effect=RuntimeError("boom")):
            snap = mgr.check(trade, [])
        self.assertFalse(snap.can_add_new)
        self.assertEqual(snap.risk_level, RiskLevel.BLOCKED)

    def test_fail_open_allows_on_error(self):
        mgr   = PortfolioRiskManager(fail_mode=FailMode.FAIL_OPEN)
        trade = _trade("EURUSD", lot=1.0, entry=1.10, sl=1.09)
        with patch.object(mgr, "_check_inner", side_effect=RuntimeError("boom")):
            snap = mgr.check(trade, [])
        self.assertTrue(snap.can_add_new)


# ===========================================================================
# FIX #4-M: DRY consistency between portfolio_risk and lot_sizing
# ===========================================================================
class TestDRYConsistency(unittest.TestCase):
    def test_xauusd_tables_match(self):
        self.assertEqual(_PIP_VALUE_TABLE.get("XAUUSD"), _LS_PIP_TABLE.get("XAUUSD"))

    def test_xagusd_tables_match(self):
        """FIX #4: Both tables must have XAGUSD=50.0."""
        self.assertEqual(_PIP_VALUE_TABLE.get("XAGUSD"), 50.0)
        self.assertEqual(_LS_PIP_TABLE.get("XAGUSD"),    50.0)

    def test_aus200_in_both_tables(self):
        """FIX #4: AUS200 added to lot_sizing."""
        self.assertIn("AUS200", _PIP_VALUE_TABLE)
        self.assertIn("AUS200", _LS_PIP_TABLE)

    def test_all_common_symbols_present(self):
        required = [
            "EURUSD", "GBPUSD",
            "XAUUSD", "XAGUSD",
            "BTCUSD", "ETHUSD",
            "US30",   "NAS100", "GER40",
            "USOIL",
        ]
        for sym in required:
            with self.subTest(symbol=sym):
                self.assertIn(sym, _PIP_VALUE_TABLE)
                self.assertIn(sym, _LS_PIP_TABLE)

    def test_pip_value_source_audit(self):
        symbols = ["EURUSD", "XAUUSD", "BTCUSD", "US30", "JPN225", "XAGUSD"]
        for sym in symbols:
            with self.subTest(symbol=sym):
                t = _trade(sym, entry=1000.0, sl=995.0)
                self.assertIsNotNone(t.pip_value_source)
                self.assertNotEqual(t.pip_value_source, "")


# ===========================================================================
# FIX #4-N: LotSizer alias resolution
# ===========================================================================
class TestLotSizerAliasResolution(unittest.TestCase):
    def test_silver_alias_resolves_50(self):
        """LotSizer.get_pip_value('SILVER') must resolve to XAGUSD -> 50.0."""
        sizer = LotSizer()
        val, src = _run(sizer.get_pip_value("SILVER"))
        self.assertEqual(val, 50.0)

    def test_gold_alias_resolves_1(self):
        sizer = LotSizer()
        val, src = _run(sizer.get_pip_value("GOLD"))
        self.assertEqual(val, 1.0)

    def test_btc_alias_resolves_1(self):
        sizer = LotSizer()
        val, src = _run(sizer.get_pip_value("BTC"))
        self.assertEqual(val, 1.0)

    def test_xagusdm_suffix_resolves_50(self):
        """Broker suffix XAGUSDm must resolve to XAGUSD -> 50.0."""
        sizer = LotSizer()
        val, src = _run(sizer.get_pip_value("XAGUSDm"))
        self.assertEqual(val, 50.0)

    def test_dax_alias_resolves_1(self):
        sizer = LotSizer()
        val, src = _run(sizer.get_pip_value("DAX"))
        self.assertEqual(val, 1.0)

    def test_unknown_symbol_raises(self):
        sizer = LotSizer()
        with self.assertRaises(UnknownSymbolError):
            _run(sizer.get_pip_value("TOTALLY_UNKNOWN_XYZ"))


# ===========================================================================
# FIX #4-O: OpenTradeRisk risk percent accuracy
# ===========================================================================
class TestOpenTradeRiskPercent(unittest.TestCase):
    def test_gold_risk_percent(self):
        t = pr.OpenTradeRisk(
            symbol="XAUUSD", direction=TradeDirection.BUY,
            lot_size=1.0, entry_price=1910.0, stop_loss=1900.0,
            account_balance=10_000.0,
        )
        self.assertAlmostEqual(t.risk_amount,  10.0, places=4)
        self.assertAlmostEqual(t.risk_percent,  0.1, places=4)

    def test_silver_risk_percent(self):
        """FIX #4: Silver risk must be 10x higher than before fix."""
        t = pr.OpenTradeRisk(
            symbol="XAGUSD", direction=TradeDirection.BUY,
            lot_size=1.0, entry_price=25.50, stop_loss=25.00,
            account_balance=10_000.0,
        )
        # dist=0.50, pip_val=50.0 -> risk=$25, pct=0.25%
        self.assertAlmostEqual(t.risk_amount,  25.0, places=4)
        self.assertAlmostEqual(t.risk_percent,  0.25, places=4)

    def test_crypto_risk_percent(self):
        t = pr.OpenTradeRisk(
            symbol="BTCUSD", direction=TradeDirection.BUY,
            lot_size=0.1, entry_price=31_000.0, stop_loss=30_000.0,
            account_balance=10_000.0,
        )
        self.assertAlmostEqual(t.risk_amount,  100.0, places=4)
        self.assertAlmostEqual(t.risk_percent,   1.0, places=4)

    def test_index_risk_percent(self):
        t = pr.OpenTradeRisk(
            symbol="NAS100", direction=TradeDirection.SELL,
            lot_size=1.0, entry_price=14_100.0, stop_loss=14_200.0,
            account_balance=10_000.0,
        )
        self.assertAlmostEqual(t.risk_amount,  100.0, places=4)
        self.assertAlmostEqual(t.risk_percent,   1.0, places=4)


# ===========================================================================
# FIX #4-P: Portfolio total risk multi-asset
# ===========================================================================
class TestPortfolioTotalRisk(unittest.TestCase):
    def test_multi_asset_total_risk(self):
        mgr          = PortfolioRiskManager()
        existing_eur = pr.OpenTradeRisk(
            symbol="EURUSD", direction=TradeDirection.BUY,
            lot_size=1.0, entry_price=1.10500, stop_loss=1.09500,
            account_balance=10_000.0,
        )
        existing_gold = pr.OpenTradeRisk(
            symbol="XAUUSD", direction=TradeDirection.BUY,
            lot_size=1.0, entry_price=1910.0, stop_loss=1900.0,
            account_balance=10_000.0,
        )
        new_btc = pr.OpenTradeRisk(
            symbol="BTCUSD", direction=TradeDirection.BUY,
            lot_size=0.1, entry_price=31_000.0, stop_loss=30_000.0,
            account_balance=10_000.0,
        )
        snap = mgr.check(new_btc, [existing_eur, existing_gold])
        self.assertTrue(snap.can_add_new)
        self.assertLess(snap.total_risk_percent, 5.0)

    def test_blocked_when_total_exceeds_5pct(self):
        mgr = PortfolioRiskManager()
        open_trades = [
            pr.OpenTradeRisk("EURUSD", TradeDirection.BUY, 10.0, 1.1, 0.6, 1_000.0)
            for _ in range(4)
        ]
        new_trade = pr.OpenTradeRisk("GBPUSD", TradeDirection.BUY, 10.0, 1.25, 0.75, 1_000.0)
        snap = mgr.check(new_trade, open_trades)
        self.assertFalse(snap.can_add_new)
        self.assertEqual(snap.risk_level, RiskLevel.BLOCKED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
