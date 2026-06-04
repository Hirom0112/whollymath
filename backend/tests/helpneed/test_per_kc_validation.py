"""Tests for per-KC validation of the HelpNeed predictor (T2 deliverable).

Mandatory-TDD (CLAUDE.md §2, §9): the per-KC validation is the *honest-reporting*
side of the cross-topic re-fit (T1_T2_COORDINATION.md §1 seam — "Per-KC validation
(AUC + calibration sliced by KC) + sub-100ms check | T2"). When one pooled model
serves every Grade-6 KC, "overall AUC 0.89" can hide a topic that scores at chance.
These tests pin that we (a) slice metrics per KC, (b) NEVER silently drop a thin KC
(it goes to a labelled pooled bucket, CLAUDE.md §9 honest reporting), (c) report a
single-class KC's AUC as ``None`` instead of crashing, and (d) hold the label-space
drift invariant the re-fit depends on (training label space ⊆ the one-hot space).

Metrics are checked against a stub scorer with pinned probabilities so the assertions
are exact and deterministic (PROJECT.md §4.1); one integration test runs a real
fitted predictor through the same path.
"""

from __future__ import annotations

import numpy as np
import pytest
from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.features import KC_ORDER, HelpNeedFeatures, TrainingExample
from app.helpneed.parse_edmcup import _CCSS_PREFIX_TO_KC
from app.helpneed.per_kc_validation import (
    THIN_BUCKET_LABEL,
    PerKcReport,
    trustworthy_kcs,
    validate_per_kc,
)
from app.helpneed.predictor import HelpNeedPredictor

_A = KnowledgeComponentId.ADDITION_UNLIKE
_B = KnowledgeComponentId.EQUIVALENCE
_C = KnowledgeComponentId.NUMBER_LINE_PLACEMENT


def _ex(kc: KnowledgeComponentId, label: bool, *, aid: str = "s") -> TrainingExample:
    """A minimal example tagged with ``kc`` and ``label``.

    Numeric features are all zero — the stub scorer's predictions are pinned by index,
    so the feature values don't drive these metric assertions (only the KC + label do).
    """
    features = HelpNeedFeatures(
        recent_latency_ms_mean=0.0,
        recent_attempts_mean=0.0,
        recent_hint_rate=0.0,
        recent_error_rate=0.0,
        recent_request_answer_rate=0.0,
        recent_no_hint_error_rate=0.0,
        turns_since_last_correct=0.0,
        prior_unproductive_rate=0.0,
        session_position=0.0,
        kc=kc,
    )
    return TrainingExample(features=features, label=label, assignment_log_id=aid, problem_id="p")


class _StubScorer:
    """A scorer whose per-row probabilities are pinned (so metric asserts are exact).

    Satisfies the structural ``predict_proba_matrix`` contract ``validate_per_kc`` uses;
    returns the pinned vector regardless of ``x`` (caller aligns it with example order).
    """

    def __init__(self, proba: list[float]) -> None:
        self._proba = np.asarray(proba, dtype=float)

    def predict_proba_matrix(self, x: np.ndarray) -> np.ndarray:
        return self._proba


def _metrics_for(report: PerKcReport, kc_value: str):  # type: ignore[no-untyped-def]
    return next(m for m in report.per_kc if m.kc == kc_value)


def test_one_entry_per_kc_above_threshold() -> None:
    """Each KC with enough examples gets its own metrics entry; no pooled bucket."""
    examples = [_ex(_A, i % 2 == 0) for i in range(40)] + [_ex(_B, i % 2 == 0) for i in range(40)]
    report = validate_per_kc(_StubScorer([0.5] * 80), examples, thin_threshold=10)

    kcs = {m.kc for m in report.per_kc}
    assert kcs == {_A.value, _B.value}
    assert THIN_BUCKET_LABEL not in kcs
    assert _metrics_for(report, _A.value).n_examples == 40
    assert _metrics_for(report, _B.value).n_examples == 40


