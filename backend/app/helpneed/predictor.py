"""The HelpNeed predictor — XGBoost classifier + logistic baseline (Slice 3.5).

Estimates P(unproductive) per turn from the Slice-3.3 features (PROJECT.md §3.7,
ARCHITECTURE.md §8). TECH_STACK §5 locks **scikit-learn + XGBoost** (interpretable
via SHAP, sub-100ms CPU inference, no GPU), with **logistic regression as a baseline
only**. This module wraps a fitted estimator behind one small, stable interface so
the turn loop (Slice 4.4) can score a turn without knowing which model is inside.

Boundaries (CLAUDE.md §8.1): **no LLM** anywhere — XGBoost only, as §8.1 requires of
the turn loop. The ML libraries are imported LAZILY inside the builders so importing
this module stays cheap, and so SHAP (an analysis-only dev dependency) never loads on
the inference path — ``top_shap_features`` imports it on demand.

Determinism: ``fit`` takes a ``random_state`` so training is reproducible
(PROJECT.md §4.1); inference is a pure function of the fitted model + features.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from app.helpneed.features import FEATURE_NAMES, HelpNeedFeatures, TrainingExample

# The model kinds this wrapper supports. "xgboost" is the production model; "logistic"
# is the interpretable baseline for the writeup comparison (TECH_STACK §5).
ModelKind = str


class _ProbaEstimator(Protocol):
    """The slice of the sklearn/xgboost estimator API this wrapper uses.

    A Protocol (not ``Any``) so mypy --strict checks our calls, even though the ML
    libraries themselves ship no stubs (they satisfy this structurally).
    """

    def fit(self, x: np.ndarray, y: np.ndarray) -> object: ...
    def predict_proba(self, x: np.ndarray) -> np.ndarray: ...


def examples_to_matrix(examples: Sequence[TrainingExample]) -> tuple[np.ndarray, np.ndarray]:
    """Stack training examples into the (X feature matrix, y label vector) arrays."""
    x = np.asarray([ex.features.to_vector() for ex in examples], dtype=float)
    y = np.asarray([1 if ex.label else 0 for ex in examples], dtype=int)
    return x, y


def _build_model(kind: ModelKind, random_state: int) -> _ProbaEstimator:
    """Construct an UNFITTED estimator for ``kind`` (ML libs imported lazily)."""
    if kind == "xgboost":
        from xgboost import XGBClassifier

        # Small, regularized trees: enough capacity for the §3.7 feature set, fast to
        # train, sub-ms single-row inference. CPU only (no GPU — TECH_STACK §5).
        model = XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=random_state,
            n_jobs=1,
        )
        return model
    if kind == "logistic":
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        # Scale first: logistic regression is scale-sensitive (latency_ms dwarfs the
        # 0–1 rates). The baseline exists to be BEATEN by XGBoost in the writeup.
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, random_state=random_state),
        )
        return model  # type: ignore[no-any-return]  # sklearn Pipeline is untyped (stubs absent)
    raise ValueError(f"unknown model kind: {kind!r} (expected 'xgboost' or 'logistic')")


@dataclass
class HelpNeedPredictor:
    """A fitted HelpNeed model behind a stable ``predict_proba`` interface.

    Constructed via :meth:`fit` (or :meth:`load`), never by hand. ``kind`` records
    which model is inside so SHAP (tree-only) can guard, and so a reloaded predictor
    reports its provenance.
    """

    model: _ProbaEstimator
    kind: ModelKind

    @classmethod
    def fit(
        cls,
        examples: Sequence[TrainingExample],
        *,
        kind: ModelKind = "xgboost",
        random_state: int = 0,
    ) -> HelpNeedPredictor:
        """Train on labeled examples (Slice 3.3 features + 3.4 labels)."""
        x, y = examples_to_matrix(examples)
        model = _build_model(kind, random_state)
        model.fit(x, y)
        return cls(model=model, kind=kind)

    def predict_proba(self, features: HelpNeedFeatures) -> float:
        """P(unproductive) for one turn — the single-row, sub-100ms inference path."""
        x = np.asarray([features.to_vector()], dtype=float)
        return float(self.model.predict_proba(x)[0, 1])

    def predict_proba_matrix(self, x: np.ndarray) -> np.ndarray:
        """P(unproductive) for a batch (column 1 of predict_proba) — for evaluation."""
        return np.asarray(self.model.predict_proba(x)[:, 1], dtype=float)

    def save(self, path: Path) -> None:
        """Persist the fitted model + kind via joblib (TECH_STACK §5)."""
        import joblib

        joblib.dump({"model": self.model, "kind": self.kind}, path)

    @classmethod
    def load(cls, path: Path) -> HelpNeedPredictor:
        """Reload a predictor saved by :meth:`save`."""
        import joblib

        payload = joblib.load(path)
        return cls(model=payload["model"], kind=payload["kind"])


def top_shap_features(
    predictor: HelpNeedPredictor,
    x: np.ndarray,
    *,
    top_n: int = 8,
) -> list[tuple[str, float]]:
    """Mean |SHAP| per feature, ranked — the writeup's "why did it fire?" answer.

    SHAP is an analysis-only dev dependency (TECH_STACK §5), imported here on demand
    so it never loads on the inference path. Tree-explainer only, so XGBoost only.
    """
    if predictor.kind != "xgboost":
        raise ValueError(f"SHAP attribution requires the xgboost model, got {predictor.kind!r}")
    import shap

    explainer = shap.TreeExplainer(predictor.model)
    shap_values = np.asarray(explainer.shap_values(x))
    mean_abs = np.abs(shap_values).mean(axis=0)
    ranked = sorted(zip(FEATURE_NAMES, mean_abs, strict=True), key=lambda kv: kv[1], reverse=True)
    return [(name, float(value)) for name, value in ranked[:top_n]]


__all__ = [
    "HelpNeedPredictor",
    "ModelKind",
    "examples_to_matrix",
    "top_shap_features",
]
