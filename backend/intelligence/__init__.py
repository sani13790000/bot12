"""Intelligence package — ML Engine + patches."""

from .ml_engine import DriftStatus, MLEngine, MLPrediction, ModelType, TrainingResult

try:
    from . import ml_engine_patch  # noqa: F401  — applies drift_status fix
except Exception:
    pass

__all__ = [
    "MLEngine",
    "MLPrediction",
    "TrainingResult",
    "ModelType",
    "DriftStatus",
]