def test_thin_kc_is_pooled_not_dropped() -> None:
    """Below-threshold KCs collapse into ONE labelled bucket — never silently dropped."""
    examples = (
        [_ex(_A, i % 2 == 0) for i in range(40)]
        + [_ex(_B, True) for _ in range(5)]
        + [_ex(_C, False) for _ in range(3)]
    )
    report = validate_per_kc(_StubScorer([0.5] * 48), examples, thin_threshold=10)

    assert {_B.value, _C.value}.isdisjoint({m.kc for m in report.per_kc})  # not their own entries
    thin = _metrics_for(report, THIN_BUCKET_LABEL)
    assert thin.n_examples == 8
    assert thin.pooled_kcs == tuple(sorted((_B.value, _C.value)))
    # No example is lost: every input lands in exactly one entry.
    assert sum(m.n_examples for m in report.per_kc) == len(examples)


def test_per_kc_auc_separates_perfect_ranking() -> None:
    """A KC whose positives all outscore its negatives gets AUC 1.0."""
    examples = [_ex(_A, True) for _ in range(20)] + [_ex(_A, False) for _ in range(20)]
    proba = [0.9] * 20 + [0.1] * 20
    report = validate_per_kc(_StubScorer(proba), examples, thin_threshold=5)
    assert _metrics_for(report, _A.value).auc == pytest.approx(1.0)


def test_single_class_kc_auc_is_none() -> None:
    """An all-positive (or all-negative) KC has an undefined AUC → None, not a crash."""
    examples = [_ex(_A, True) for _ in range(20)]
    report = validate_per_kc(_StubScorer([0.7] * 20), examples, thin_threshold=5)
    metrics = _metrics_for(report, _A.value)
    assert metrics.auc is None
    assert metrics.positive_rate == pytest.approx(1.0)


def test_calibration_gap_is_mean_pred_minus_observed() -> None:
    """Calibration gap = |mean predicted − observed positive rate| (0 when matched)."""
    examples = [_ex(_A, i < 5) for i in range(10)]  # 5 positives → observed 0.5
    perfect = validate_per_kc(_StubScorer([0.5] * 10), examples, thin_threshold=5)
    assert _metrics_for(perfect, _A.value).calibration_gap == pytest.approx(0.0)

    overconfident = validate_per_kc(_StubScorer([1.0] * 10), examples, thin_threshold=5)
    assert _metrics_for(overconfident, _A.value).calibration_gap == pytest.approx(0.5)


def test_overall_auc_spans_all_examples() -> None:
    """The report carries an overall AUC across every example, not just per-KC."""
    examples = [_ex(_A, True) for _ in range(10)] + [_ex(_B, False) for _ in range(10)]
    proba = [0.9] * 10 + [0.1] * 10
    report = validate_per_kc(_StubScorer(proba), examples, thin_threshold=5)
    assert report.overall_auc == pytest.approx(1.0)


def test_thin_threshold_is_recorded() -> None:
    """The threshold used is on the report (so the writeup states what 'thin' meant)."""
    examples = [_ex(_A, i % 2 == 0) for i in range(10)]
    assert validate_per_kc(_StubScorer([0.5] * 10), examples, thin_threshold=7).thin_threshold == 7


def test_empty_examples_raises() -> None:
    """Validating nothing is a caller error, not a silent empty report (CLAUDE.md §8.5)."""
    with pytest.raises(ValueError):
        validate_per_kc(_StubScorer([]), [], thin_threshold=5)


