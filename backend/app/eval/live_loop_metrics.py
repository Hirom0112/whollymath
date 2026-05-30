"""Live-loop evidence metrics — "branching is not enough", prove it (Slice HR.D1).

The PRD demands evidence the hyperreactive loop HELPS, not just that it changes the UI. This module
computes the honestly-computable live-loop metrics from the shipped components (no live A/B run
needed for these three), so the pitch can report real numbers with their counter-metrics:

  - classifier_accuracy: on a labeled set of behavioral scenarios (a known intended state per
    scenario), how often the deterministic 6-state classifier (HR.B2) names the intended state.
    Counter-metric: a classifier that fired the wrong state would morph the UI wrongly.
  - reason_label_coverage: of the adaptations the policy fires, the fraction that carry a one-line
    on-screen reason (the refuse-rule "every change carries a reason"). By construction this is
    1.0 — reported as a GUARANTEE, with the scenario count, not a hopeful estimate.
  - sensor_noise_agreement: typed vs OCR-transcribed answer — the fraction graded to the SAME
    verdict. The multimodal robustness check (HR.C2): a second INPUT must not change correctness.

These are run as an eval (CLAUDE.md §9), not a unit gate; the metric functions are pure and tested.
The responsiveness→hint-dependence and transfer-after-scaffold-removal deltas need a live A/B run
(gated on the arm) and are out of scope here — flagged honestly rather than faked.
"""

from __future__ import annotations

from dataclasses import dataclass

from sympy import Rational

from app.api.live_adaptation import propose_adaptation_view
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import AnswerKind, Problem
from app.domain.verifier import verify
from app.helpneed.live_signal_features import LiveSignalFeatures
from app.policy.state_classifier import LearnerState, classify_state
from app.policy.surface_states import SurfaceState
from app.tutor.transcribed_answer import read_back_answer

_ADD = KnowledgeComponentId.ADDITION_UNLIKE


@dataclass(frozen=True)
class _ClassifierCase:
    """A labeled behavioral scenario: these signals SHOULD read as ``expected``."""

    features: LiveSignalFeatures
    helpneed_score: float
    correct_streak_no_hint: int
    distinct_recent_representations: int
    expected: LearnerState


def _feat(
    *,
    ttfi_ms: int | None = 4000,
    attempts: int = 1,
    revisions: int = 1,
    idle: int = 0,
    hints: int = 0,
) -> LiveSignalFeatures:
    return LiveSignalFeatures(
        time_to_first_interaction_ms=ttfi_ms,
        current_attempts=attempts,
        current_revisions=revisions,
        current_idle_events=idle,
        current_hint_requests=hints,
        current_requested_answer=False,
        recent_attempts_mean=float(attempts),
        recent_revisions_mean=float(revisions),
        recent_idle_mean=float(idle),
        recent_hint_rate=0.0,
        recent_give_up_rate=0.0,
        problems_seen=4,
    )


# A labeled scenario per state — the behaviors a learner in that state exhibits.
_CLASSIFIER_CASES: tuple[_ClassifierCase, ...] = (
    _ClassifierCase(_feat(idle=3), 0.5, 0, 1, LearnerState.IDLE_AVOIDING),
    _ClassifierCase(_feat(ttfi_ms=600, attempts=3, revisions=0), 0.4, 0, 1, LearnerState.GUESSING),
    _ClassifierCase(_feat(), 0.2, 3, 2, LearnerState.FLUENT_READY),
    _ClassifierCase(_feat(), 0.2, 3, 1, LearnerState.PATTERN_MATCHING),
    _ClassifierCase(_feat(attempts=3), 0.8, 0, 1, LearnerState.CONFUSED),
    _ClassifierCase(_feat(attempts=2, revisions=2), 0.45, 0, 1, LearnerState.PRODUCTIVE_STRUGGLE),
)


def classifier_accuracy(
    cases: tuple[_ClassifierCase, ...] = _CLASSIFIER_CASES,
) -> tuple[float, int]:
    """Fraction of labeled scenarios the classifier names correctly, and the case count."""
    hits = sum(
        1
        for c in cases
        if classify_state(
            c.features,
            helpneed_score=c.helpneed_score,
            correct_streak_no_hint=c.correct_streak_no_hint,
            distinct_recent_representations=c.distinct_recent_representations,
        )
        is c.expected
    )
    return hits / len(cases), len(cases)


