"""Tests for the live-loop evidence metrics (Slice HR.D1).

The metrics are an eval, but the metric functions are pure and pinned: the classifier names its
labeled states, every fired adaptation carries a reason, and typed/OCR verdicts agree.
"""

from __future__ import annotations

from app.eval.live_loop_metrics import (
    UI_CHANGE_FREQUENCY_BOUND,
    classifier_accuracy,
    compute_live_loop_metrics,
    format_report,
    intent_routing_accuracy,
    reason_label_coverage,
    sensor_noise_agreement,
    ui_change_frequency,
)


def test_classifier_names_its_labeled_states() -> None:
    accuracy, n = classifier_accuracy()
    assert n == 6  # one labeled scenario per state
    assert accuracy == 1.0  # the deterministic classifier names each labeled behavior


def test_every_fired_adaptation_carries_a_reason() -> None:
    coverage, n = reason_label_coverage()
    assert n >= 1
    assert coverage == 1.0  # refuse-rule: every change carries a one-line reason


def test_typed_and_ocr_answers_agree_on_the_verdict() -> None:
    agreement, n = sensor_noise_agreement()
    assert n == 3
    assert agreement == 1.0  # a second INPUT modality never changes correctness (SymPy owns it)


def test_ui_change_frequency_is_within_the_bound() -> None:
    """The morph/nudge rate over the labeled states is computed and within the target bound.

    Counter-metric to "did the UI change too often" (HYPERREACTIVE §6): productive-struggle is a
    protected no-op, so not every classified state fires — the rate must sit at or below the bound.
    """
    rate, n = ui_change_frequency()
    assert n == 6  # one labeled scenario per state
    assert 0.0 <= rate <= 1.0
    assert rate <= UI_CHANGE_FREQUENCY_BOUND


def test_protected_struggle_is_not_counted_as_a_ui_change() -> None:
    """Productive-struggle must NOT fire — so the rate is strictly below 1.0 because of it."""
    rate, _ = ui_change_frequency()
    assert rate < 1.0  # at least the protected productive-struggle state fires no change


def test_intent_routing_accuracy_over_all_specs() -> None:
    """Routing accuracy = fraction of error routes that morph to a manipulative surface.

    HYPERREACTIVE §6 asks intent→UI routing accuracy ≥ 0.75 — "did the morph fix the error?".
    A route back to the symbolic default is NOT a morph, so it does not count. The metric is
    computed over every registered lesson spec and reported honestly (it is < 1.0 today because
    the ratio/percent KCs route to symbolic — there is no manipulative for them yet).
    """
    accuracy, n_routes = intent_routing_accuracy()
    assert n_routes > 0
    assert 0.0 <= accuracy <= 1.0


def test_report_renders_with_sample_sizes() -> None:
    metrics = compute_live_loop_metrics()
    report = format_report(metrics)
    assert "classifier accuracy" in report
    assert "reason-label coverage" in report
    assert "typed/OCR verdict agree" in report
    assert "UI-change frequency" in report
    assert "intent->UI routing accuracy" in report
    # Honest reporting: the un-computed deltas are flagged, not faked.
    assert "live A/B run" in report
