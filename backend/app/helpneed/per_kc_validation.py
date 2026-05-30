"""Per-KC validation of the HelpNeed predictor (T2 deliverable; T1_T2_COORDINATION §1).

One pooled, cross-topic model serves every Grade-6 KC after the re-fit (§0 of the
coordination note). A single "overall AUC 0.89" can hide a topic scoring at chance,
so the honest-reporting deliverable is to slice quality **per KC**: AUC, calibration
gap, and positive rate for each KC that has enough held-out examples, with the thin
ones pooled into one clearly-labelled bucket rather than silently dropped (CLAUDE.md
§9). The complement of ``train_pipeline.train_and_evaluate`` (which reports the
*overall* holdout) — this module answers "and how does each KC do?".

Boundaries (CLAUDE.md §8.1): no LLM, no SymPy, no DB. scikit-learn metrics only,
imported lazily so importing this module stays cheap. The scorer is duck-typed on
``predict_proba_matrix`` (``HelpNeedPredictor`` satisfies it) so the validation is
testable against a pinned-probability stub and stays a pure function of
(predictions, labels, KCs) — deterministic (PROJECT.md §4.1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app.helpneed.features import TrainingExample
from app.helpneed.predictor import examples_to_matrix

# A KC needs at least this many held-out examples for a stable per-KC AUC; below it the
# AUC is too noisy to report on its own, so the KC is pooled into the thin bucket. Named
# so a change is a deliberate, reviewed edit (tunable in the week 4-5 eval pass).
DEFAULT_THIN_THRESHOLD = 30

# The ``kc`` label of the pooled low-N bucket. Not a real ``KnowledgeComponentId`` value
# (those are ``KC_...`` / representation strings), so it can never collide with one.
THIN_BUCKET_LABEL = "__thin__"

# Tier-2 weak-KC guard: the proactive-intervention arm may only fire on a KC whose validated
# per-KC AUC clears this bar. Below it, the predictor isn't trustworthy enough to drive a
# proactive nudge, so the tutor falls back to the deterministic reactive layer (SymPy verdict →
# morph + misconception model) on that KC. 0.85 cleanly separates the RP/expression-eval cluster
# (~0.74–0.82 — the genuinely weak topics) from the rest; tunable in the eval pass.
DEFAULT_TRUSTWORTHY_MIN_AUC = 0.85


class _BatchScorer(Protocol):
    """The slice of the predictor API per-KC validation needs: batch P(unproductive)."""

    def predict_proba_matrix(self, x: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class KcMetrics:
    """Held-out quality for one KC (or the pooled thin bucket).

    - ``kc``               the KC value, or ``THIN_BUCKET_LABEL`` for the pooled bucket.
    - ``n_examples``       held-out examples scored for this entry.
    - ``positive_rate``    observed fraction of unproductive turns (the base rate).
    - ``auc``              ROC-AUC, or ``None`` when the slice is single-class (undefined).
    - ``calibration_gap``  ``|mean(predicted) − observed positive rate|`` — a simple,
      robust-on-small-N calibration summary (a binned ECE is the week 4-5 upgrade).
    - ``pooled_kcs``       the KC values folded into this entry: ``(kc,)`` for a normal
      entry, the sorted list of thin KCs for the bucket (so nothing is hidden).
    """

    kc: str
    n_examples: int
    positive_rate: float
    auc: float | None
    calibration_gap: float
    pooled_kcs: tuple[str, ...]


@dataclass(frozen=True)
class PerKcReport:
    """The per-KC validation result: one ``KcMetrics`` per reported group + the overall."""

    per_kc: tuple[KcMetrics, ...]
    overall_auc: float | None
    thin_threshold: int


def _auc(labels: np.ndarray, proba: np.ndarray) -> float | None:
    """ROC-AUC, or ``None`` if the slice is single-class (AUC undefined there)."""
    from sklearn.metrics import roc_auc_score

    if len(np.unique(labels)) < 2:
        return None
    return float(roc_auc_score(labels, proba))


def _metrics(
    kc_label: str, pooled_kcs: tuple[str, ...], labels: np.ndarray, proba: np.ndarray
) -> KcMetrics:
    """Compute the metrics for one already-selected slice of examples."""
    return KcMetrics(
        kc=kc_label,
        n_examples=int(labels.size),
        positive_rate=float(labels.mean()),
        auc=_auc(labels, proba),
        calibration_gap=float(abs(proba.mean() - labels.mean())),
        pooled_kcs=pooled_kcs,
    )


def validate_per_kc(
    scorer: _BatchScorer,
    examples: Sequence[TrainingExample],
    *,
    thin_threshold: int = DEFAULT_THIN_THRESHOLD,
) -> PerKcReport:
    """Score ``examples`` with ``scorer`` and report AUC + calibration sliced by KC.

    KCs with ``>= thin_threshold`` examples get their own entry (sorted by KC value for
    determinism); the rest are pooled into one ``THIN_BUCKET_LABEL`` entry appended last,
    recording which KCs it covers. Raises ``ValueError`` on empty input — validating
    nothing is a caller error, not a silent empty report (CLAUDE.md §8.5).
    """
    if not examples:
        raise ValueError("validate_per_kc requires at least one example")

    x, y = examples_to_matrix(examples)
    proba = np.asarray(scorer.predict_proba_matrix(x), dtype=float)

    # Group row indices by the example's KC (the join key for the per-KC slice).
    indices_by_kc: dict[str, list[int]] = {}
    for i, example in enumerate(examples):
        indices_by_kc.setdefault(example.features.kc.value, []).append(i)

    entries: list[KcMetrics] = []
    thin_rows: list[int] = []
    thin_kcs: list[str] = []
    for kc_value in sorted(indices_by_kc):
        rows = indices_by_kc[kc_value]
        if len(rows) >= thin_threshold:
            idx = np.asarray(rows, dtype=int)
            entries.append(_metrics(kc_value, (kc_value,), y[idx], proba[idx]))
        else:
            thin_rows.extend(rows)
            thin_kcs.append(kc_value)

    if thin_rows:
        idx = np.asarray(thin_rows, dtype=int)
        entries.append(_metrics(THIN_BUCKET_LABEL, tuple(sorted(thin_kcs)), y[idx], proba[idx]))

    return PerKcReport(
        per_kc=tuple(entries),
        overall_auc=_auc(y, proba),
        thin_threshold=thin_threshold,
    )


def trustworthy_kcs(
    report: PerKcReport,
    *,
    min_auc: float = DEFAULT_TRUSTWORTHY_MIN_AUC,
) -> frozenset[str]:
    """The KC values the proactive arm may fire on: validated per-KC AUC ≥ ``min_auc``.

    Tier-2 of the weak-KC plan (T1_T2_COORDINATION §"Tier-2"): the `SustainedHelpNeedGate`
    reads this set and only intervenes proactively where the model is trustworthy; everything
    else falls back to the deterministic reactive layer. Excludes the pooled thin bucket (too
    few examples to gate on, regardless of its AUC) and any KC with an undefined AUC. A pure
    projection of the per-KC report — no new data, re-derived each re-fit so the gate widens
    automatically as the model improves (never a hardcoded KC list).
    """
    return frozenset(
        m.kc
        for m in report.per_kc
        if m.kc != THIN_BUCKET_LABEL and m.auc is not None and m.auc >= min_auc
    )


def format_report(report: PerKcReport) -> list[str]:
    """Human-readable lines for the training-pipeline run (one per KC + overall)."""
    overall = "n/a" if report.overall_auc is None else f"{report.overall_auc:.3f}"
    lines = [f"  per-KC validation (thin<{report.thin_threshold}, overall AUC={overall}):"]
    for m in report.per_kc:
        auc = "  n/a" if m.auc is None else f"{m.auc:.3f}"
        label = m.kc
        if m.kc == THIN_BUCKET_LABEL:
            label = f"{THIN_BUCKET_LABEL}{list(m.pooled_kcs)}"
        lines.append(
            f"    {label:30} n={m.n_examples:5d}  auc={auc}  "
            f"cal_gap={m.calibration_gap:.3f}  pos={m.positive_rate:.3f}"
        )
    return lines


__all__ = [
    "DEFAULT_THIN_THRESHOLD",
    "DEFAULT_TRUSTWORTHY_MIN_AUC",
    "THIN_BUCKET_LABEL",
    "KcMetrics",
    "PerKcReport",
    "format_report",
    "trustworthy_kcs",
    "validate_per_kc",
]
