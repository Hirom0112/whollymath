"""Tests for the HelpNeed predictor (Slice 3.5).

Mandatory-TDD (CLAUDE.md §2, §9): we test inference LATENCY (the turn loop has a
sub-100ms budget — §8.1) and BEHAVIOR on known-edge-case inputs, not the exact
probabilities of a non-deterministic-ish learner (we DO seed for reproducibility).
The model trains on a small, strongly-separable synthetic dataset so the tests are
fast and the expected behavior is unambiguous.
"""

from __future__ import annotations

import time
from dataclasses import replace

import numpy as np
from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.features import FEATURE_NAMES, HelpNeedFeatures, TrainingExample
from app.helpneed.predictor import HelpNeedPredictor

_KC = KnowledgeComponentId.ADDITION_UNLIKE


def _features(*, error_rate: float, unproductive_rate: float, attempts: float) -> HelpNeedFeatures:
    return HelpNeedFeatures(
        recent_latency_ms_mean=2000.0 + 4000.0 * error_rate,
        recent_attempts_mean=attempts,
        recent_hint_rate=2.0 * error_rate,
        recent_error_rate=error_rate,
        recent_request_answer_rate=error_rate,
        turns_since_last_correct=1.0 + 4.0 * error_rate,
        prior_unproductive_rate=unproductive_rate,
        session_position=5.0,
        kc=_KC,
    )


_STRUGGLING = _features(error_rate=0.9, unproductive_rate=0.85, attempts=4.0)
_CLEAN = _features(error_rate=0.05, unproductive_rate=0.05, attempts=1.0)


def _dataset(n_per_class: int = 120) -> list[TrainingExample]:
    """A separable synthetic set: high-struggle history → unproductive, clean → not.

    Small per-row variation (via the index) keeps the columns non-degenerate while
    the two clusters stay clearly separable, so the trained model's behavior on the
    canonical struggling/clean inputs is unambiguous.
    """
    examples: list[TrainingExample] = []
    for i in range(n_per_class):
        jitter = (i % 10) / 100.0
        examples.append(
            TrainingExample(
                features=_features(
                    error_rate=0.8 + jitter, unproductive_rate=0.8 + jitter, attempts=3.0 + jitter
                ),
                label=True,
                assignment_log_id=f"s{i}",
                problem_id="p",
            )
        )
        examples.append(
            TrainingExample(
                features=_features(
                    error_rate=0.0 + jitter, unproductive_rate=0.0 + jitter, attempts=1.0 + jitter
                ),
                label=False,
                assignment_log_id=f"c{i}",
                problem_id="p",
            )
        )
    return examples


def test_predict_proba_is_a_probability() -> None:
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    p = predictor.predict_proba(_STRUGGLING)
    assert 0.0 <= p <= 1.0


def test_struggling_history_scores_higher_than_clean() -> None:
    """The core behavior: more struggle in the recent window → higher HelpNeed."""
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    assert predictor.predict_proba(_STRUGGLING) > predictor.predict_proba(_CLEAN)
    assert predictor.predict_proba(_STRUGGLING) > 0.5
    assert predictor.predict_proba(_CLEAN) < 0.5


def test_inference_is_sub_100ms() -> None:
    """A single-turn inference must fit the turn-loop latency budget (§8.1)."""
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    predictor.predict_proba(_STRUGGLING)  # warm any one-time prediction setup
    start = time.perf_counter()
    predictor.predict_proba(_STRUGGLING)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert elapsed_ms < 100.0, f"inference took {elapsed_ms:.1f}ms (budget 100ms)"


def test_logistic_baseline_trains_and_predicts() -> None:
    """The interpretable baseline (TECH_STACK §5) also fits and ranks the two inputs."""
    predictor = HelpNeedPredictor.fit(_dataset(), kind="logistic", random_state=0)
    assert 0.0 <= predictor.predict_proba(_CLEAN) <= 1.0
    assert predictor.predict_proba(_STRUGGLING) > predictor.predict_proba(_CLEAN)


