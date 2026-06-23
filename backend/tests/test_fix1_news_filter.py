"""
backend/tests/test_fix1_news_filter.py
FIX #1 — Real News Filter Gate — 25 tests — >=90% coverage
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'risk'))
from news_filter import NewsEvent, NewsFilterGate, NewsImpact, NewsBlockResult
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

def _now():
    return datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC)

def _event(delta_s, currency="USD", impact=NewsImpact.HIGH, title="NFP"):
    et = _now() + timedelta(seconds=delta_s)
    return NewsEvent(title=title, currency=currency, impact=impact, event_time=et)

def _gate(**kw):
    return NewsFilterGate(block_minutes_before=30, block_minutes_after=15, clock=_now, **kw)

def test_no_events_not_blocked():
    gate = _gate()
    r = gate.check("EURUSD")
    assert not r.blocked

def test_blocks_inside_window():
    gate = _gate()
    gate.load_events([_event(delta_s=0)])
    r = gate.check("EURUSD")
    assert r.blocked and r.reason == "NEWS_EVENT_BLOCK"

def test_not_blocked_outside_window():
    gate = _gate()
    gate.load_events([_event(delta_s=-(31*60))])
    assert not gate.check("EURUSD").blocked

def test_multiple_events_first_match():
    gate = _gate()
    gate.load_events([_event(delta_s=3600, currency="EUR"), _event(delta_s=60, currency="USD")])
    r = gate.check("EURUSD")
    assert r.blocked and r.event_currency == "USD"

def test_currency_filter_no_match():
    gate = _gate()
    gate.load_events([_event(delta_s=0, currency="JPY")])
    assert not gate.check("EURUSD").blocked

def test_currency_all_blocks_any():
    gate = _gate()
    gate.load_events([_event(delta_s=0, currency="ALL")])
    for sym in ["EURUSD", "XAUUSD", "BTCUSD", "US30"]:
        assert gate.check(sym).blocked

def test_failsafe_provider_exception():
    gate = _gate()
    gate._events = [None, None]
    r = gate.check("EURUSD")
    assert not r.blocked

def test_load_events_rejects_invalid():
    gate = _gate()
    gate.load_events(["bad", 42, None, _event(0)])
    assert gate.event_count() == 1

def test_clear_events():
    gate = _gate()
    gate.load_events([_event(0)])
    gate.clear_events()
    assert not gate.check("EURUSD").blocked

def test_add_event():
    gate = _gate()
    assert gate.event_count() == 0
    gate.add_event(_event(0))
    assert gate.event_count() == 1

def test_upcoming_events():
    gate = _gate()
    e1 = _event(delta_s=10*60, currency="USD")
    e2 = _event(delta_s=90*60, currency="USD")
    e3 = _event(delta_s=-(5*60), currency="USD")
    gate.load_events([e1, e2, e3])
    upcoming = gate.upcoming_events("EURUSD", lookahead_minutes=60, now=_now())
    assert e1 in upcoming and e2 not in upcoming and e3 not in upcoming

def test_naive_datetime_normalised():
    ev = NewsEvent(title="T", currency="USD", impact="HIGH", event_time=datetime(2026,6,23,8,30,0))
    assert ev.event_time.tzinfo == UTC

def test_block_at_exact_start_of_window():
    gate = _gate()
    gate.load_events([_event(delta_s=30*60, currency="USD")])
    assert gate.check("EURUSD").blocked

def test_block_at_exact_end_of_window():
    gate = _gate()
    gate.load_events([_event(delta_s=-(15*60), currency="USD")])
    assert gate.check("EURUSD").blocked

def test_not_blocked_before_window():
    gate = _gate()
    gate.load_events([_event(delta_s=30*60+1, currency="USD")])
    assert not gate.check("EURUSD").blocked

def test_not_blocked_after_window():
    gate = _gate()
    gate.load_events([_event(delta_s=-(15*60+1), currency="USD")])
    assert not gate.check("EURUSD").blocked

def test_impact_filter_low_no_block():
    gate = NewsFilterGate(min_impact=NewsImpact.HIGH, clock=_now)
    gate.load_events([_event(delta_s=0, impact=NewsImpact.LOW)])
    assert not gate.check("EURUSD").blocked

def test_fomc_always_blocks():
    gate = NewsFilterGate(min_impact=NewsImpact.LOW, clock=_now)
    gate.load_events([_event(delta_s=0, impact=NewsImpact.FOMC)])
    assert gate.check("EURUSD").blocked

def test_refresh_no_provider():
    assert asyncio.run(_gate().refresh_from_provider()) is False

def test_refresh_provider_timeout():
    class Slow:
        async def fetch(self, d):
            await asyncio.sleep(999)
            return []
    gate = NewsFilterGate(provider=Slow(), refresh_interval_s=0, clock=_now)
    gate.load_events([_event(0)])
    assert asyncio.run(gate.refresh_from_provider(force=True)) is False
    assert gate.event_count() == 1

def test_block_result_fields():
    gate = _gate()
    gate.load_events([_event(delta_s=60, title="NFP Release")])
    r = gate.check("EURUSD")
    assert r.blocked and r.event_title == "NFP Release" and r.event_time is not None

def test_minutes_to_event_positive_future():
    gate = _gate()
    gate.load_events([_event(delta_s=10*60, currency="USD")])
    r = gate.check("EURUSD")
    assert r.blocked and r.minutes_to_event > 0

def test_minutes_to_event_negative_past():
    gate = _gate()
    gate.load_events([_event(delta_s=-(5*60), currency="USD")])
    r = gate.check("EURUSD")
    assert r.blocked and r.minutes_to_event < 0

def test_multiple_events_currency_isolation():
    gate = _gate()
    gate.load_events([_event(delta_s=0, currency="JPY", title="JPY"), _event(delta_s=0, currency="USD", title="USD")])
    assert gate.check("USDJPY").blocked

def test_volatility_filter_news_delegation():
    import importlib.util, pathlib
    p = pathlib.Path(__file__).parent.parent / 'risk' / 'volatility_filter.py'
    spec = importlib.util.spec_from_file_location('vf', p)
    vf_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vf_mod)
    cfg = vf_mod.VolatilityFilterConfig(enable_news_filter=True,
        news_block_minutes_before=30, news_block_minutes_after=15)
    vf = vf_mod.VolatilityFilter(cfg)
    ev = vf_mod.NewsEvent(title='CPI', currency='USD', impact='HIGH',
        event_time=datetime.now(UTC))
    vf.add_news_event(ev)
    r = vf.check(1.0, [1.0]*14, 0.0002, 0.0002, 'EURUSD')
    assert not r.can_trade and 'NEWS_EVENT_BLOCK' in r.reason

if __name__ == '__main__':
    tests = [
        test_no_events_not_blocked, test_blocks_inside_window,
        test_not_blocked_outside_window, test_multiple_events_first_match,
        test_currency_filter_no_match, test_currency_all_blocks_any,
        test_failsafe_provider_exception, test_load_events_rejects_invalid,
        test_clear_events, test_add_event, test_upcoming_events,
        test_naive_datetime_normalised, test_block_at_exact_start_of_window,
        test_block_at_exact_end_of_window, test_not_blocked_before_window,
        test_not_blocked_after_window, test_impact_filter_low_no_block,
        test_fomc_always_blocks, test_refresh_no_provider,
        test_refresh_provider_timeout, test_block_result_fields,
        test_minutes_to_event_positive_future, test_minutes_to_event_negative_past,
        test_multiple_events_currency_isolation, test_volatility_filter_news_delegation,
    ]
    ok = fail = 0
    for t in tests:
        try:
            t(); ok += 1; print(f'PASS {t.__name__}')
        except Exception as e:
            fail += 1; print(f'FAIL {t.__name__}: {e}')
    print(f'\n{ok}/{len(tests)} PASS  {fail} FAIL')
    sys.exit(fail)