# The states that DO fire an adaptation (productive-struggle is a protected no-op).
_FIRING_STATES: tuple[LearnerState, ...] = (
    LearnerState.CONFUSED,
    LearnerState.GUESSING,
    LearnerState.PATTERN_MATCHING,
    LearnerState.IDLE_AVOIDING,
    LearnerState.FLUENT_READY,
)


def reason_label_coverage() -> tuple[float, int]:
    """Of the adaptations that fire (from S1), the fraction carrying a non-empty reason, + count."""
    fired = [
        propose_adaptation_view(state, _ADD, SurfaceState.SYMBOLIC_FOCUS)
        for state in _FIRING_STATES
    ]
    present = [v for v in fired if v is not None]
    if not present:
        return 1.0, 0
    with_reason = sum(1 for v in present if v.reason.strip())
    return with_reason / len(present), len(present)


def _problem(correct: Rational) -> Problem:
    return Problem(
        problem_id="EVAL",
        kc=_ADD,
        surface_format=Representation.SYMBOLIC,
        statement="1/3 + 1/4 = ?",
        correct_value=correct,
        representations_available=(Representation.SYMBOLIC,),
        operands=(Rational(1, 3), Rational(1, 4)),
        answer_kind=AnswerKind.NUMERIC,
    )


# (typed answer, OCR transcription of the SAME handwritten answer) for the 7/12 problem.
_SENSOR_CASES: tuple[tuple[str, str], ...] = (
    ("7/12", "\\frac{7}{12}"),  # correct, both
    ("2/7", "\\frac{2}{7}"),  # wrong, both
    ("7/12", "$= 7 / 12$"),  # correct with delimiters/spaces
)


def sensor_noise_agreement() -> tuple[float, int]:
    """Fraction of cases where the OCR-transcribed answer grades to the SAME verdict as typed."""
    problem = _problem(Rational(7, 12))
    agree = 0
    for typed, transcription in _SENSOR_CASES:
        ocr = read_back_answer(transcription)
        if ocr is not None and verify(problem, typed).is_correct == verify(problem, ocr).is_correct:
            agree += 1
    return agree / len(_SENSOR_CASES), len(_SENSOR_CASES)


@dataclass(frozen=True)
class LiveLoopMetrics:
    """The computed live-loop evidence (HR.D1), each with the sample size it was measured over."""

    classifier_accuracy: float
    classifier_n: int
    reason_label_coverage: float
    reason_label_n: int
    sensor_noise_agreement: float
    sensor_noise_n: int


def compute_live_loop_metrics() -> LiveLoopMetrics:
    """Compute the three honestly-computable live-loop metrics (HR.D1)."""
    acc, acc_n = classifier_accuracy()
    cov, cov_n = reason_label_coverage()
    agree, agree_n = sensor_noise_agreement()
    return LiveLoopMetrics(
        classifier_accuracy=acc,
        classifier_n=acc_n,
        reason_label_coverage=cov,
        reason_label_n=cov_n,
        sensor_noise_agreement=agree,
        sensor_noise_n=agree_n,
    )


def format_report(metrics: LiveLoopMetrics) -> str:
    """A plain-text report of the live-loop metrics with their sample sizes (honest reporting)."""
    return (
        "Live-loop evidence (HR.D1)\n"
        f"  classifier accuracy:     {metrics.classifier_accuracy:.0%} "
        f"(n={metrics.classifier_n} labeled states)\n"
        f"  reason-label coverage:   {metrics.reason_label_coverage:.0%} "
        f"(n={metrics.reason_label_n} fired adaptations)\n"
        f"  typed/OCR verdict agree: {metrics.sensor_noise_agreement:.0%} "
        f"(n={metrics.sensor_noise_n} answers)\n"
        "  NOTE: responsiveness->hint-dependence + transfer-after-scaffold-removal deltas\n"
        "  need a live A/B run (gated on the proactive arm) — not computed here."
    )


__all__ = [
    "LiveLoopMetrics",
    "classifier_accuracy",
    "compute_live_loop_metrics",
    "format_report",
    "reason_label_coverage",
    "sensor_noise_agreement",
]
