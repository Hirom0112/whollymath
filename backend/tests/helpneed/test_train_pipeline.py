"""Tests for the HelpNeed training pipeline core (Slice 3.5).

``train_and_evaluate`` is the testable heart of the otherwise script-like pipeline:
a deterministic stratified split, fit, and holdout score. We assert it learns a
clearly-separable synthetic signal and reports sane metrics. (The real-data ``main``
run is a script — CLAUDE.md §9 — its numbers are recorded in the commit message.)
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.features import HelpNeedFeatures, TrainingExample
from app.helpneed.train_pipeline import train_and_evaluate

_KC = KnowledgeComponentId.ADDITION_UNLIKE


def _example(*, struggling: bool, i: int) -> TrainingExample:
    jitter = (i % 10) / 100.0
    rate = (0.85 if struggling else 0.05) + jitter
    return TrainingExample(
        features=HelpNeedFeatures(
            recent_latency_ms_mean=2000.0 + 4000.0 * rate,
            recent_attempts_mean=(3.0 if struggling else 1.0) + jitter,
            recent_hint_rate=2.0 * rate,
            recent_error_rate=rate,
            recent_request_answer_rate=rate,
            recent_no_hint_error_rate=rate,
            turns_since_last_correct=1.0 + 4.0 * rate,
            prior_unproductive_rate=rate,
            session_position=5.0,
            kc=_KC,
        ),
        label=struggling,
        assignment_log_id=f"{'s' if struggling else 'c'}{i}",
        problem_id="p",
    )


def _dataset() -> list[TrainingExample]:
    out: list[TrainingExample] = []
    for i in range(120):
        out.append(_example(struggling=True, i=i))
        out.append(_example(struggling=False, i=i))
    return out


def test_train_and_evaluate_learns_separable_signal() -> None:
    """On a clearly-separable set, holdout accuracy beats the majority baseline."""
    _, report = train_and_evaluate(_dataset(), kind="xgboost", random_state=0)
    assert report.holdout_accuracy > 0.9
    assert report.holdout_accuracy >= report.majority_baseline_accuracy
    assert 0.0 <= report.holdout_auc <= 1.0
    assert report.n_examples == 240
    assert 0.45 < report.positive_rate < 0.55  # balanced by construction


def test_logistic_baseline_also_reported() -> None:
    """The baseline trains through the same path (TECH_STACK §5 comparison)."""
    _, report = train_and_evaluate(_dataset(), kind="logistic", random_state=0)
    assert report.kind == "logistic"
    assert report.holdout_accuracy > 0.9


def test_evaluation_is_deterministic() -> None:
    """Same seed ⇒ identical reported accuracy (PROJECT.md §4.1)."""
    _, a = train_and_evaluate(_dataset(), kind="xgboost", random_state=7)
    _, b = train_and_evaluate(_dataset(), kind="xgboost", random_state=7)
    assert a.holdout_accuracy == b.holdout_accuracy
    assert a.holdout_auc == b.holdout_auc
