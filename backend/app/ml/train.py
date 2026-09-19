from __future__ import annotations

"""Train the lead recovery-propensity model.

    PYTHONPATH=. python app/ml/train.py

Writes app/ml/artifacts/lead_scorer.joblib and metrics.json. Serving reads both;
if either is missing the scorer falls back to a transparent heuristic, so the
API never depends on a model being present.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.core.config import DATA_DIR
from app.ml.features import CATEGORICAL_FEATURES, FEATURE_ORDER, NUMERIC_FEATURES, build_features

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "lead_scorer.joblib"
METRICS_PATH = ARTIFACT_DIR / "metrics.json"
MODEL_VERSION = "1.0.0"
RANDOM_STATE = 42

# Features are time-relative, so training pins "now" to the dataset's reference
# point. Serving uses the real clock; the meaning of the feature is identical.
REFERENCE_NOW = datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc)

# The call list is a ranking problem: what matters is whether the leads we ring
# first are the ones worth ringing.
TOP_K_FRACTION = 0.20


def load_frame(path: Path | None = None) -> pd.DataFrame:
    source = path or (DATA_DIR / "lead_history.json")
    rows = json.loads(source.read_text())
    features = [build_features(r, now=REFERENCE_NOW) for r in rows]
    frame = pd.DataFrame(features)[FEATURE_ORDER]
    frame["recovered"] = [r["recovered"] for r in rows]
    return frame


def build_pipeline(estimator) -> Pipeline:
    pre = ColumnTransformer(
        [
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )
    return Pipeline([("pre", pre), ("clf", estimator)])


def top_k_metrics(y_true: np.ndarray, scores: np.ndarray, fraction: float) -> dict:
    """How good is the top of the call queue, versus calling at random?"""
    n = max(1, int(len(scores) * fraction))
    order = np.argsort(scores)[::-1][:n]
    hits = int(y_true[order].sum())
    base_rate = float(y_true.mean())
    precision_at_k = hits / n
    return {
        "k_fraction": fraction,
        "k": n,
        "precision_at_k": round(precision_at_k, 4),
        "recall_at_k": round(hits / max(1, int(y_true.sum())), 4),
        "base_rate": round(base_rate, 4),
        "lift_at_k": round(precision_at_k / base_rate, 3) if base_rate else 0.0,
    }


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    frame = load_frame()
    X = frame[FEATURE_ORDER]
    y = frame["recovered"].to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=y
    )

    candidates = {
        "logistic_regression": build_pipeline(
            LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)
        ),
        "gradient_boosting": build_pipeline(
            GradientBoostingClassifier(random_state=RANDOM_STATE)
        ),
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    selection = {}
    for name, pipe in candidates.items():
        scores = cross_val_score(pipe, X_train, y_train, cv=cv, scoring="roc_auc")
        selection[name] = {
            "cv_roc_auc_mean": round(float(scores.mean()), 4),
            "cv_roc_auc_std": round(float(scores.std()), 4),
        }
        print(f"{name}: CV ROC-AUC {scores.mean():.4f} (+/- {scores.std():.4f})")

    best_name = max(selection, key=lambda k: selection[k]["cv_roc_auc_mean"])
    model = candidates[best_name]
    model.fit(X_train, y_train)
    print(f"selected: {best_name}")

    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, preds).ravel()

    metrics = {
        "model_version": MODEL_VERSION,
        "algorithm": best_name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "sklearn_feature_order": FEATURE_ORDER,
        "n_rows": int(len(frame)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "base_rate": round(float(y.mean()), 4),
        "selection": selection,
        "test": {
            "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
            "pr_auc": round(float(average_precision_score(y_test, proba)), 4),
            "precision": round(float(precision_score(y_test, preds, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, preds, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, preds, zero_division=0)), 4),
            "brier": round(float(brier_score_loss(y_test, proba)), 4),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        },
        "queue": top_k_metrics(y_test, proba, TOP_K_FRACTION),
        "data_source": "synthetic (app/ml/dataset.py) - see the docstring; metrics "
                       "measure pipeline correctness on a known generating process, "
                       "not real-world accuracy",
        "dataset_sha256": hashlib.sha256(
            (DATA_DIR / "lead_history.json").read_bytes()
        ).hexdigest()[:16],
    }

    dump(model, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))

    t = metrics["test"]
    q = metrics["queue"]
    print(f"\nheld-out ROC-AUC {t['roc_auc']}  PR-AUC {t['pr_auc']}  F1 {t['f1']}  Brier {t['brier']}")
    print(f"top {int(q['k_fraction']*100)}% of the queue: precision {q['precision_at_k']} "
          f"vs base rate {q['base_rate']} = {q['lift_at_k']}x lift")
    print(f"saved {MODEL_PATH.name} + {METRICS_PATH.name}")


if __name__ == "__main__":
    main()
