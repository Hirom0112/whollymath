"""HelpNeed persona calibration (Slice 4.3).

Before the HelpNeed predictor (Slices 3.3–3.5) is allowed to drive ANY intervention
in the live tutor, we check it behaves sanely on OUR tutor — not just on the EDM Cup
holdout it was trained on. The risk is the documented train/serve gap (PROJECT.md
§7.2, RESEARCH.md §7.4): the model trained on the ASSISTments clickstream, but live
it consumes the Slice-4.4 adapter's feature vector, which carries two proxied
columns (``recent_attempts_mean`` ≡ 1, ``recent_request_answer_rate`` ≡ the hint
rate). This eval drives the five personas through the reactive tutor, rebuilds each
turn's LIVE feature vector with ``live_features`` (the exact path the live loop will
use), scores it with the predictor, and reports the probabilities — **observe-only**.

Observe-only is the whole point and is structurally guaranteed here: this module
reads ``predict_proba`` and records it; it never calls a transition, a refuse-rule,
or an intervention (the intervention surface is Slice 4.5). So running it cannot
change a learner's experience — it only tells us whether wiring the predictor would
be sane.

The sanity stat is **separation**: the mean predicted P(unproductive) on the turns
the persona got WRONG minus the mean on the turns they got RIGHT. A sane predictor
scores struggle higher than fluency, so separation should be clearly positive in
aggregate. The per-persona breakdown is the interesting part — e.g. Procedure Priya
answers correctly throughout (she is procedurally fluent), so HelpNeed should rate
her LOW; she is the false-positive the *transfer probe* catches (§8), not a HelpNeed
target. That HelpNeed and the mastery defense catch different failure modes is the
finding, not a bug.

This is an EVALUATION run, not a unit test (CLAUDE.md §9): the real numbers come from
``main()`` over the local EDM Cup data. The mechanics are pinned in
``tests/eval/test_helpneed_calibration.py`` with a tiny synthetic model. Reuses the
already-built pieces (``harness_cases`` sequences, ``run_persona``, ``live_features``,
``HelpNeedPredictor``) — no re-implementation, no LLM/DB/SymPy (CLAUDE.md §7).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.domain.knowledge_components import KnowledgeComponentId
from app.eval.false_positive_harness import PersonaCase, harness_cases
from app.helpneed.live_features import LiveTurn, live_features
from app.helpneed.predictor import HelpNeedPredictor
from app.personas.run import PersonaRun, run_persona


@dataclass(frozen=True)
class TurnPrediction:
    """The predictor's observe-only readout for one turn of a persona run."""

    turn_index: int
    kc: KnowledgeComponentId
    correct: bool
    hinted: bool
    latency_ms: int
    p_unproductive: float


@dataclass(frozen=True)
class PersonaCalibration:
    """One persona's calibration: every turn's prediction + the separation stat."""

    persona_id: str
    persona_name: str
    attacked_dimension: str
    predictions: tuple[TurnPrediction, ...]
    mean_p_correct: float
    mean_p_wrong: float

    @property
    def separation(self) -> float:
        """Mean P(unproductive) on WRONG turns minus on CORRECT turns (want > 0)."""
        return self.mean_p_wrong - self.mean_p_correct


@dataclass(frozen=True)
class CalibrationReport:
    """The five persona calibrations plus the aggregate separation."""

    per_persona: tuple[PersonaCalibration, ...]
    overall_mean_p_correct: float
    overall_mean_p_wrong: float

    @property
    def overall_separation(self) -> float:
        return self.overall_mean_p_wrong - self.overall_mean_p_correct


def _mean(values: list[float]) -> float:
    """Arithmetic mean, or 0.0 for an empty list (no turns of that kind)."""
    return sum(values) / len(values) if values else 0.0


def predict_run(
    predictor: HelpNeedPredictor, run: PersonaRun, *, persona_name: str
) -> PersonaCalibration:
    """Score every answered turn of one persona run over the LIVE feature path.

    Walks the run in order, maintaining the live history of COMPLETED turns. For each
    turn that produced a mastery observation (pure-EXPLAIN probes submit no answer and
    are skipped), it builds the feature vector for that in-progress problem from the
    history SO FAR (leakage-safe by construction — the current turn is not yet in the
    history) and records the predicted P(unproductive). Then it appends the turn's own
    live signals to the history for the next turn. Nothing is acted on.
    """
    history: list[LiveTurn] = []
    predictions: list[TurnPrediction] = []
    for turn in run.turns:
        obs = turn.observation
        if obs is None:  # a pure-EXPLAIN justification probe — no answer, no observation
            continue
        features = live_features(history, current_kc=turn.problem.kc)
        predictions.append(
            TurnPrediction(
                turn_index=len(predictions),
                kc=turn.problem.kc,
                correct=obs.correct,
                hinted=obs.hinted,
                latency_ms=obs.latency_ms,
                p_unproductive=predictor.predict_proba(features),
            )
        )
        history.append(LiveTurn(correct=obs.correct, hinted=obs.hinted, latency_ms=obs.latency_ms))

    return PersonaCalibration(
        persona_id=run.persona_id,
        persona_name=persona_name,
        attacked_dimension="",  # filled by calibrate(), which knows the case
        predictions=tuple(predictions),
        mean_p_correct=_mean([p.p_unproductive for p in predictions if p.correct]),
        mean_p_wrong=_mean([p.p_unproductive for p in predictions if not p.correct]),
    )


