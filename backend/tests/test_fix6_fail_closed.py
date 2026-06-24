import sys, types, importlib.util as _ilu, logging, unittest, os
from unittest.mock import patch
from enum import Enum

def _make_pkg(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    mod.__package__ = name
    sys.modules.setdefault(name, mod)
    return mod

_make_pkg('backend')
_make_pkg('backend.risk')

def _load(alias, path):
    spec = _ilu.spec_from_file_location(alias, path)
    mod  = _ilu.module_from_spec(spec)
    mod.__package__ = 'backend.risk'
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'risk')

_fm_mod = _load('backend.risk.fail_mode',          os.path.join(BASE, 'fail_mode.py'))
_cf_mod = _load('backend.risk.correlation_filter', os.path.join(BASE, 'correlation_filter.py'))
_ec_mod = _load('backend.risk.exposure_control',   os.path.join(BASE, 'exposure_control.py'))

FailMode              = _fm_mod.FailMode
CorrelationFilter     = _cf_mod.CorrelationFilter
CorrelationFilterConfig = _cf_mod.CorrelationFilterConfig
OpenPosition          = _cf_mod.OpenPosition
ExposureControlEngine = _ec_mod.ExposureControlEngine
ExposureControlConfig = _ec_mod.ExposureControlConfig
ExposurePosition      = _ec_mod.ExposurePosition


class TestFailModeCanonical(unittest.TestCase):
    def test_fail_closed_value(self):
        self.assertEqual(FailMode.FAIL_CLOSED, 'FAIL_CLOSED')
    def test_fail_open_value(self):
        self.assertEqual(FailMode.FAIL_OPEN, 'FAIL_OPEN')
    def test_coerce_string(self):
        self.assertIs(_fm_mod.coerce('FAIL_CLOSED'), FailMode.FAIL_CLOSED)
        self.assertIs(_fm_mod.coerce('FAIL_OPEN'), FailMode.FAIL_OPEN)
    def test_coerce_enum_passthrough(self):
        self.assertIs(_fm_mod.coerce(FailMode.FAIL_CLOSED), FailMode.FAIL_CLOSED)
    def test_coerce_lowercase(self):
        self.assertIs(_fm_mod.coerce('fail_closed'), FailMode.FAIL_CLOSED)
    def test_single_source_of_truth(self):
        self.assertIs(_cf_mod.FailMode, _fm_mod.FailMode)
        self.assertIs(_ec_mod.FailMode, _fm_mod.FailMode)


class TestCorrelationFilterNormal(unittest.TestCase):
    def setUp(self):
        self.cf = CorrelationFilter()
    def test_no_positions_passes(self):
        r = self.cf.check('EURUSD', 'BUY', [], 1.0)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, 'NO_OPEN_POSITIONS')
    def test_high_correlation_blocks(self):
        pos = [OpenPosition('GBPUSD', 'BUY', 1.0)]
        r = self.cf.check('EURUSD', 'BUY', pos, 1.0)
        self.assertFalse(r.can_trade)
        self.assertIn('HIGH_CORRELATION', r.reason)
    def test_uncorrelated_passes(self):
        pos = [OpenPosition('XAGUSD', 'BUY', 1.0)]
        r = self.cf.check('USDJPY', 'BUY', pos, 1.0)
        self.assertTrue(r.can_trade)
    def test_default_fail_mode_is_closed(self):
        self.assertIs(self.cf._fail_mode, FailMode.FAIL_CLOSED)


class TestCorrelationFilterFailClosed(unittest.TestCase):
    def test_fail_closed_blocks_on_exception(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('boom')):
            r = cf.check('EURUSD', 'BUY', [], 1.0)
        self.assertFalse(r.can_trade)
        self.assertIn('FAIL_CLOSED', r.reason)
        self.assertIn('CORRELATION_GATE_ERROR', r.reason)
    def test_fail_closed_is_default(self):
        cf = CorrelationFilter()
        with patch.object(cf, '_check_inner', side_effect=ValueError('oops')):
            r = cf.check('EURUSD', 'BUY', [], 1.0)
        self.assertFalse(r.can_trade)
    def test_fail_closed_returns_zero_risk_multiplier(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('x')):
            r = cf.check('EURUSD', 'BUY', [], 2.0)
        self.assertEqual(r.risk_multiplier, 0.0)
        self.assertEqual(r.adjusted_risk_percent, 0.0)
    def test_fail_closed_logs_critical(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('err')):
            with self.assertLogs('risk.correlation_filter', level='CRITICAL'):
                cf.check('EURUSD', 'BUY', [], 1.0)


