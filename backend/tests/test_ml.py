"""Tests for the lead scoring model and its serving path."""

from datetime import datetime, timezone

import pytest

from app.ml.dataset import generate, recovery_probability
from app.ml.features import FEATURE_ORDER, build_features
from app.ml.scorer import LeadScorer

NOW = datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc)


def _lead(**overrides):
    base = {
        "lead_id": "EN-TEST",
        "known_fields": {"postcode": "3000", "property_type": "house"},
        "dropped_at": "2026-09-19T03:00:00+00:00",
        "source": "econnex",
        "prior_attempts": 0,
    }
    base.update(overrides)
    return base


# ---- features ------------------------------------------------------------

def test_features_match_the_declared_contract():
    feats = build_features(_lead(), now=NOW)
    assert set(feats) == set(FEATURE_ORDER)
    assert feats["fields_completed"] == 2
    assert feats["progress_ratio"] == 0.25
    assert feats["hours_since_drop"] == 6.0
    assert feats["source"] == "econnex"


def test_features_survive_missing_and_unknown_values():
    feats = build_features({"lead_id": "X"}, now=NOW)
    assert feats["fields_completed"] == 0
    assert feats["source"] == "econnex"          # unknown source falls back
    assert feats["hours_since_drop"] == 48.0     # no timestamp -> documented default

    weird = build_features(_lead(source="tiktok", dropped_at="not-a-date"), now=NOW)
    assert weird["source"] == "econnex"
    assert weird["hours_since_drop"] == 48.0


def test_no_future_leakage_in_features():
    """Nothing knowable only after the call may become a feature."""
    forbidden = {"recovered", "outcome", "completed_at", "consent"}
    assert not forbidden & set(FEATURE_ORDER)


# ---- generating process --------------------------------------------------

def test_generating_process_moves_in_the_expected_direction():
    far = recovery_probability(0.875, 4, 0, "econnex", 14, 0)
    near = recovery_probability(0.125, 4, 0, "econnex", 14, 0)
    assert far > near, "more progress should mean more propensity"

    fresh = recovery_probability(0.5, 2, 0, "econnex", 14, 0)
    stale = recovery_probability(0.5, 200, 0, "econnex", 14, 0)
    assert fresh > stale, "propensity should decay with time"

    untried = recovery_probability(0.5, 10, 0, "econnex", 14, 0)
    chased = recovery_probability(0.5, 10, 3, "econnex", 14, 0)
    assert untried > chased, "repeated attempts should lower propensity"


def test_dataset_is_deterministic_and_balanced_enough_to_train():
    a = generate(n=300, seed=7)
    b = generate(n=300, seed=7)
    assert a == b, "same seed must give the same dataset"

    rate = sum(r["recovered"] for r in a) / len(a)
    assert 0.1 < rate < 0.6, f"degenerate label balance: {rate}"


# ---- scoring -------------------------------------------------------------

def test_scorer_ranks_and_explains():
    scorer = LeadScorer()
    leads = [
        _lead(lead_id="A", known_fields={f"f{i}": 1 for i in range(7)}),
        _lead(lead_id="B", known_fields={}, prior_attempts=3,
              dropped_at="2026-09-10T03:00:00+00:00", source="affiliate"),
    ]
    ranked = scorer.rank(leads, now=NOW)

    assert [r["lead_id"] for r in ranked] == ["A", "B"], "the better lead must rank first"
    assert ranked[0]["queue_position"] == 1
    assert 0.0 <= ranked[0]["recovery_probability"] <= 1.0
    assert ranked[0]["band"] in {"High", "Medium", "Low"}
    assert ranked[0]["reasons"], "a score with no explanation is not usable by ops"


def test_scorer_falls_back_when_no_artifact(tmp_path):
    scorer = LeadScorer(
        model_path=tmp_path / "missing.joblib",
        metrics_path=tmp_path / "missing.json",
    )
    assert scorer.mode == "heuristic"

    result = scorer.score(_lead(), now=NOW)
    assert 0.0 <= result["recovery_probability"] <= 1.0
    assert result["scored_by"] == "heuristic"
    assert result["model_version"] == "heuristic-1.0"

    status = scorer.status()
    assert status["artifact_present"] is False
    assert status["note"]


def test_heuristic_agrees_with_the_model_on_ordering(tmp_path):
    """Fallback must not invert the queue if the artifact goes missing."""
    good = _lead(lead_id="good", known_fields={f"f{i}": 1 for i in range(7)})
    poor = _lead(lead_id="poor", known_fields={}, prior_attempts=3,
                 dropped_at="2026-09-09T03:00:00+00:00", source="affiliate")

    model = LeadScorer()
    heuristic = LeadScorer(
        model_path=tmp_path / "none.joblib", metrics_path=tmp_path / "none.json"
    )
    for scorer in (model, heuristic):
        order = [r["lead_id"] for r in scorer.rank([poor, good], now=NOW)]
        assert order == ["good", "poor"], f"{scorer.mode} ranked the wrong lead first"


@pytest.mark.skipif(not LeadScorer().status()["artifact_present"], reason="model not trained")
def test_trained_model_beats_random_on_its_own_test_split():
    """The recorded metrics must show real signal, not a coin flip."""
    metrics = LeadScorer().status()["metrics"]
    assert metrics["roc_auc"] > 0.6, "model shows no usable signal"
    assert metrics["pr_auc"] > LeadScorer().status()["queue_lift"]["base_rate"]


@pytest.mark.skipif(not LeadScorer().status()["artifact_present"], reason="model not trained")
def test_queue_lift_is_recorded_and_better_than_calling_at_random():
    lift = LeadScorer().status()["queue_lift"]
    assert lift["lift_at_k"] > 1.0, "ranking must beat calling leads in arbitrary order"
    assert lift["precision_at_k"] > lift["base_rate"]