def test_integration_with_real_predictor() -> None:
    """A real fitted predictor flows through the per-KC path and yields valid metrics."""
    examples: list[TrainingExample] = []
    for i in range(60):
        jitter = (i % 10) / 100.0
        struggling = HelpNeedFeatures(
            recent_latency_ms_mean=5000.0,
            recent_attempts_mean=4.0,
            recent_hint_rate=2.0,
            recent_error_rate=0.9 + jitter / 10,
            recent_request_answer_rate=0.9,
            recent_no_hint_error_rate=0.9,
            turns_since_last_correct=5.0,
            prior_unproductive_rate=0.9,
            session_position=5.0,
            kc=_A,
        )
        clean = HelpNeedFeatures(
            recent_latency_ms_mean=1000.0,
            recent_attempts_mean=1.0,
            recent_hint_rate=0.0,
            recent_error_rate=0.0 + jitter / 10,
            recent_request_answer_rate=0.0,
            recent_no_hint_error_rate=0.0,
            turns_since_last_correct=1.0,
            prior_unproductive_rate=0.0,
            session_position=5.0,
            kc=_A,
        )
        examples.append(TrainingExample(struggling, True, f"s{i}", "p"))
        examples.append(TrainingExample(clean, False, f"c{i}", "p"))

    predictor = HelpNeedPredictor.fit(examples, kind="xgboost", random_state=0)
    report = validate_per_kc(predictor, examples, thin_threshold=10)

    metrics = _metrics_for(report, _A.value)
    assert metrics.n_examples == 120
    assert metrics.auc is not None and 0.5 <= metrics.auc <= 1.0
    assert 0.0 <= metrics.calibration_gap <= 1.0


def _report_with(aucs: dict[str, float | None], *, thin: tuple[str, ...] = ()) -> PerKcReport:
    """Build a PerKcReport with pinned per-KC AUCs (for trustworthy_kcs tests)."""
    from app.helpneed.per_kc_validation import KcMetrics

    entries = [
        KcMetrics(
            kc=kc, n_examples=100, positive_rate=0.5, auc=auc, calibration_gap=0.0, pooled_kcs=(kc,)
        )
        for kc, auc in aucs.items()
    ]
    if thin:
        entries.append(
            KcMetrics(
                kc=THIN_BUCKET_LABEL,
                n_examples=10,
                positive_rate=0.5,
                auc=0.99,  # even a high thin-bucket AUC must NOT count as trustworthy
                calibration_gap=0.0,
                pooled_kcs=thin,
            )
        )
    return PerKcReport(per_kc=tuple(entries), overall_auc=0.9, thin_threshold=30)


def test_trustworthy_kcs_keeps_strong_drops_weak() -> None:
    """Tier-2 gate: only KCs at/above the AUC bar are trustworthy for the proactive arm."""
    report = _report_with({"KC_strong": 0.92, "KC_percent": 0.819, "KC_rate_problems": 0.744})
    trusted = trustworthy_kcs(report, min_auc=0.85)
    assert trusted == frozenset({"KC_strong"})


def test_trustworthy_threshold_is_inclusive() -> None:
    """A KC exactly at the bar is trustworthy (>= , not >)."""
    report = _report_with({"KC_edge": 0.85})
    assert "KC_edge" in trustworthy_kcs(report, min_auc=0.85)


def test_trustworthy_excludes_thin_bucket_even_if_high_auc() -> None:
    """The pooled thin bucket is never trustworthy — too few examples to gate on."""
    report = _report_with({"KC_strong": 0.95}, thin=("KC_obscure_a", "KC_obscure_b"))
    trusted = trustworthy_kcs(report, min_auc=0.85)
    assert trusted == frozenset({"KC_strong"})
    assert THIN_BUCKET_LABEL not in trusted


def test_trustworthy_excludes_undefined_auc() -> None:
    """A KC with undefined AUC (single-class slice) can't be trusted to fire proactively."""
    report = _report_with({"KC_singleclass": None, "KC_ok": 0.9})
    assert trustworthy_kcs(report, min_auc=0.85) == frozenset({"KC_ok"})


def test_label_space_drift_invariant() -> None:
    """The training label space must be a subset of the one-hot space, in enum order.

    This is the §1-seam drift guard: every KC the CCSS→KC map (T1's lane) can emit MUST
    be a real ``KnowledgeComponentId`` and therefore have a one-hot column, and KC_ORDER
    MUST be exactly the enum (the column order the artifact is trained against). If T1
    widens the enum/map and this drifts, the re-fit would train a label space the live
    one-hot can't represent — caught here before it reaches an artifact.
    """
    assert KC_ORDER == tuple(KnowledgeComponentId)
    for _prefix, kc in _CCSS_PREFIX_TO_KC:
        assert kc in KC_ORDER
