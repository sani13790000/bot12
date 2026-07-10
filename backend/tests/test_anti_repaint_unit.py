"""Unit tests for backend/trading/anti_repaint.py.

Covers the AntiRepaintValidator lookahead / repaint detection logic:
CLEAN, SUSPICIOUS and CONFIRMED classification paths, future-data and
bar-index violations, replay hash comparison, feature hashing and the
RepaintError wrapper.
"""
from __future__ import annotations

from backend.trading.anti_repaint import (
    AntiRepaintValidator,
    FeatureSnapshot,
    RepaintError,
    RepaintResult,
    RepaintRisk,
    SignalRecord,
)

BAR_CLOSE = 1_000.0


def _feature(name="rsi", value=1.0, timestamp=BAR_CLOSE - 1.0, bar_index=10):
    return FeatureSnapshot(name=name, value=value, timestamp=timestamp, bar_index=bar_index)


def _record(generated_at, features=None, bar_index=10, signal_id="sig-1", input_hash=""):
    return SignalRecord(
        signal_id=signal_id,
        generated_at=generated_at,
        bar_close_time=BAR_CLOSE,
        bar_index=bar_index,
        features=features if features is not None else [_feature()],
        input_hash=input_hash,
    )


class TestClassification:
    def test_clean_signal(self):
        v = AntiRepaintValidator(confirmation_delay_s=1.0, max_future_tolerance_s=0.5)
        rec = _record(generated_at=BAR_CLOSE + 2.0)
        res = v.validate(rec)
        assert isinstance(res, RepaintResult)
        assert res.risk is RepaintRisk.CLEAN
        assert res.confidence == 1.0
        assert res.issues == []
        assert res.metadata["confirmation_lag_s"] == 2.0

    def test_suspicious_when_lag_below_delay(self):
        v = AntiRepaintValidator(confirmation_delay_s=1.0, max_future_tolerance_s=0.5)
        rec = _record(generated_at=BAR_CLOSE + 0.4)
        res = v.validate(rec)
        assert res.risk is RepaintRisk.SUSPICIOUS
        assert res.confidence == 0.5
        assert any("SUSPICIOUS" in i for i in res.issues)

    def test_confirmed_lookahead(self):
        v = AntiRepaintValidator(confirmation_delay_s=1.0, max_future_tolerance_s=0.5)
        rec = _record(generated_at=BAR_CLOSE - 2.0)
        res = v.validate(rec)
        assert res.risk is RepaintRisk.CONFIRMED
        assert res.confidence == 0.95
        assert any("LOOKAHEAD" in i for i in res.issues)

    def test_future_feature_data(self):
        v = AntiRepaintValidator(confirmation_delay_s=1.0, max_future_tolerance_s=0.5)
        feats = [_feature(name="future_feat", timestamp=BAR_CLOSE + 5.0)]
        rec = _record(generated_at=BAR_CLOSE + 2.0, features=feats)
        res = v.validate(rec)
        assert res.risk is RepaintRisk.CONFIRMED
        assert "future_feat" in res.metadata["future_features"]
        assert any("FUTURE DATA" in i for i in res.issues)

    def test_bar_index_violation(self):
        v = AntiRepaintValidator(confirmation_delay_s=1.0, max_future_tolerance_s=0.5)
        feats = [_feature(name="peek", bar_index=99)]
        rec = _record(generated_at=BAR_CLOSE + 2.0, features=feats, bar_index=10)
        res = v.validate(rec)
        assert res.risk is RepaintRisk.CONFIRMED
        assert "peek" in res.metadata["index_violation"]
        assert any("INDEX VIOLATION" in i for i in res.issues)


class TestReplay:
    def test_replay_hash_match_stays_clean(self):
        v = AntiRepaintValidator(confirmation_delay_s=1.0, max_future_tolerance_s=0.5)
        feats = [_feature(name="rsi", value=1.0)]
        input_hash = AntiRepaintValidator._hash_features(feats)
        rec = _record(generated_at=BAR_CLOSE + 2.0, features=feats, input_hash=input_hash)
        v.register_replay("sig-1", {"rsi": 1.0})
        res = v.validate(rec)
        assert res.risk is RepaintRisk.CLEAN
        assert "hash_mismatch" not in res.metadata

    def test_replay_hash_mismatch_flags_repaint(self):
        v = AntiRepaintValidator(confirmation_delay_s=1.0, max_future_tolerance_s=0.5)
        feats = [_feature(name="rsi", value=1.0)]
        input_hash = AntiRepaintValidator._hash_features(feats)
        rec = _record(generated_at=BAR_CLOSE + 2.0, features=feats, input_hash=input_hash)
        v.register_replay("sig-1", {"rsi": 2.0})  # changed input
        res = v.validate(rec)
        assert res.risk is RepaintRisk.CONFIRMED
        assert "hash_mismatch" in res.metadata
        assert any("REPAINT CONFIRMED" in i for i in res.issues)


class TestCaptureAndBulk:
    def test_capture_records_history_and_hash(self):
        v = AntiRepaintValidator()
        feats = [_feature(name="a", value=1.0), _feature(name="b", value=2.0)]
        rec = v.capture("sig-x", BAR_CLOSE, 10, feats, direction="BUY", score=0.7)
        assert rec.signal_id == "sig-x"
        assert rec.direction == "BUY"
        assert rec.score == 0.7
        # generated_at stamped to "now" -> well after the bar close
        assert rec.generated_at > BAR_CLOSE
        assert rec.input_hash == AntiRepaintValidator._hash_features(feats)
        assert v._history["sig-x"] is rec

    def test_bulk_validate_returns_result_per_signal(self):
        v = AntiRepaintValidator(confirmation_delay_s=1.0, max_future_tolerance_s=0.5)
        clean = _record(generated_at=BAR_CLOSE + 2.0, signal_id="clean")
        bad = _record(generated_at=BAR_CLOSE - 2.0, signal_id="bad")
        out = v.bulk_validate([clean, bad])
        assert set(out) == {"clean", "bad"}
        assert out["clean"].risk is RepaintRisk.CLEAN
        assert out["bad"].risk is RepaintRisk.CONFIRMED


class TestHashing:
    def test_hash_is_order_independent(self):
        a = [_feature(name="x", value=1.0), _feature(name="y", value=2.0)]
        b = [_feature(name="y", value=2.0), _feature(name="x", value=1.0)]
        assert AntiRepaintValidator._hash_features(a) == AntiRepaintValidator._hash_features(b)

    def test_hash_features_matches_raw(self):
        feats = [_feature(name="x", value=1.0), _feature(name="y", value=2.0)]
        assert (
            AntiRepaintValidator._hash_features(feats)
            == AntiRepaintValidator._hash_features_raw({"x": 1.0, "y": 2.0})
        )


class TestRepaintError:
    def test_repaint_error_carries_result_and_message(self):
        res = RepaintResult(
            signal_id="sig-err",
            risk=RepaintRisk.CONFIRMED,
            confidence=0.95,
            issues=["LOOKAHEAD"],
        )
        err = RepaintError(res)
        assert err.result is res
        assert "sig-err" in str(err)
        assert "LOOKAHEAD" in str(err)
