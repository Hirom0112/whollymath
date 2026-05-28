"""Tests for the HelpNeed predictor (Slice 3.5).

Mandatory-TDD (CLAUDE.md §2, §9): we test inference LATENCY (the turn loop has a
sub-100ms budget — §8.1) and BEHAVIOR on known-edge-case inputs, not the exact
probabilities of a non-deterministic-ish learner (we DO seed for reproducibility).
The model trains on a small, strongly-separable synthetic dataset so the tests are
fast and the expected behavior is unambiguous.
"""

from __future__ import annotations

import time

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.features import HelpNeedFeatures, TrainingExample
from app.helpneed.predictor import HelpNeedPredictor

_KC = KnowledgeComponentId.ADDITION_UNLIKE


def _features(*, error_rate: float, unproductive_rate: float, attempts: float) -> HelpNeedFeatures:
    return HelpNeedFeatures(
        recent_latency_ms_mean=2000.0 + 4000.0 * error_rate,
        recent_attempts_mean=attempts,
        recent_hint_rate=2.0 * error_rate,
        recent_error_rate=error_rate,
        recent_request_answer_rate=error_rate,
        turns_since_last_correct=1.0 + 4.0 * error_rate,
        prior_unproductive_rate=unproductive_rate,
        session_position=5.0,
        kc=_KC,
    )


_STRUGGLING = _features(error_rate=0.9, unproductive_rate=0.85, attempts=4.0)
_CLEAN = _features(error_rate=0.05, unproductive_rate=0.05, attempts=1.0)


def _dataset(n_per_class: int = 120) -> list[TrainingExample]:
    """A separable synthetic set: high-struggle history → unproductive, clean → not.

    Small per-row variation (via the index) keeps the columns non-degenerate while
    the two clusters stay clearly separable, so the trained model's behavior on the
    canonical struggling/clean inputs is unambiguous.
    """
    examples: list[TrainingExample] = []
    for i in range(n_per_class):
        jitter = (i % 10) / 100.0
        examples.append(
            TrainingExample(
                features=_features(
                    error_rate=0.8 + jitter, unproductive_rate=0.8 + jitter, attempts=3.0 + jitter
                ),
                label=True,
                assignment_log_id=f"s{i}",
                problem_id="p",
            )
        )
        examples.append(
            TrainingExample(
                features=_features(
                    error_rate=0.0 + jitter, unproductive_rate=0.0 + jitter, attempts=1.0 + jitter
                ),
                label=False,
                assignment_log_id=f"c{i}",
                problem_id="p",
            )
        )
    return examples


def test_predict_proba_is_a_probability() -> None:
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    p = predictor.predict_proba(_STRUGGLING)
    assert 0.0 <= p <= 1.0


def test_struggling_history_scores_higher_than_clean() -> None:
    """The core behavior: more struggle in the recent window → higher HelpNeed."""
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    assert predictor.predict_proba(_STRUGGLING) > predictor.predict_proba(_CLEAN)
    assert predictor.predict_proba(_STRUGGLING) > 0.5
    assert predictor.predict_proba(_CLEAN) < 0.5


def test_inference_is_sub_100ms() -> None:
    """A single-turn inference must fit the turn-loop latency budget (§8.1)."""
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    predictor.predict_proba(_STRUGGLING)  # warm any one-time prediction setup
    start = time.perf_counter()
    predictor.predict_proba(_STRUGGLING)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert elapsed_ms < 100.0, f"inference took {elapsed_ms:.1f}ms (budget 100ms)"


def test_logistic_baseline_trains_and_predicts() -> None:
    """The interpretable baseline (TECH_STACK §5) also fits and ranks the two inputs."""
    predictor = HelpNeedPredictor.fit(_dataset(), kind="logistic", random_state=0)
    assert 0.0 <= predictor.predict_proba(_CLEAN) <= 1.0
    assert predictor.predict_proba(_STRUGGLING) > predictor.predict_proba(_CLEAN)


def test_save_load_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A persisted predictor reloads and gives identical predictions (joblib)."""
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    path = tmp_path / "helpneed.joblib"
    predictor.save(path)
    reloaded = HelpNeedPredictor.load(path)
    assert reloaded.predict_proba(_STRUGGLING) == predictor.predict_proba(_STRUGGLING)
    assert reloaded.kind == "xgboost"