def calibrate(predictor: HelpNeedPredictor, cases: list[PersonaCase]) -> CalibrationReport:
    """Run every persona case observe-only and assemble the calibration report."""
    per_persona: list[PersonaCalibration] = []
    for case in cases:
        run = run_persona(case.persona, case.sequence)
        cal = predict_run(predictor, run, persona_name=case.persona.name)
        per_persona.append(
            PersonaCalibration(
                persona_id=cal.persona_id,
                persona_name=cal.persona_name,
                attacked_dimension=case.attacked_dimension,
                predictions=cal.predictions,
                mean_p_correct=cal.mean_p_correct,
                mean_p_wrong=cal.mean_p_wrong,
            )
        )

    all_correct = [p.p_unproductive for pc in per_persona for p in pc.predictions if p.correct]
    all_wrong = [p.p_unproductive for pc in per_persona for p in pc.predictions if not p.correct]
    return CalibrationReport(
        per_persona=tuple(per_persona),
        overall_mean_p_correct=_mean(all_correct),
        overall_mean_p_wrong=_mean(all_wrong),
    )


def format_report(report: CalibrationReport) -> str:
    """A readable table of the calibration outcome for the decision log / writeup."""
    lines = ["HelpNeed persona calibration (Slice 4.3) — observe-only:", ""]
    for pc in report.per_persona:
        lines.append(f"  {pc.persona_name}  (attacks: {pc.attacked_dimension})")
        for p in pc.predictions:
            mark = "ok " if p.correct else "ERR"
            hint = " +hint" if p.hinted else ""
            lines.append(
                f"    turn {p.turn_index} [{mark}] {p.kc.value:<28} "
                f"P(unproductive)={p.p_unproductive:.3f}{hint}"
            )
        lines.append(
            f"    mean P: correct={pc.mean_p_correct:.3f}  wrong={pc.mean_p_wrong:.3f}  "
            f"separation={pc.separation:+.3f}"
        )
        lines.append("")
    lines.append(
        f"OVERALL  mean P(unproductive): correct={report.overall_mean_p_correct:.3f}  "
        f"wrong={report.overall_mean_p_wrong:.3f}  separation={report.overall_separation:+.3f}"
    )
    sane = report.overall_separation > 0.0
    lines.append(
        f"Calibration {'SANE ✓' if sane else 'SUSPECT ✗'}: "
        "the predictor rates wrong turns "
        f"{'higher' if sane else 'NOT higher'} than correct turns."
    )
    return "\n".join(lines)


def main() -> None:
    """Train v1 on the local EDM Cup data, then calibrate against the personas.

    Run from ``backend/``: ``uv run python -m app.eval.helpneed_calibration``.
    Honors ``WHOLLYMATH_EDMCUP_DIR`` / ``WHOLLYMATH_EDMCUP_ROW_LIMIT`` like the
    training pipeline. Prints the table recorded in RESEARCH.md §7.5.
    """
    from app.helpneed.train_pipeline import load_examples_from_edmcup, train_and_evaluate

    data_dir = Path(os.environ.get("WHOLLYMATH_EDMCUP_DIR", "data/edmcup2023"))
    raw_limit = os.environ.get("WHOLLYMATH_EDMCUP_ROW_LIMIT", "")
    row_limit = int(raw_limit) if raw_limit else None

    print(f"Training HelpNeed v1 on {data_dir} (row_limit={row_limit}) …")
    examples = load_examples_from_edmcup(data_dir, row_limit=row_limit)
    if not examples:
        print("No examples parsed — check the data directory.")
        return
    predictor, report = train_and_evaluate(examples, kind="xgboost")
    print(f"  trained on {report.n_examples:,} examples (holdout AUC={report.holdout_auc:.3f})\n")

    print(format_report(calibrate(predictor, harness_cases())))


if __name__ == "__main__":
    main()


__all__ = [
    "CalibrationReport",
    "PersonaCalibration",
    "TurnPrediction",
    "calibrate",
    "format_report",
    "predict_run",
]
