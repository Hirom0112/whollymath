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

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from app.helpneed.features import FEATURE_NAMES, HelpNeedFeatures, TrainingExample

_LOGGER = logging.getLogger(__name__)

# The model kinds this wrapper supports. "xgboost" is the production model; "logistic"
# is the interpretable baseline for the writeup comparison (TECH_STACK §5).
ModelKind = str

# The observe-only fallback score returned when the loaded artifact's input width no
# longer matches the live one-hot (the KC enum widened ahead of a re-fit — see
# T1_T2_COORDINATION.md §2). 0.0 = "no help needed", so it can NEVER trip the §3.7
# intervention gate (P ≥ threshold): scoring degrades to silent, never to a crash or a
# spurious intervention, until a re-fit artifact at the new width lands.
_NEUTRAL_PROBA = 0.0


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
    # The feature columns the model was TRAINED on, in order (== FEATURE_NAMES at fit time).
    # Stamped by ``fit`` and persisted by ``save`` so the width-guard can detect when the live
    # one-hot has drifted from the artifact (the KC enum widened ahead of a re-fit). ``None`` for a
    # legacy artifact saved before stamping — the guard then falls back to ``model.n_features_in_``.
    feature_names: tuple[str, ...] | None = None
    # Log the width-mismatch warning at most once per predictor (the turn loop calls predict_proba
    # every turn; we don't want a log line per turn). Not part of the saved state.
    _width_mismatch_logged: bool = field(default=False, init=False, repr=False)

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
        return cls(model=model, kind=kind, feature_names=FEATURE_NAMES)

    def _is_width_compatible(self, live_len: int) -> bool:
        """Whether this model can score the current live feature vector.

        Prefers an exact ``feature_names`` match (catches a re-ORDERING of columns, not just a
        width change); falls back to the model's ``n_features_in_`` count for a legacy artifact
        that carries no names. If neither is available we proceed best-effort (real estimators
        always expose ``n_features_in_`` after fit, so this only spares a hand-built fake).
        """
        if self.feature_names is not None:
            return tuple(self.feature_names) == FEATURE_NAMES
        expected = getattr(self.model, "n_features_in_", None)
        return expected is None or int(expected) == live_len

    def predict_proba(self, features: HelpNeedFeatures) -> float:
        """P(unproductive) for one turn — the single-row, sub-100ms inference path.

        Width-guarded: if the artifact was trained on a different feature width than the live
        one-hot (KC enum widened ahead of a re-fit), return a neutral observe-only score instead
        of feeding a mismatched vector into the model and crashing the turn loop (§2 of the T1↔T2
        coordination note). The guard self-heals: a re-fit artifact at the new width compares
        equal again and full scoring resumes with no code change.
        """
        vector = features.to_vector()
        if not self._is_width_compatible(len(vector)):
            self._log_width_mismatch_once(len(vector))
            return _NEUTRAL_PROBA
        x = np.asarray([vector], dtype=float)
        return float(self.model.predict_proba(x)[0, 1])

    def _log_width_mismatch_once(self, live_len: int) -> None:
        """Warn (once) that the model is stale-width and scoring is degraded to observe-only."""
        if self._width_mismatch_logged:
            return
        trained = (
            len(self.feature_names)
            if self.feature_names is not None
            else getattr(self.model, "n_features_in_", "unknown")
        )
        _LOGGER.warning(
            "HelpNeed predictor feature-width mismatch (trained on %s, live FEATURE_NAMES has %s); "
            "returning a neutral observe-only score (the intervention gate cannot fire) until a "
            "re-fit artifact at the new width lands.",
            trained,
            live_len,
        )
        self._width_mismatch_logged = True

    def predict_proba_matrix(self, x: np.ndarray) -> np.ndarray:
        """P(unproductive) for a batch (column 1 of predict_proba) — for evaluation."""
        return np.asarray(self.model.predict_proba(x)[:, 1], dtype=float)

    def save(self, path: Path) -> None:
        """Persist the fitted model + kind + the trained feature names via joblib (TECH_STACK §5).

        ``feature_names`` is stamped so the width-guard can compare the artifact against the live
        one-hot on reload (the T1↔T2 artifact-metadata contract). A re-fit at a wider width stamps
        the wider names automatically through ``fit``.
        """
        import joblib

        names = list(self.feature_names) if self.feature_names is not None else None
        joblib.dump({"model": self.model, "kind": self.kind, "feature_names": names}, path)

    @classmethod
    def load(cls, path: Path) -> HelpNeedPredictor:
        """Reload a predictor saved by :meth:`save`.

        Tolerant of a legacy payload that predates the ``feature_names`` stamp (``.get`` → ``None``)
        so the committed width-13 artifact still loads; the width-guard then falls back to the
        model's own ``n_features_in_``.
        """
        import joblib

        payload = joblib.load(path)
        stamped = payload.get("feature_names")
        return cls(
            model=payload["model"],
            kind=payload["kind"],
            feature_names=tuple(stamped) if stamped is not None else None,
        )


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
