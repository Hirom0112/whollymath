"""Tests for the proactive intervention wiring (Slice 4.5.1).

The §3.7 sustained-signal gate is wired into the turn loop, but behind a per-session
proactive arm that defaults OFF. These tests pin the contract:

  - the **default arm is OFF** — no proactive intervention ever appears, even when the
    HelpNeed stream would trip the gate (the observe-only default, RESEARCH.md §7.5);
  - with the arm ON, the intervention fires **only after a sustained signal** (K
    consecutive high-P turns), never on a single high turn;
  - turning the arm on **does not alter any deterministic turn outcome** — same
    correctness, error class, surface state, next problem; only ``intervention`` differs
    (the §8.1 ordering: the score/gate run AFTER the settled turn);
  - the offered text comes from the **pre-written nudge bank** (no LLM, §8.1).

Fixture is the committed artifact (``load_predictor``), so wrong answers produce the high
P that exercises the gate, matching the live path.
"""

from __future__ import annotations

from app.api.schemas import ActionType, InterventionKind, SurfaceState, TurnRequest, TurnResponse
from app.api.service import SessionStore
from app.helpneed.artifact import load_predictor
from app.policy.intervention_gate import SustainedHelpNeedGate
from app.tutor.hints import select_nudge

from tests.api._artifact_skip import stale_artifact

_ADDITION_ROUTE_KEY = "combine"
_WRONG = "1/2"  # wrong for the addition calibration family — drives P high


def _answer(session_id: str, problem_id: str, answer: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.SUBMIT_ANSWER,
        submitted_answer=answer,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=3000,
        hint_used=False,
    )


def _walk_wrong(
    store: SessionStore, session_id: str, first_problem_id: str, turns: int
) -> list[TurnResponse]:
    """Submit `turns` wrong answers in a row; return the per-turn responses."""
    responses = []
    pid = first_problem_id
    for _ in range(turns):
        resp = store.process_turn(_answer(session_id, pid, _WRONG))
        responses.append(resp)
        assert resp.next_problem is not None
        pid = resp.next_problem.problem_id
    return responses


def test_default_arm_off_never_intervenes() -> None:
    """A session started without the proactive arm never gets an intervention."""
    store = SessionStore(predictor=load_predictor())
    started = store.start(_ADDITION_ROUTE_KEY)  # arm defaults OFF
    responses = _walk_wrong(store, started.session_id, started.problem.problem_id, turns=6)
    assert all(r.intervention is None for r in responses)


@stale_artifact
def test_proactive_arm_fires_only_after_sustained_signal() -> None:
    """With the arm ON, the gate fires after K consecutive high-P turns, not before."""
    store = SessionStore(predictor=load_predictor(), gate=SustainedHelpNeedGate(k=3, threshold=0.5))
    started = store.start(_ADDITION_ROUTE_KEY, proactive_enabled=True)
    responses = _walk_wrong(store, started.session_id, started.problem.problem_id, turns=4)
    # First turn cannot fire (fewer than K scored turns exist yet).
    assert responses[0].intervention is None
    # By the time a sustained run has built up, the intervention appears.
    fired = [r for r in responses if r.intervention is not None]
    assert fired, "expected the sustained gate to fire within 4 consecutive wrong turns"
    assert fired[0].intervention is not None
    assert fired[0].intervention.kind is InterventionKind.INLINE_ASSERTION


@stale_artifact
def test_intervention_text_comes_from_the_nudge_bank() -> None:
    """The offered text is the pre-written nudge for the upcoming KC (no LLM, §8.1)."""
    store = SessionStore(predictor=load_predictor(), gate=SustainedHelpNeedGate(k=2, threshold=0.5))
    started = store.start(_ADDITION_ROUTE_KEY, proactive_enabled=True)
    responses = _walk_wrong(store, started.session_id, started.problem.problem_id, turns=4)
    fired = next(r for r in responses if r.intervention is not None)
    assert fired.next_problem is not None
    assert fired.intervention is not None
    expected = select_nudge(fired.next_problem.kc).text
    assert fired.intervention.text == expected


@stale_artifact
def test_arm_does_not_alter_deterministic_turn_outcome() -> None:
    """Arm ON vs OFF: identical turn outcomes; only `intervention` differs (§8.1 order).

    Both stores have the SAME predictor, so `help_need` matches turn-for-turn too — the
    proactive arm reads the settled turn and can only add the intervention, never move
    correctness, the surface state, or the next problem.
    """
    on = SessionStore(predictor=load_predictor(), gate=SustainedHelpNeedGate(k=3, threshold=0.5))
    off = SessionStore(predictor=load_predictor(), gate=SustainedHelpNeedGate(k=3, threshold=0.5))
    # Pin the SAME session id in both walks: the problem seed is derived from the id (Fix A),
    # so an equivalence test must hold identity fixed to isolate the variable under test (the
    # arm), not the per-session problem variety.
    fixed_id = "equivsession0000000000000000proa"
    a = on.start(_ADDITION_ROUTE_KEY, proactive_enabled=True, session_id=fixed_id)
    b = off.start(_ADDITION_ROUTE_KEY, session_id=fixed_id)  # arm OFF
    assert a.problem.problem_id == b.problem.problem_id

    pid_a, pid_b = a.problem.problem_id, b.problem.problem_id
    saw_intervention = False
    for _ in range(6):
        resp_a = on.process_turn(_answer(a.session_id, pid_a, _WRONG))
        resp_b = off.process_turn(_answer(b.session_id, pid_b, _WRONG))
        assert resp_a.correct == resp_b.correct
        assert resp_a.error_type == resp_b.error_type
        assert resp_a.next_surface_state == resp_b.next_surface_state
        assert resp_a.help_need == resp_b.help_need
        assert resp_a.next_problem is not None and resp_b.next_problem is not None
        assert resp_a.next_problem.problem_id == resp_b.next_problem.problem_id
        assert resp_b.intervention is None  # OFF arm never intervenes
        saw_intervention = saw_intervention or resp_a.intervention is not None
        pid_a = resp_a.next_problem.problem_id
        pid_b = resp_b.next_problem.problem_id
    assert saw_intervention, "the ON arm should have fired at least once over 6 wrong turns"
