"""Intelligence package — ML Engine + patches."""
from .ml_engine import MLEngine, MLPrediction, TrainingResult, ModelType, DriftStatus
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
