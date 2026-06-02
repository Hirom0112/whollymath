"""Tests for the EXPERIMENTAL synthetic v2 HelpNeed training path (Slice 0.1, V2_TODO WAVE 0).

These pin that the experimental path:

  - runs end-to-end on SYNTHETIC persona traces → ``events_features`` v2 columns → the SAME
    XGBoost, producing a fitted predictor;
  - scores a single v2 feature row in well under the turn-loop's 100ms budget (§8.1; reuses the
    existing latency-test pattern from ``test_predictor``);
  - writes to a SEPARATE, clearly-named EXPERIMENTAL artifact path and leaves the committed v1
    production artifact UNTOUCHED (the load-bearing safety property — we must never disturb the
    shipped model).

HONEST SCOPE (PROJECT.md §9; V2_TODO Slice 0.1): this trains an OBSERVE-ONLY / SYNTHETIC model
that AWAITS real-student validation. It is NOT a shippable v2 and is asserted as such (the v1
artifact is the one the live loop loads; this never replaces it).
"""

from __future__ import annotations

import time

from app.helpneed.artifact import ARTIFACT_PATH
from app.helpneed.events_features import FEATURE_NAMES_V2
from app.helpneed.train_synthetic import (
    DEFAULT_SYNTHETIC_SEQUENCE,
    build_synthetic_v2_examples,
    train_synthetic_v2,
)


def test_build_synthetic_examples_yields_labeled_v2_rows() -> None:
    """The builder produces (v2-feature, label) rows across the personas, full model width."""
    examples = build_synthetic_v2_examples()
    assert examples, "expected synthetic examples across the persona roster"
    # Both classes present — a struggler (Hugo) contributes positives, a clean learner negatives.
    labels = {ex.label for ex in examples}
    assert labels == {True, False}
    for ex in examples:
        assert len(ex.features.to_vector()) == len(FEATURE_NAMES_V2)


def test_train_synthetic_runs_end_to_end_and_separates_struggle() -> None:
    """The experimental path fits the XGBoost on synthetic traces and learns the help-need split."""
    predictor, report = train_synthetic_v2()
    assert report.n_examples == len(build_synthetic_v2_examples())
    assert 0.0 < report.positive_rate < 1.0  # both classes seen
    # A clearly hint-dependent (struggling) row must score higher than a clean one.
    struggling, clean = report.probe_scores
    assert struggling > clean


def test_single_row_inference_is_sub_100ms() -> None:
    """A single v2-row inference fits the turn-loop latency budget (§8.1); reuses §3.5's pattern."""
    predictor, _ = train_synthetic_v2()
    probe = build_synthetic_v2_examples()[0].features
    predictor.predict_proba(probe)  # warm any one-time setup
    start = time.perf_counter()
    predictor.predict_proba(probe)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert elapsed_ms < 100.0, f"inference took {elapsed_ms:.1f}ms (budget 100ms)"


def test_writes_experimental_artifact_and_leaves_v1_untouched(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The experimental artifact lands at the requested path; the committed v1 model is intact."""
    v1_before = ARTIFACT_PATH.read_bytes()
    out = tmp_path / "helpneed_v2_synthetic_experimental.joblib"
    assert not out.exists()
    train_synthetic_v2(out_path=out)
    assert out.exists(), "experimental artifact was not written"
    assert out != ARTIFACT_PATH
    # The shipped v1 production artifact must be byte-for-byte unchanged.
    assert ARTIFACT_PATH.read_bytes() == v1_before


def test_default_sequence_is_nonempty_and_deterministic_inputs() -> None:
    """The default training sequence is a concrete, non-empty problem block (deterministic seed)."""
    assert DEFAULT_SYNTHETIC_SEQUENCE
    seeds = [spec.seed for spec in DEFAULT_SYNTHETIC_SEQUENCE]
    assert seeds == sorted(seeds) or len(set(seeds)) == len(seeds)