class TestCorrelationFilterFailOpen(unittest.TestCase):
    def test_fail_open_allows_on_exception(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('crash')):
            r = cf.check('EURUSD', 'BUY', [], 1.0)
        self.assertTrue(r.can_trade)
        self.assertIn('FAIL_OPEN', r.reason)
    def test_fail_open_returns_base_risk(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('x')):
            r = cf.check('EURUSD', 'BUY', [], 2.5)
        self.assertEqual(r.adjusted_risk_percent, 2.5)
        self.assertEqual(r.risk_multiplier, 1.0)
    def test_fail_open_logs_critical(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('err')):
            with self.assertLogs('risk.correlation_filter', level='CRITICAL'):
                cf.check('EURUSD', 'BUY', [], 1.0)
    def test_fail_open_string_accepted(self):
        cf = CorrelationFilter(fail_mode='FAIL_OPEN')
        self.assertIs(cf._fail_mode, FailMode.FAIL_OPEN)


class TestCorrelationFilterConfig(unittest.TestCase):
    def test_config_fail_mode_respected(self):
        cfg = CorrelationFilterConfig(fail_mode=FailMode.FAIL_OPEN)
        cf  = CorrelationFilter(config=cfg)
        self.assertIs(cf._fail_mode, FailMode.FAIL_OPEN)
    def test_kwarg_overrides_config(self):
        cfg = CorrelationFilterConfig(fail_mode=FailMode.FAIL_OPEN)
        cf  = CorrelationFilter(config=cfg, fail_mode=FailMode.FAIL_CLOSED)
        self.assertIs(cf._fail_mode, FailMode.FAIL_CLOSED)
    def test_default_config_fail_mode_is_closed(self):
        cfg = CorrelationFilterConfig()
        self.assertIs(cfg.fail_mode, FailMode.FAIL_CLOSED)


class TestExposureControlNormal(unittest.TestCase):
    def setUp(self):
        self.ec = ExposureControlEngine()
    def test_no_positions_passes(self):
        r = self.ec.check('EURUSD', 'BUY', 1.0, [], 10000)
        self.assertTrue(r.can_trade)
    def test_max_trades_blocks(self):
        pos = [
            ExposurePosition('EURUSD', 'BUY', 1.0, 100),
            ExposurePosition('GBPUSD', 'BUY', 1.0, 100),
            ExposurePosition('AUDUSD', 'BUY', 1.0, 100),
            ExposurePosition('NZDUSD', 'SELL', 1.0, 100),
            ExposurePosition('USDCHF', 'SELL', 1.0, 100),
        ]
        r = self.ec.check('USDJPY', 'BUY', 1.0, pos, 10000)
        self.assertFalse(r.can_trade)
        self.assertIn('MAX_TRADES', r.reason)
    def test_total_exposure_blocks(self):
        pos = [
            ExposurePosition('EURUSD', 'BUY', 2.0, 200),
            ExposurePosition('GBPUSD', 'SELL', 2.0, 200),
        ]
        r = self.ec.check('AUDUSD', 'BUY', 2.0, pos, 10000)
        self.assertFalse(r.can_trade)
        self.assertIn('MAX_EXPOSURE', r.reason)
    def test_default_fail_mode_is_closed(self):
        self.assertIs(self.ec._fail_mode, FailMode.FAIL_CLOSED)


class TestExposureControlFailClosed(unittest.TestCase):
    def test_fail_closed_blocks_on_exception(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError('boom')):
            r = ec.check('EURUSD', 'BUY', 1.0, [], 10000)
        self.assertFalse(r.can_trade)
        self.assertIn('FAIL_CLOSED', r.reason)
        self.assertIn('EXPOSURE_CHECK_ERROR', r.reason)
    def test_fail_closed_is_default(self):
        ec = ExposureControlEngine()
        with patch.object(ec, '_check_inner', side_effect=ValueError('bad')):
            r = ec.check('EURUSD', 'BUY', 1.0, [], 10000)
        self.assertFalse(r.can_trade)
    def test_fail_closed_snapshot_safe(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError('x')):
            r = ec.check('EURUSD', 'BUY', 1.0, [], 10000)
        self.assertIsNotNone(r.snapshot)
        self.assertEqual(r.projected_total_risk, 0.0)
    def test_fail_closed_logs_critical(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError('err')):
            with self.assertLogs('risk.exposure_control', level='CRITICAL'):
                ec.check('EURUSD', 'BUY', 1.0, [], 10000)


