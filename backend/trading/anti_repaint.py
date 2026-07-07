from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class RepaintRisk(str, Enum):
    CLEAN = "CLEAN"
    SUSPICIOUS = "SUSPICIOUS"
    CONFIRMED = "CONFIRMED"
    UNKNOWN = "UNKNOWN"


@dataclass
class FeatureSnapshot:
    name: str
    value: float
    timestamp: float
    bar_index: int


@dataclass
class SignalRecord:
    signal_id: str
    generated_at: float
    bar_close_time: float
    bar_index: int
    features: List[FeatureSnapshot] = field(default_factory=list)
    direction: str = ""
    score: float = 0.0
    input_hash: str = ""


@dataclass(frozen=True)
class RepaintResult:
    signal_id: str
    risk: RepaintRisk
    confidence: float
    issues: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AntiRepaintValidator:
    """Validates signals for lookahead bias / repainting."""

    def __init__(self, confirmation_delay_s: float = 1.0, max_future_tolerance_s: float = 0.5):
        self._delay = confirmation_delay_s
        self._tolerance = max_future_tolerance_s
        self._history: Dict[str, SignalRecord] = {}
        self._replays: Dict[str, List[Dict]] = {}

    def capture(self, signal_id, bar_close_time, bar_index, features, direction="", score=0.0):
        h = self._hash_features(features)
        r = SignalRecord(
            signal_id, time.time(), bar_close_time, bar_index, features, direction, score, h
        )
        self._history[signal_id] = r
        return r

    def validate(self, record: SignalRecord) -> RepaintResult:
        issues = []
        metadata = {}
        risk = RepaintRisk.CLEAN
        lag = record.generated_at - record.bar_close_time
        metadata["confirmation_lag_s"] = round(lag, 3)
        if lag < -self._tolerance:
            issues.append(f"LOOKAHEAD: signal generated {-lag:.2f}s BEFORE bar closed")
            risk = RepaintRisk.CONFIRMED
        elif lag < self._delay:
            issues.append(
                f"SUSPICIOUS: signal generated only {lag:.3f}s after bar close (expected >={self._delay}s)"
            )
            if risk == RepaintRisk.CLEAN:
                risk = RepaintRisk.SUSPICIOUS
        future = [
            f for f in record.features if f.timestamp > record.bar_close_time + self._tolerance
        ]
        if future:
            names = [f.name for f in future]
            issues.append(f"FUTURE DATA: features {names} timestamp > bar_close")
            risk = RepaintRisk.CONFIRMED
            metadata["future_features"] = names
        wrong = [f for f in record.features if f.bar_index > record.bar_index]
        if wrong:
            names = [f.name for f in wrong]
            issues.append(f"INDEX VIOLATION: features {names} have higher bar_index than signal")
            risk = RepaintRisk.CONFIRMED
            metadata["index_violation"] = names
        for replay in self._replays.get(record.signal_id, []):
            rh = self._hash_features_raw(replay)
            if rh != record.input_hash:
                issues.append("REPAINT CONFIRMED: inputs changed between original and replay")
                risk = RepaintRisk.CONFIRMED
                metadata["hash_mismatch"] = {"original": record.input_hash[:16], "replay": rh[:16]}
        conf = {
            RepaintRisk.CLEAN: 1.0,
            RepaintRisk.SUSPICIOUS: 0.5,
            RepaintRisk.CONFIRMED: 0.95,
            RepaintRisk.UNKNOWN: 0.1,
        }[risk]
        if risk != RepaintRisk.CLEAN:
            logger.warning(
                "anti-repaint %s -> %s | %s", record.signal_id, risk.value, "; ".join(issues)
            )
        return RepaintResult(record.signal_id, risk, conf, issues, metadata)

    def register_replay(self, signal_id, replay_features):
        self._replays.setdefault(signal_id, []).append(replay_features)

    def bulk_validate(self, records):
        return {r.signal_id: self.validate(r) for r in records}

    @staticmethod
    def _hash_features(features):
        raw = {f.name: f.value for f in sorted(features, key=lambda x: x.name)}
        return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _hash_features_raw(raw):
        return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


class RepaintError(Exception):
    def __init__(self, result):
        self.result = result
        super().__init__(f"Repaint detected for {result.signal_id}: {result.issues}")
