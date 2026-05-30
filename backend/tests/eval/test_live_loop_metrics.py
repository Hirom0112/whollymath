"""Tests for the live-loop evidence metrics (Slice HR.D1).

The metrics are an eval, but the metric functions are pure and pinned: the classifier names its
labeled states, every fired adaptation carries a reason, and typed/OCR verdicts agree.
"""

from __future__ import annotations

from app.eval.live_loop_metrics import (
    classifier_accuracy,
    compute_live_loop_metrics,
    format_report,
    reason_label_coverage,
    sensor_noise_agreement,
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


def test_report_renders_with_sample_sizes() -> None:
    metrics = compute_live_loop_metrics()
    report = format_report(metrics)
    assert "classifier accuracy" in report
    assert "reason-label coverage" in report
    assert "typed/OCR verdict agree" in report
    # Honest reporting: the un-computed deltas are flagged, not faked.
    assert "live A/B run" in report
