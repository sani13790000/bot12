"""
Galaxy Vast AI — XGBoost Trainer
Train, validate and optimize XGBoost model for trade success prediction.
"""
from __future__ import annotations
import logging, os, asyncio, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
logger = logging.getLogger(__name__)

@dataclass
class TrainingResult:
    version_id: str; accuracy: float; precision: float; recall: float
    f1_score: float; auc_roc: float; n_samples: int; n_features: int; training_time_s: float
    trained_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    feature_importance: Dict[str, float] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)

class XGBoostTrainer:
    DEFAULT_PARAMS = {
        "n_estimators":200,"max_depth":6,"learning_rate":0.05,
        "subsample":0.8,"colsample_bytree":0.8,"min_child_weight":3,
        "gamma":0.1,"reg_alpha":0.1,"reg_lambda":1.0,
        "objective":"binary:logistic","eval_metric":"auc",
        "use_label_encoder":False,"verbosity":0,
    }
    def __init__(self, model_dir="models", params=None):
        self._dir = model_dir; self._params = {**self.DEFAULT_PARAMS, **(params or {})}
        self._log = logging.getLogger(self.__class__.__name__)
    def _import_deps(self):
        try:
            import xgboost as xgb
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
            return xgb, train_test_split, (accuracy_score, precision_score, recall_score, f1_score, roc_auc_score)
        except ImportError as e:
            raise ImportError(f"required package missing: {e}; run: pip install xgboost scikit-learn")
    async def train(self, X, y, version_id=None) -> TrainingResult:
        import pickle
        xgb, split, (acc_fn, prec_fn, rec_fn, f1_fn, auc_fn) = self._import_deps()
        def _train():
            t0 = time.time()
            Xtr,Xv,ytr,yv = split(X,y,test_size=0.2,random_state=42)
            m = xgb.XGBClassifier(**self._params)
            m.fit(Xtr,ytr,eval_set=[(Xv,yv)],verbose=False)
            yp = m.predict(Xv); ypr = m.predict_proba(Xv)[:,1]
            vid = version_id or f"v{int(time.time())}"
            os.makedirs(self._dir,exist_ok=True)
            with open(f"{self._dir}/{vid}.pkl","wb") as fh: pickle.dump(m,fh)
            fi = {f"f{i}":float(v) for i,v in enumerate(getattr(m,"feature_importances_",[]))}
            return TrainingResult(
                version_id=vid,accuracy=float(acc_fn(yv,yp)),
                precision=float(prec_fn(yv,yp,zero_division=0)),
                recall=float(rec_fn(yv,yp,zero_division=0)),
                f1_score=float(f1_fn(yv,yp,zero_division=0)),
                auc_roc=float(auc_fn(yv,ypr)),
                n_samples=len(X),n_features=X.shape[1] if hasattr(X,"shape") else len(X[0]),
                training_time_s=time.time()-t0,feature_importance=fi,params=self._params)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _train)
        self._log.info("Training: %s acc=%.3f auc=%.3f", result.version_id, result.accuracy, result.auc_roc)
        return result
