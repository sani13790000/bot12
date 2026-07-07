from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    n_splits: int = 5
    train_pct: float = 0.7
    embargo_pct: float = 0.01
    min_train_samples: int = 100
    min_test_samples: int = 30
    anchored: bool = True
    purge_k: int = 5


@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_start: int
    train_end: int
    embargo_end: int
    test_start: int
    test_end: int
    n_train: int
    n_test: int


@dataclass
class FoldResult:
    fold_id: int
    sharpe: float
    total_return: float
    max_drawdown: float
    win_rate: float
    n_trades: int
    train_sharpe: float = 0.0
    overfitting_ratio: float = 0.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class WalkForwardResult:
    config: WalkForwardConfig
    folds: List[FoldResult]
    stability_score: float
    sharpe_mean: float
    sharpe_std: float
    sharpe_cv: float
    mean_drawdown: float
    mean_return: float
    is_robust: bool
    warnings: List[str] = field(default_factory=list)
    duration_s: float = 0.0


class WalkForwardEngine:
    """Anchored+rolling walk-forward with purged CV, embargo, CPCV, robustness metrics."""

    def __init__(self, config=None):
        self._cfg = config or WalkForwardConfig()

    def generate_folds(self, n_bars: int) -> List[Fold]:
        cfg = self._cfg
        folds = []
        if cfg.anchored:
            fold_size = n_bars // (cfg.n_splits + 1)
            if fold_size < cfg.min_train_samples + cfg.min_test_samples:
                raise ValueError(f"Insufficient data: {n_bars} bars for {cfg.n_splits} folds")
            for i in range(cfg.n_splits):
                te = fold_size * (i + 1)
                emb = max(cfg.purge_k, int(fold_size * cfg.embargo_pct))
                ts = te + emb
                tend = min(ts + fold_size, n_bars)
                if tend - ts < cfg.min_test_samples:
                    continue
                folds.append(Fold(i, 0, te, ts, ts, tend, te, tend - ts))
        else:
            w = int(n_bars / (cfg.n_splits + 1))
            tr = int(w * cfg.train_pct)
            te = w - tr
            emb = max(cfg.purge_k, int(w * cfg.embargo_pct))
            step = (n_bars - w) // max(cfg.n_splits - 1, 1)
            for i in range(cfg.n_splits):
                s = i * step
                tend2 = s + tr
                ts = tend2 + emb
                tend3 = ts + te
                if tend3 > n_bars:
                    break
                if tend2 - s < cfg.min_train_samples:
                    continue
                folds.append(Fold(i, s, tend2, ts, ts, tend3, tend2 - s, tend3 - ts))
        return folds

    def run(self, bars, strategy_fn) -> WalkForwardResult:
        t0 = time.monotonic()
        folds = self.generate_folds(len(bars))
        results = []
        warnings = []
        for fold in folds:
            train = bars[fold.train_start : fold.train_end]
            test = bars[fold.test_start : fold.test_end]
            try:
                r = strategy_fn(train, test)
                r = FoldResult(
                    fold.fold_id,
                    r.sharpe,
                    r.total_return,
                    r.max_drawdown,
                    r.win_rate,
                    r.n_trades,
                    r.train_sharpe,
                    r.train_sharpe / r.sharpe if r.sharpe > 0.01 else 0.0,
                    r.metadata,
                )
                results.append(r)
            except Exception as e:
                warnings.append(f"fold {fold.fold_id} failed: {e}")
                logger.error("fold %d error: %s", fold.fold_id, e, exc_info=True)
        if not results:
            raise RuntimeError("All walk-forward folds failed")
        agg = self._aggregate(results, warnings)
        agg.duration_s = time.monotonic() - t0
        return agg

    def _aggregate(self, results, warnings):
        sh = [r.sharpe for r in results]
        ret = [r.total_return for r in results]
        dd = [r.max_drawdown for r in results]
        ofr = [r.overfitting_ratio for r in results if r.overfitting_ratio > 0]
        m = sum(sh) / len(sh)
        v = sum((x - m) ** 2 for x in sh) / len(sh)
        s = math.sqrt(v)
        cv = s / abs(m) if abs(m) > 0.01 else 999.0
        is_r = True
        if m < 0.5:
            warnings.append(f"Mean Sharpe {m:.2f} < 0.5")
            is_r = False
        if cv > 0.5:
            warnings.append(f"Sharpe CV {cv:.2f} > 0.5")
            is_r = False
        neg = sum(1 for x in sh if x < 0)
        if neg > len(sh) // 3:
            warnings.append(f"{neg}/{len(sh)} folds negative Sharpe")
            is_r = False
        mofr = sum(ofr) / len(ofr) if ofr else 0.0
        if mofr > 2.0:
            warnings.append(f"OFR {mofr:.2f} > 2.0")
            is_r = False
        prof = sum(1 for r in ret if r > 0)
        if prof < len(results) // 2:
            warnings.append(f"Only {prof}/{len(results)} folds profitable")
            is_r = False
        stab = max(
            0.0,
            min(
                1.0,
                0.3 * min(1.0, m / 1.5)
                + 0.3 * max(0.0, 1.0 - cv)
                + 0.2 * (prof / len(results))
                + 0.2 * max(0.0, 1.0 - mofr / 4.0),
            ),
        )
        return WalkForwardResult(
            self._cfg,
            results,
            round(stab, 4),
            round(m, 4),
            round(s, 4),
            round(cv, 4),
            round(sum(dd) / len(dd), 4),
            round(sum(ret) / len(ret), 4),
            is_r,
            warnings,
        )

    def combinatorial_purged_cv(self, n_bars, n_splits=6, n_test_splits=2):
        from itertools import combinations

        fs = n_bars // n_splits
        max(self._cfg.purge_k, int(fs * self._cfg.embargo_pct))
        sp = [i * fs for i in range(n_splits + 1)]
        sp[-1] = n_bars
        fid = 0
        for ti in combinations(range(n_splits), n_test_splits):
            ts = set(ti)
            trs = []
            tes = []
            for i in range(n_splits):
                s2, e2 = sp[i], sp[i + 1]
                (tes if i in ts else trs).append((s2, e2))
            if not trs or not tes:
                continue
            yield Fold(
                fid,
                trs[0][0],
                trs[-1][1],
                tes[0][0],
                tes[0][0],
                tes[-1][1],
                sum(e - s for s, e in trs),
                sum(e - s for s, e in tes),
            )
            fid += 1
