"""weight_adjuster.py -- Phase P Fix P-6a/b/c/d."""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict
from typing import Dict
import numpy as np
from ..core.logger import get_logger

logger = get_logger("intelligence.weight_adjuster")
_MIN_WEIGHT = 0.05
_MAX_WEIGHT = 0.70
_MAX_DELTA_PER_CYCLE = 0.05

def _to_float(v) -> float:
    """FIX P-6a: safely convert np.float64 to plain float."""
    return float(v)

@dataclass
class IndicatorWeights:
    smc_weight: float = 0.40
    price_action_weight: float = 0.25
    htf_alignment_weight: float = 0.20
    session_weight: float = 0.10
    ltf_weight: float = 0.05
    bos_weight: float = 0.25
    order_block_weight: float = 0.30
    fvg_weight: float = 0.20
    liquidity_weight: float = 0.15
    structure_weight: float = 0.10

    def normalize(self) -> "IndicatorWeights":
        """FIX P-6b: clamp + normalize."""
        main = [max(_MIN_WEIGHT, min(_MAX_WEIGHT, _to_float(x))) for x in [
            self.smc_weight, self.price_action_weight, self.htf_alignment_weight,
            self.session_weight, self.ltf_weight,
        ]]
        total = sum(main) or 1.0
        main = [w / total for w in main]
        smc_total = _to_float(
            self.bos_weight + self.order_block_weight +
            self.fvg_weight + self.liquidity_weight + self.structure_weight
        ) or 1.0
        return IndicatorWeights(
            smc_weight=_to_float(main[0]),
            price_action_weight=_to_float(main[1]),
            htf_alignment_weight=_to_float(main[2]),
            session_weight=_to_float(main[3]),
            ltf_weight=_to_float(main[4]),
            bos_weight=_to_float(self.bos_weight / smc_total),
            order_block_weight=_to_float(self.order_block_weight / smc_total),
            fvg_weight=_to_float(self.fvg_weight / smc_total),
            liquidity_weight=_to_float(self.liquidity_weight / smc_total),
            structure_weight=_to_float(self.structure_weight / smc_total),
        )

    def to_dict(self) -> Dict[str, float]:
        """FIX P-6a: all values cast to float -- safe for JSON."""
        return {k: _to_float(v) for k, v in asdict(self).items()}

    def save(self, path: str) -> None:
        """FIX P-6c: default=float for numpy safety."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=float)
        logger.info("[WeightAdjuster] saved -> %s", path)

    @classmethod
    def load(cls, path: str) -> "IndicatorWeights":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{k: _to_float(v) for k, v in data.items()}).normalize()
        except Exception as exc:
            logger.warning("[WeightAdjuster] load failed: %s", exc)
            return cls()

    def apply_delta(self, key: str, delta: float) -> "IndicatorWeights":
        """FIX P-6d: clamp delta to +/-_MAX_DELTA_PER_CYCLE."""
        clamped = max(-_MAX_DELTA_PER_CYCLE, min(_MAX_DELTA_PER_CYCLE, delta))
        d = self.to_dict()
        if key not in d:
            raise KeyError(f"Unknown weight key: {key}")
        d[key] = _to_float(max(_MIN_WEIGHT, min(_MAX_WEIGHT, d[key] + clamped)))
        return IndicatorWeights(**d).normalize()
