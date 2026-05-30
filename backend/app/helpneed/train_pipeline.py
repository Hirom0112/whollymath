"""HelpNeed v1 training pipeline (Slice 3.5).

Ties the pieces together: parse the EDM Cup traces (Slice 3.2) → build leakage-safe
features + labels (Slices 3.3/3.4) → train the XGBoost model and the logistic
baseline, and report holdout accuracy/AUC plus SHAP top features (TECH_STACK §5).

``train_and_evaluate`` is the testable core (a deterministic split + fit + score).
``load_examples_from_edmcup`` is a thin wrapper over the already-tested parser +
feature builder. ``main`` is the one-off run over the local 1.44 GB dataset
(CLAUDE.md §9: pulling/training scripts are scripts, not mandatory-TDD systems) — it
prints the numbers we record in the decision log. No LLM anywhere (§8.1).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from app.helpneed.features import TrainingExample, build_examples
from app.helpneed.parse_edmcup import (
    ParseStats,
    load_fraction_problems,
    parse_action_logs,
)
from app.helpneed.per_kc_validation import format_report, trustworthy_kcs, validate_per_kc
from app.helpneed.predictor import HelpNeedPredictor, examples_to_matrix, top_shap_features


@dataclass(frozen=True)
class TrainingReport:
    """Holdout metrics for one trained model — the numbers the writeup quotes."""

    kind: str
    n_examples: int
    positive_rate: float
    holdout_accuracy: float
    holdout_auc: float
    majority_baseline_accuracy: float


def split_examples(
    examples: Sequence[TrainingExample],
    *,
    random_state: int = 0,
    test_size: float = 0.25,
) -> tuple[list[TrainingExample], list[TrainingExample]]:
    """Deterministic stratified train/test split (PROJECT.md §4.1).

    Extracted so ``train_and_evaluate`` (overall holdout) and the per-KC validation in
    ``main`` recover the *same* holdout from the same args — one fit, validated two ways.
    """
    from sklearn.model_selection import train_test_split

    labels = [ex.label for ex in examples]
    train_examples, test_examples = train_test_split(
        list(examples),
        test_size=test_size,
        random_state=random_state,
        stratify=labels,
    )
    return train_examples, test_examples


def train_and_evaluate(
    examples: Sequence[TrainingExample],
    *,
    kind: str = "xgboost",
    random_state: int = 0,
    test_size: float = 0.25,
) -> tuple[HelpNeedPredictor, TrainingReport]:
    """Stratified train/test split, fit, and score on the holdout (deterministic).

    Returns the fitted predictor (trained on the TRAIN split) and its report. AUC is
    reported as ``nan`` if the holdout happens to be single-class (degenerate split).
    """
    from sklearn.metrics import accuracy_score, roc_auc_score

    labels = [ex.label for ex in examples]
    train_examples, test_examples = split_examples(
        examples, random_state=random_state, test_size=test_size
    )
    predictor = HelpNeedPredictor.fit(train_examples, kind=kind, random_state=random_state)

    x_test, y_test = examples_to_matrix(test_examples)
    proba = predictor.predict_proba_matrix(x_test)
    predicted = (proba >= 0.5).astype(int)

    accuracy = float(accuracy_score(y_test, predicted))
    positive_fraction = float(y_test.mean())
    try:
        auc = float(roc_auc_score(y_test, proba))
    except ValueError:
        auc = float("nan")  # single-class holdout — AUC undefined

    report = TrainingReport(
        kind=kind,
        n_examples=len(examples),
        positive_rate=float(sum(labels) / len(labels)) if labels else 0.0,
        holdout_accuracy=accuracy,
        holdout_auc=auc,
        majority_baseline_accuracy=max(positive_fraction, 1.0 - positive_fraction),
    )
    return predictor, report


def load_examples_from_edmcup(
    data_dir: Path,
    *,
    row_limit: int | None = None,
    stats: ParseStats | None = None,
) -> list[TrainingExample]:
    """Parse the local EDM Cup data and build training examples (parser + features)."""
    fraction_problems = load_fraction_problems(data_dir / "problem_details.csv")
    turns = parse_action_logs(
        data_dir / "action_logs.csv",
        fraction_problems,
        row_limit=row_limit,
        stats=stats,
    )
    return build_examples(turns)


def main() -> None:
    """Train v1 on the local EDM Cup data and print the holdout report + SHAP.

    Honors ``WHOLLYMATH_EDMCUP_ROW_LIMIT`` (cap on action rows scanned) so a fast
    pass is possible without the full 24M-row read. Run from ``backend/``:
        uv run python -m app.helpneed.train_pipeline
    """
    data_dir = Path(os.environ.get("WHOLLYMATH_EDMCUP_DIR", "data/edmcup2023"))
    raw_limit = os.environ.get("WHOLLYMATH_EDMCUP_ROW_LIMIT", "")
    row_limit = int(raw_limit) if raw_limit else None

    stats = ParseStats()
    print(f"Parsing {data_dir} (row_limit={row_limit}) …")
    examples = load_examples_from_edmcup(data_dir, row_limit=row_limit, stats=stats)
    print(
        f"  rows_read={stats.rows_read:,}  fraction_turns(examples)={len(examples):,}  "
        f"skipped_non_fraction={stats.skipped_non_fraction_rows:,}  "
        f"malformed={stats.malformed_rows:,}"
    )
    if not examples:
        print("No examples parsed — check the data directory.")
        return

    xgb_predictor, xgb_report = train_and_evaluate(examples, kind="xgboost")
    _, logistic_report = train_and_evaluate(examples, kind="logistic")
    for report in (xgb_report, logistic_report):
        print(
            f"  [{report.kind:8}] acc={report.holdout_accuracy:.3f}  auc={report.holdout_auc:.3f}  "
            f"majority={report.majority_baseline_accuracy:.3f}  pos_rate={report.positive_rate:.3f}"
        )

    x_all, _ = examples_to_matrix(examples)
    print("  SHAP top features (xgboost):")
    for name, value in top_shap_features(xgb_predictor, x_all):
        print(f"    {name:28} {value:.4f}")

    # Per-KC validation on the SAME holdout the xgb report used (re-derived via the
    # deterministic split). The honest-reporting deliverable for the cross-topic model:
    # which KCs score well, which sit in the thin bucket (T1_T2_COORDINATION §1).
    _, test_examples = split_examples(examples)
    per_kc_report = validate_per_kc(xgb_predictor, test_examples)
    for line in format_report(per_kc_report):
        print(line)

    # The Tier-2 trustworthy set the proactive arm may fire on (T1_T2_COORDINATION §"Tier-2"):
    # the KCs whose validated per-KC AUC clears the bar. Derived from the SAME holdout report —
    # never a hardcoded KC list — and stamped onto the production artifact below so the live gate
    # reads the validated set off the loaded model (no holdout data at boot to recompute it).
    trusted = trustworthy_kcs(per_kc_report)
    print(f"  Tier-2 trustworthy KCs (proactive-eligible, AUC>=0.85): {sorted(trusted)}")

    # Optionally persist the PRODUCTION artifact (Slice 4.4.1). The reported metrics
    # above come from the 75/25 holdout split; the deployed model is fit on ALL
    # examples (the holdout exists to measure quality, not to be thrown away in
    # production). The trustworthy set is measured on the holdout (above) and stamped onto
    # the all-examples model, so the artifact carries the validated Tier-2 allow-list. Saved
    # only when an output path is given, so the default run stays a pure reporting pass.
    out_path = os.environ.get("WHOLLYMATH_HELPNEED_OUT", "")
    if out_path:
        destination = Path(out_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        production = replace(
            HelpNeedPredictor.fit(examples, kind="xgboost"), trustworthy_kcs=trusted
        )
        production.save(destination)
        print(
            f"  saved production artifact (fit on all {len(examples):,} examples, "
            f"{len(trusted)} trustworthy KCs stamped) -> {destination}"
        )


if __name__ == "__main__":
    main()


__all__ = [
    "TrainingReport",
    "load_examples_from_edmcup",
    "split_examples",
    "train_and_evaluate",
]
