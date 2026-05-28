"""Tests for the HelpNeed persona-calibration eval (Slice 4.3).

The eval drives the 5 personas through the reactive tutor and runs the HelpNeed
predictor OVER THE LIVE FEATURE PATH (the Slice-4.4 adapter), observe-only, to check
the predictor behaves sanely on our tutor before it is ever allowed to drive an
intervention (handoff §5; PROJECT.md §7.2 cross-tutor gap).

These tests pin the eval MECHANICS with a tiny synthetic model (no 1.44 GB EDM Cup
dependency — that data feeds ``main()``, which produces the numbers in RESEARCH.md
§7.5). They assert: one prediction per observed turn, probabilities in range,
determinism, the live path is sub-100ms per turn (the §8 latency budget), and that
all five persona cases are covered.
"""

from __future__ import annotations

import time

from app.domain.knowledge_components import KnowledgeComponentId
from app.eval.false_positive_harness import harness_cases
from app.eval.helpneed_calibration import calibrate, predict_run
from app.helpneed.features import HelpNeedFeatures, TrainingExample
from app.helpneed.predictor import HelpNeedPredictor
from app.personas.run import run_persona

KC = KnowledgeComponentId.ADDITION_UNLIKE


def _example(error_rate: float, *, label: bool, idx: int) -> TrainingExample:
    """A synthetic training row whose label correlates with the error rate."""
    feats = HelpNeedFeatures(
        recent_latency_ms_mean=5000.0,
        recent_attempts_mean=1.0,
        recent_hint_rate=error_rate,
        recent_error_rate=error_rate,
        recent_request_answer_rate=error_rate,
        turns_since_last_correct=1.0 + 4.0 * error_rate,
        prior_unproductive_rate=error_rate,
        session_position=3.0,
        kc=KC,
    )
    return TrainingExample(features=feats, label=label, assignment_log_id="s", problem_id=f"p{idx}")


def _synthetic_predictor() -> HelpNeedPredictor:
    """A small logistic model fit on separable synthetic rows (no external data)."""
    examples = [_example(0.1, label=False, idx=i) for i in range(15)] + [
        _example(0.9, label=True, idx=15 + i) for i in range(15)
    ]
    return HelpNeedPredictor.fit(examples, kind="logistic", random_state=0)


def test_predict_run_yields_one_prediction_per_observed_turn() -> None:
    predictor = _synthetic_predictor()
    case = harness_cases()[0]  # Surface Sam
    run = run_persona(case.persona, case.sequence)
    cal = predict_run(predictor, run, persona_name=case.persona.name)

    observed = [t for t in run.turns if t.observation is not None]
    assert len(cal.predictions) == len(observed)
    assert all(0.0 <= p.p_unproductive <= 1.0 for p in cal.predictions)
    # turn indices are the per-observed-turn order, contiguous from 0
    assert [p.turn_index for p in cal.predictions] == list(range(len(observed)))


def test_predictions_are_deterministic() -> None:
    predictor = _synthetic_predictor()
    case = harness_cases()[0]
    run = run_persona(case.persona, case.sequence)
    first = predict_run(predictor, run, persona_name=case.persona.name)
    second = predict_run(predictor, run, persona_name=case.persona.name)
    assert [p.p_unproductive for p in first.predictions] == [
        p.p_unproductive for p in second.predictions
    ]


def test_live_inference_path_is_sub_100ms_per_turn() -> None:
    """The §8 latency budget covers the LIVE path: adapter + predict, per turn."""
    predictor = _synthetic_predictor()
    case = harness_cases()[0]
    run = run_persona(case.persona, case.sequence)

    start = time.perf_counter()
    cal = predict_run(predictor, run, persona_name=case.persona.name)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    per_turn_ms = elapsed_ms / max(len(cal.predictions), 1)
    assert per_turn_ms < 100.0


def test_calibrate_covers_all_five_personas() -> None:
    predictor = _synthetic_predictor()
    report = calibrate(predictor, harness_cases())
    assert len(report.per_persona) == 5
    # every persona produced at least one prediction
    assert all(len(pc.predictions) >= 1 for pc in report.per_persona)
    # the overall separation stat is finite (mean_p_wrong - mean_p_correct)
    assert isinstance(report.overall_separation, float)