def test_save_load_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A persisted predictor reloads and gives identical predictions (joblib)."""
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    path = tmp_path / "helpneed.joblib"
    predictor.save(path)
    reloaded = HelpNeedPredictor.load(path)
    assert reloaded.predict_proba(_STRUGGLING) == predictor.predict_proba(_STRUGGLING)
    assert reloaded.kind == "xgboost"


# ─── Width-guard (T1↔T2 coordination): degrade-safe on artifact↔one-hot width drift ───
# When the KC enum widens (KC_ORDER grows the one-hot) before the model is re-fit, the
# live to_vector() is wider than the committed artifact expects. The predictor must NOT
# crash the turn loop on that mismatch — it returns a neutral observe-only score (never
# trips the §3.7 gate) until a re-fit artifact at the new width lands. See
# T1_T2_COORDINATION.md §2.


class _ExplodingModel:
    """A stand-in estimator that fails if ``predict_proba`` is ever called.

    Proves the width-guard SHORT-CIRCUITS before touching the model — a real width-13
    model would raise a feature-count error on a wider vector; this makes "the guard
    fired" unambiguous instead of relying on which exception sklearn happens to throw.
    """

    n_features_in_ = 99  # deliberately != the live FEATURE_NAMES width

    def fit(self, x: np.ndarray, y: np.ndarray) -> _ExplodingModel:
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        raise AssertionError("guard must short-circuit; predict_proba must not be called")


def test_predict_proba_neutral_on_feature_name_mismatch() -> None:
    """feature_names that don't match the live FEATURE_NAMES → neutral, model untouched."""
    predictor = HelpNeedPredictor(
        model=_ExplodingModel(), kind="xgboost", feature_names=("only", "two")
    )
    assert predictor.predict_proba(_STRUGGLING) == 0.0  # neutral; the gate can never trip on it


def test_predict_proba_neutral_on_width_mismatch_via_n_features() -> None:
    """No stamped feature_names → fall back to the model's n_features_in_; mismatch → neutral."""
    predictor = HelpNeedPredictor(model=_ExplodingModel(), kind="xgboost")  # n_features_in_ == 99
    assert predictor.predict_proba(_STRUGGLING) == 0.0


def test_fit_stamps_feature_names_and_save_load_preserves_them(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A freshly fit predictor carries the live FEATURE_NAMES, and they survive a round-trip."""
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    assert predictor.feature_names == FEATURE_NAMES
    path = tmp_path / "stamped.joblib"
    predictor.save(path)
    assert HelpNeedPredictor.load(path).feature_names == FEATURE_NAMES


def test_load_tolerates_legacy_artifact_without_feature_names(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """An old {model, kind} payload (no feature_names) still loads; width matches → scores."""
    import joblib

    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    path = tmp_path / "legacy.joblib"
    joblib.dump({"model": predictor.model, "kind": predictor.kind}, path)  # pre-stamp payload shape
    reloaded = HelpNeedPredictor.load(path)
    assert reloaded.feature_names is None
    # Same width as today → compatible → still produces a real score (degrades only when widened).
    assert 0.0 <= reloaded.predict_proba(_STRUGGLING) <= 1.0


# ─── Tier-2 trustworthy-KC stamp (T1_T2_COORDINATION §"Tier-2") ───────────────────────
# The set of KCs the proactive arm may fire on is a property of the VALIDATED model, so it
# is frozen at train time (computed on the holdout via per_kc_validation.trustworthy_kcs)
# and persisted WITH the artifact. The runtime reads it off the loaded predictor and hands
# it to the gate — never recomputed at boot (no holdout data there). A legacy artifact that
# predates the stamp carries None, which the gate treats as "no filter" (default-unchanged).


def test_fit_leaves_trustworthy_kcs_unset() -> None:
    """``fit`` alone doesn't know the holdout, so it stamps no trustworthy set (None).

    The set is computed by the training pipeline on the holdout AFTER the fit and attached
    there — ``fit`` itself stays a pure model fit, so a directly-fit predictor is unfiltered.
    """
    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    assert predictor.trustworthy_kcs is None


def test_save_load_preserves_trustworthy_kcs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A stamped trustworthy set survives a joblib round-trip."""
    base = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    stamped = replace(base, trustworthy_kcs=frozenset({"KC_multiply_fractions", "KC_unit_rate"}))
    path = tmp_path / "stamped_trust.joblib"
    stamped.save(path)
    reloaded = HelpNeedPredictor.load(path)
    assert reloaded.trustworthy_kcs == frozenset({"KC_multiply_fractions", "KC_unit_rate"})


def test_load_tolerates_artifact_without_trustworthy_kcs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The committed pre-stamp artifact (no trustworthy_kcs key) loads with None — no filter."""
    import joblib

    predictor = HelpNeedPredictor.fit(_dataset(), kind="xgboost", random_state=0)
    path = tmp_path / "pre_trust.joblib"
    joblib.dump(
        {"model": predictor.model, "kind": predictor.kind, "feature_names": list(FEATURE_NAMES)},
        path,
    )
    assert HelpNeedPredictor.load(path).trustworthy_kcs is None
