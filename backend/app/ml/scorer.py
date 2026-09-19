from __future__ import annotations

"""Serving side of the lead recovery-propensity model.

Ranks the dropped-lead queue so the dialler rings the leads most likely to be
recovered first. Every score comes back with the reasons behind it - an ops team
will not trust a number it cannot interrogate, and the JD's responsible-AI line
about explainability applies as much to a small model as a large one.

If the artifact is missing or scikit-learn is unavailable, scoring falls back to
a transparent heuristic with the same interface, so the API never breaks because
a model was not trained.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.ml.features import (
    CATEGORICAL_FEATURES,
    FEATURE_LABELS,
    FEATURE_ORDER,
    NUMERIC_FEATURES,
    build_features,
)

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "lead_scorer.joblib"
METRICS_PATH = ARTIFACT_DIR / "metrics.json"

HIGH_BAND = 0.45
MEDIUM_BAND = 0.25


class LeadScorer:
    def __init__(self, model_path: Optional[Path] = None, metrics_path: Optional[Path] = None):
        self.model_path = model_path or MODEL_PATH
        self.metrics_path = metrics_path or METRICS_PATH
        self.model = None
        self.metrics: dict[str, Any] = {}
        self.load_error: Optional[str] = None
        self._load()

    # ---- lifecycle -------------------------------------------------------

    def _load(self) -> None:
        try:
            if self.metrics_path.exists():
                self.metrics = json.loads(self.metrics_path.read_text())
            if self.model_path.exists():
                from joblib import load

                self.model = load(self.model_path)
        except Exception as exc:
            self.model = None
            self.load_error = f"{type(exc).__name__}: {exc}"

    def reload(self) -> dict[str, Any]:
        self.model = None
        self.metrics = {}
        self.load_error = None
        self._load()
        return self.status()

    @property
    def mode(self) -> str:
        return "model" if self.model is not None else "heuristic"

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "model_version": self.metrics.get("model_version"),
            "algorithm": self.metrics.get("algorithm"),
            "trained_at": self.metrics.get("trained_at"),
            "features": FEATURE_ORDER,
            "metrics": self.metrics.get("test", {}),
            "queue_lift": self.metrics.get("queue", {}),
            "data_source": self.metrics.get("data_source"),
            "artifact_present": self.model_path.exists(),
            "load_error": self.load_error,
            "note": "Falls back to a documented heuristic when no artifact is present."
            if self.model is None
            else None,
        }

    # ---- scoring ---------------------------------------------------------

    def score(self, lead: dict[str, Any], *, now: Optional[datetime] = None) -> dict[str, Any]:
        feats = build_features(lead, now=now or datetime.now(timezone.utc))
        if self.model is not None:
            probability = self._model_probability(feats)
            contributions = self._contributions(feats)
        else:
            probability = self._heuristic_probability(feats)
            contributions = []

        return {
            "lead_id": lead.get("lead_id"),
            "recovery_probability": round(float(probability), 4),
            "band": self._band(probability),
            "features": feats,
            "reasons": self._reasons(feats, contributions),
            "scored_by": self.mode,
            "model_version": self.metrics.get("model_version") if self.model else "heuristic-1.0",
        }

    def rank(self, leads: list[dict[str, Any]], *, now: Optional[datetime] = None) -> list[dict[str, Any]]:
        scored = [self.score(lead, now=now) for lead in leads]
        scored.sort(key=lambda s: s["recovery_probability"], reverse=True)
        for position, item in enumerate(scored, start=1):
            item["queue_position"] = position
        return scored

    # ---- internals -------------------------------------------------------

    def _model_probability(self, feats: dict[str, Any]) -> float:
        import pandas as pd

        frame = pd.DataFrame([feats])[FEATURE_ORDER]
        return float(self.model.predict_proba(frame)[0][1])

    def _contributions(self, feats: dict[str, Any]) -> list[tuple[str, float]]:
        """Per-feature push on the log-odds, for linear models."""
        try:
            pre = self.model.named_steps["pre"]
            clf = self.model.named_steps["clf"]
            coefs = getattr(clf, "coef_", None)
            if coefs is None:
                return []

            import pandas as pd

            transformed = pre.transform(pd.DataFrame([feats])[FEATURE_ORDER])
            row = transformed[0] if hasattr(transformed, "__getitem__") else transformed
            names = list(pre.get_feature_names_out())
            pairs = [(names[i], float(row[i] * coefs[0][i])) for i in range(len(names))]
            pairs.sort(key=lambda p: abs(p[1]), reverse=True)
            return pairs[:3]
        except Exception:
            return []

    @staticmethod
    def _heuristic_probability(feats: dict[str, Any]) -> float:
        """Documented fallback - the same shape of judgement, without a model."""
        score = 0.30
        score += 0.35 * feats["progress_ratio"]
        score -= min(0.20, 0.0015 * feats["hours_since_drop"])
        score -= 0.10 * feats["prior_attempts"]
        score += {"econnex": 0.08, "campaign": 0.0, "affiliate": -0.08}.get(feats["source"], 0.0)
        if feats["dropped_hour"] < 7 or feats["dropped_hour"] >= 21:
            score -= 0.05
        return max(0.02, min(0.95, score))

    @staticmethod
    def _band(probability: float) -> str:
        if probability >= HIGH_BAND:
            return "High"
        if probability >= MEDIUM_BAND:
            return "Medium"
        return "Low"

    @staticmethod
    def _reasons(feats: dict[str, Any], contributions: list[tuple[str, float]]) -> list[str]:
        reasons: list[str] = []

        completed = int(feats["fields_completed"])
        if completed >= 5:
            reasons.append(f"{completed} of 8 fields already captured - little left to ask")
        elif completed <= 1:
            reasons.append(f"only {completed} field(s) captured - most of the journey remains")

        hours = feats["hours_since_drop"]
        if hours <= 12:
            reasons.append(f"dropped {hours:.0f}h ago - still fresh")
        elif hours >= 96:
            reasons.append(f"dropped {hours/24:.0f} days ago - intent has likely cooled")

        attempts = int(feats["prior_attempts"])
        if attempts >= 2:
            reasons.append(f"{attempts} previous attempts - risk of annoying the customer")
        elif attempts == 0:
            reasons.append("never been called before")

        if feats["source"] == "affiliate":
            reasons.append("affiliate traffic - historically converts lower")
        elif feats["source"] == "econnex":
            reasons.append("came from econnex directly")

        if contributions:
            top = contributions[0]
            direction = "raises" if top[1] > 0 else "lowers"
            label = FEATURE_LABELS.get(top[0].split("__")[-1], top[0].split("__")[-1])
            reasons.append(f"model: {label} {direction} the score most")

        return reasons[:4]
