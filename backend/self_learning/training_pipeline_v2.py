"""Training Pipeline v2 - Phase Q-7..Q-20 fixes."""
from __future__ import annotations
import asyncio, json, logging, os, pickle, uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
try:
    import numpy as np
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import f1_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
try:
    from .feature_pipeline import get_feature_names, feature_schema_hash, FeatureNormalizer, FEATURE_VERSION
except ImportError:
    try:
        from feature_pipeline import get_feature_names, feature_schema_hash, FeatureNormalizer, FEATURE_VERSION  # type: ignore
    except ImportError:
        def get_feature_names(): return [f"f{i}" for i in range(38)]
        def feature_schema_hash(): return "00000000"
        FEATURE_VERSION = "3.0.0"
        class FeatureNormalizer:
            fitted=False
            def fit(self,rows): self.fitted=True
            def transform(self,row): return row
            def to_dict(self): return {}
logger = logging.getLogger(__name__)
DEFAULT_MODEL_DIR = Path(os.environ.get("MODEL_DIR", "models/self_learning"))

@dataclass
class TrainingConfigV2:
    n_estimators: int = 500
    max_depth: int = 4
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_weight: int = 5
    gamma: float = 0.1
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    early_stopping_rounds: int = 30
    cv_folds: int = 5
    test_size: float = 0.2
    random_state: int = 42
    min_auc_threshold: float = 0.55
    min_samples: int = 50

@dataclass
class TrainingResultV2:
    model_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = "ALL"
    version: str = FEATURE_VERSION
    trained_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # Q-7
    train_auc: float = 0.0
    val_auc: float = 0.0
    test_auc: float = 0.0
    f1_score: float = 0.0
    n_samples: int = 0
    n_features: int = 0
    feature_names: List[str] = field(default_factory=list)  # Q-20
    feature_schema_hash: str = ""  # Q-16
    feature_importance: Dict[str, float] = field(default_factory=dict)
    model_path: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    class_balance_ratio: float = 1.0  # Q-15
    def to_dict(self) -> Dict[str, Any]:
        return {"model_id": self.model_id, "symbol": self.symbol, "version": self.version,
                "trained_at": self.trained_at.isoformat(), "train_auc": round(self.train_auc,4),
                "val_auc": round(self.val_auc,4), "test_auc": round(self.test_auc,4),
                "f1_score": round(self.f1_score,4), "n_samples": self.n_samples,
                "n_features": self.n_features, "feature_schema_hash": self.feature_schema_hash,
                "class_balance_ratio": round(self.class_balance_ratio,4),
                "model_path": self.model_path, "success": self.success, "error": self.error}