class TestExposureControlFailOpen(unittest.TestCase):
    def test_fail_open_allows_on_exception(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError('crash')):
            r = ec.check('EURUSD', 'BUY', 1.5, [], 10000)
        self.assertTrue(r.can_trade)
        self.assertIn('FAIL_OPEN', r.reason)
    def test_fail_open_returns_projected_risk(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError('x')):
            r = ec.check('EURUSD', 'BUY', 2.5, [], 10000)
        self.assertEqual(r.projected_total_risk, 2.5)
    def test_fail_open_logs_critical(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError('err')):
            with self.assertLogs('risk.exposure_control', level='CRITICAL'):
                ec.check('EURUSD', 'BUY', 1.0, [], 10000)
    def test_fail_open_string_accepted(self):
        ec = ExposureControlEngine(fail_mode='FAIL_OPEN')
        self.assertIs(ec._fail_mode, FailMode.FAIL_OPEN)


class TestExposureControlConfig(unittest.TestCase):
    def test_config_fail_mode_respected(self):
        cfg = ExposureControlConfig(fail_mode=FailMode.FAIL_OPEN)
        ec  = ExposureControlEngine(config=cfg)
        self.assertIs(ec._fail_mode, FailMode.FAIL_OPEN)
    def test_kwarg_overrides_config(self):
        cfg = ExposureControlConfig(fail_mode=FailMode.FAIL_OPEN)
        ec  = ExposureControlEngine(config=cfg, fail_mode=FailMode.FAIL_CLOSED)
        self.assertIs(ec._fail_mode, FailMode.FAIL_CLOSED)
    def test_default_config_fail_mode_is_closed(self):
        cfg = ExposureControlConfig()
        self.assertIs(cfg.fail_mode, FailMode.FAIL_CLOSED)


class TestEveryExceptionLogged(unittest.TestCase):
    def test_corr_fail_closed_logs(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('e')):
            with self.assertLogs('risk.correlation_filter', level='CRITICAL'):
                cf.check('EURUSD', 'BUY', [], 1.0)
    def test_corr_fail_open_logs(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('e')):
            with self.assertLogs('risk.correlation_filter', level='CRITICAL'):
                cf.check('EURUSD', 'BUY', [], 1.0)
    def test_expo_fail_closed_logs(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError('e')):
            with self.assertLogs('risk.exposure_control', level='CRITICAL'):
                ec.check('EURUSD', 'BUY', 1.0, [], 10000)
    def test_expo_fail_open_logs(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError('e')):
            with self.assertLogs('risk.exposure_control', level='CRITICAL'):
                ec.check('EURUSD', 'BUY', 1.0, [], 10000)


class TestBackwardCompatibility(unittest.TestCase):
    def test_corr_filter_no_args(self):
        cf = CorrelationFilter()
        self.assertTrue(cf.check('EURUSD', 'BUY', [], 1.0).can_trade)
    def test_corr_filter_config_only(self):
        cfg = CorrelationFilterConfig()
        cf  = CorrelationFilter(config=cfg)
        self.assertTrue(cf.check('USDJPY', 'SELL', [], 1.0).can_trade)
    def test_exposure_engine_no_args(self):
        ec = ExposureControlEngine()
        self.assertTrue(ec.check('EURUSD', 'BUY', 1.0, [], 10000).can_trade)
    def test_exposure_engine_config_only(self):
        cfg = ExposureControlConfig()
        ec  = ExposureControlEngine(config=cfg)
        self.assertTrue(ec.check('EURUSD', 'BUY', 1.0, [], 10000).can_trade)
    def test_get_correlation_filter_singleton(self):
        from backend.risk.correlation_filter import get_correlation_filter
        cf1 = get_correlation_filter()
        cf2 = get_correlation_filter()
        self.assertIs(cf1, cf2)
    def test_get_exposure_control_singleton(self):
        from backend.risk.exposure_control import get_exposure_control
        ec1 = get_exposure_control()
        ec2 = get_exposure_control()
        self.assertIs(ec1, ec2)
    def test_check_result_fields(self):
        ec = ExposureControlEngine()
        r  = ec.check('EURUSD', 'BUY', 1.0, [], 10000)
        self.assertTrue(hasattr(r, 'can_trade'))
        self.assertTrue(hasattr(r, 'reason'))
        self.assertTrue(hasattr(r, 'snapshot'))
        self.assertTrue(hasattr(r, 'projected_total_risk'))
    def test_corr_result_fields(self):
        cf = CorrelationFilter()
        r  = cf.check('EURUSD', 'BUY', [], 1.0)
        self.assertTrue(hasattr(r, 'can_trade'))
        self.assertTrue(hasattr(r, 'correlation_score'))
        self.assertTrue(hasattr(r, 'adjusted_risk_percent'))
        self.assertTrue(hasattr(r, 'risk_multiplier'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