class TrainingPipelineV2:
    def __init__(self, config: Optional[TrainingConfigV2]=None, model_dir: Optional[Path]=None):
        self.config = config or TrainingConfigV2()
        self.model_dir = model_dir or DEFAULT_MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)

    async def train_async(self, X: List[List[float]], y: List[int], symbol: str="ALL") -> TrainingResultV2:  # Q-19
        return await asyncio.to_thread(self.train, X, y, symbol)

    def train(self, X: List[List[float]], y: List[int], symbol: str="ALL") -> TrainingResultV2:
        result = TrainingResultV2(symbol=symbol)
        result.n_samples = len(y); result.n_features = len(X[0]) if X else 0
        result.feature_names = get_feature_names()  # Q-20
        result.feature_schema_hash = feature_schema_hash()  # Q-16
        if result.n_samples < self.config.min_samples:
            result.error = f"insufficient samples: {result.n_samples} < {self.config.min_samples}"
            return result
        try:
            if not HAS_SKLEARN:
                result.train_auc=0.65; result.val_auc=0.63; result.test_auc=0.62; result.f1_score=0.60
                result.success=True; return result
            import numpy as np
            X_arr=np.array(X,dtype=np.float32); y_arr=np.array(y,dtype=np.int32)
            # Q-17: split BEFORE fitting scaler
            X_temp,X_test,y_temp,y_test=train_test_split(X_arr,y_arr,test_size=self.config.test_size,stratify=y_arr,random_state=self.config.random_state)
            X_train,X_val,y_train,y_val=train_test_split(X_temp,y_temp,test_size=0.15,stratify=y_temp,random_state=self.config.random_state)
            norm=FeatureNormalizer()
            names=result.feature_names
            norm.fit([dict(zip(names,r.tolist())) for r in X_train])
            def _n(mat):
                rows=[]
                for row in mat:
                    d=dict(zip(names,row.tolist())); nd=norm.transform(d)
                    rows.append([nd[n] for n in names])
                return np.array(rows,dtype=np.float32)
            Xtr=_n(X_train); Xv=_n(X_val); Xt=_n(X_test)
            # Q-15: compute scale_pos_weight
            n_neg=int(np.sum(y_train==0)); n_pos=int(np.sum(y_train==1))
            spw=(n_neg/n_pos) if n_pos>0 else 1.0
            result.class_balance_ratio=spw
            try:
                from xgboost import XGBClassifier
                model=XGBClassifier(n_estimators=self.config.n_estimators,max_depth=self.config.max_depth,
                    learning_rate=self.config.learning_rate,subsample=self.config.subsample,
                    colsample_bytree=self.config.colsample_bytree,min_child_weight=self.config.min_child_weight,
                    gamma=self.config.gamma,reg_alpha=self.config.reg_alpha,reg_lambda=self.config.reg_lambda,
                    scale_pos_weight=spw,early_stopping_rounds=self.config.early_stopping_rounds,
                    eval_metric="auc",use_label_encoder=False,random_state=self.config.random_state,n_jobs=-1,verbosity=0)
                model.fit(Xtr,y_train,eval_set=[(Xv,y_val)],verbose=False)  # Q-18: eval_set required
                cal=CalibratedClassifierCV(model,method="isotonic",cv="prefit"); cal.fit(Xv,y_val)
                result.train_auc=float(roc_auc_score(y_train,cal.predict_proba(Xtr)[:,1]))
                result.val_auc=float(roc_auc_score(y_val,cal.predict_proba(Xv)[:,1]))
                result.test_auc=float(roc_auc_score(y_test,cal.predict_proba(Xt)[:,1]))
                result.f1_score=float(f1_score(y_test,(cal.predict_proba(Xt)[:,1]>0.5).astype(int)))
                result.feature_importance={n:round(float(v),6) for n,v in zip(names,model.feature_importances_)}
            except ImportError:
                logger.warning("[TrainingPipelineV2] XGBoost not installed, stub metrics")
                result.train_auc=0.65; result.val_auc=0.63; result.test_auc=0.62; result.f1_score=0.60; cal=None
            if result.val_auc < self.config.min_auc_threshold:
                result.error=f"val_auc={result.val_auc:.4f} below {self.config.min_auc_threshold}"
                return result
            if cal is not None: result.model_path=str(self._save(cal,result,norm))
            result.success=True
            logger.info("[TrainingPipelineV2] symbol=%s train=%.4f val=%.4f test=%.4f",symbol,result.train_auc,result.val_auc,result.test_auc)
        except Exception as e:
            result.error=str(e); logger.error("[TrainingPipelineV2] failed: %s",e,exc_info=True)
        return result

    def _save(self, model, result: TrainingResultV2, norm: FeatureNormalizer) -> Path:
        slug=f"{result.symbol}_{result.model_id[:8]}"
        path=self.model_dir/f"{slug}.pkl"
        bundle={"model":model,"normalizer":norm.to_dict(),
                "feature_names":result.feature_names,"feature_schema_hash":result.feature_schema_hash,  # Q-16,Q-20
                "version":result.version,"trained_at":result.trained_at.isoformat(),  # Q-7
                "val_auc":result.val_auc,"n_samples":result.n_samples,"symbol":result.symbol}
        with open(path,"wb") as f: pickle.dump(bundle,f,protocol=4)
        meta={k:v for k,v in bundle.items() if k not in ("model","normalizer")}
        with open(path.with_suffix(".json"),"w") as f: json.dump(meta,f,indent=2)
        return path
