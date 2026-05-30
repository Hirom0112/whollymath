"""Tests for the observe-only HelpNeed wiring in the live turn loop (Slice 4.4.1/4.4.2).

The predictor is wired into ``SessionStore`` to score each answered turn, but the
locked 4.3 decision (RESEARCH.md §7.5) is **observe-only**: the score is reported and
NEVER acted on (interventions are Slice 4.5). These tests pin exactly that contract at
the service seam:

  - an answer turn returns a ``help_need`` probability in [0, 1] when a predictor is
    injected, and ``None`` when one is not (the ``create_app`` store always injects the
    committed artifact, so production always scores; a bare store does not);
  - a hint turn never scores (no answer was submitted);
  - **observe-only is proved by equivalence**: a session walked WITH a predictor and the
    same session walked WITHOUT one produce byte-identical turn outcomes (correctness,
    error class, next surface state, next problem) — only ``help_need`` differs. If the
    score ever fed a transition or the next-problem choice, this would diverge;
  - the live scoring path stays **sub-100ms per turn** (§8.1) with the real committed
    model (200 trees, depth 4) inline — Slice 4.4.2.

The fixture is the committed production artifact itself (``load_predictor``), so the
latency assertion measures the true inference cost, not a toy model.
"""

from __future__ import annotations

import time

from app.api.schemas import ActionType, SurfaceState, TurnRequest
from app.api.service import SessionStore
from app.helpneed.artifact import load_predictor

from tests.api._artifact_skip import stale_artifact

_ADDITION_ROUTE_KEY = "combine"
# Two answers we can replay deterministically: one correct, one wrong. Walking a mix of
# both exercises the predictor on both fluent and struggling histories.
_CORRECT = "7/12"
_WRONG = "1/2"


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


def test_answer_turn_scores_help_need_in_unit_interval() -> None:
    """With a predictor injected, an answer turn returns P(unproductive) in [0, 1]."""
    store = SessionStore(predictor=load_predictor())
    started = store.start(_ADDITION_ROUTE_KEY)
    response = store.process_turn(_answer(started.session_id, started.problem.problem_id, _CORRECT))
    assert response.help_need is not None
    assert 0.0 <= response.help_need <= 1.0


def test_no_predictor_means_no_score() -> None:
    """A bare store (no predictor) still runs the turn but reports help_need=None."""
    store = SessionStore()
    started = store.start(_ADDITION_ROUTE_KEY)
    response = store.process_turn(_answer(started.session_id, started.problem.problem_id, _CORRECT))
    assert response.help_need is None
    assert response.next_problem is not None  # the deterministic turn is unaffected


def test_hint_turn_is_never_scored() -> None:
    """A hint request submits no answer, so there is nothing to score (help_need=None)."""
    store = SessionStore(predictor=load_predictor())
    started = store.start(_ADDITION_ROUTE_KEY)
    hint = _answer(started.session_id, started.problem.problem_id, _CORRECT).model_copy(
        update={"action": ActionType.REQUEST_HINT, "submitted_answer": None}
    )
    response = store.process_turn(hint)
    assert response.help_need is None


@stale_artifact
def test_struggle_scores_higher_than_fluency() -> None:
    """The wired predictor rates a wrong-streak history above a correct one (sane sign).

    Not a calibration test (that is the §7.5 eval) — just a directional sanity check that
    the live feature path is plumbed correctly: repeated wrong answers should not score
    BELOW a correct opener.
    """
    store = SessionStore(predictor=load_predictor())
    started = store.start(_ADDITION_ROUTE_KEY)
    sid = started.session_id
    first = store.process_turn(_answer(sid, started.problem.problem_id, _CORRECT))
    assert first.next_problem is not None and first.help_need is not None
    last_help_need = first.help_need
    pid = first.next_problem.problem_id
    for _ in range(3):
        resp = store.process_turn(_answer(sid, pid, _WRONG))
        assert resp.next_problem is not None and resp.help_need is not None
        last_help_need = resp.help_need
        pid = resp.next_problem.problem_id
    assert last_help_need > first.help_need


def test_scoring_does_not_alter_turn_outcome() -> None:
    """Observe-only proof: the score never feeds the loop (CLAUDE.md §8.1, §7.5 decision).

    The SAME deterministic session is walked twice — once WITH the predictor, once
    WITHOUT — over an identical action sequence. Every deterministic output (correctness,
    error class, next surface state, next problem) must match turn-for-turn; only
    ``help_need`` may differ (present vs. None). If the predictor's score ever drove a
    transition or the next-problem choice, the two walks would diverge.
    """
    scored = SessionStore(predictor=load_predictor())
    bare = SessionStore()
    # Pin the SAME session id in both walks: the problem seed is derived from the id (Fix A),
    # so an equivalence test must hold identity fixed to isolate the variable under test (the
    # predictor), not the per-session problem variety.
    fixed_id = "equivsession00000000000000helpnd"
    a = scored.start(_ADDITION_ROUTE_KEY, session_id=fixed_id)
    b = bare.start(_ADDITION_ROUTE_KEY, session_id=fixed_id)
    assert a.problem.problem_id == b.problem.problem_id  # start() is deterministic

    answers = [_CORRECT, _WRONG, _WRONG, _CORRECT, _WRONG]
    pid_a, pid_b = a.problem.problem_id, b.problem.problem_id
    for answer in answers:
        resp_a = scored.process_turn(_answer(a.session_id, pid_a, answer))
        resp_b = bare.process_turn(_answer(b.session_id, pid_b, answer))
        assert resp_a.correct == resp_b.correct
        assert resp_a.error_type == resp_b.error_type
        assert resp_a.next_surface_state == resp_b.next_surface_state
        assert resp_a.next_problem is not None and resp_b.next_problem is not None
        assert resp_a.next_problem.problem_id == resp_b.next_problem.problem_id
        # The only intended difference: the scored walk carries an observe-only readout.
        assert resp_a.help_need is not None
        assert resp_b.help_need is None
        pid_a = resp_a.next_problem.problem_id
        pid_b = resp_b.next_problem.problem_id


def test_live_scoring_path_is_sub_100ms_per_turn() -> None:
    """Slice 4.4.2: the turn loop stays sub-100ms per turn with the real model inline.

    Measures the full ``process_turn`` (verify → mastery → policy → serve → observe-only
    score) with the committed XGBoost artifact loaded, over several turns, and asserts the
    slowest turn is comfortably under the 100ms budget (§8.1). The model load happens once
    at store construction (mirroring ``create_app``), not per turn.
    """
    store = SessionStore(predictor=load_predictor())
    started = store.start(_ADDITION_ROUTE_KEY)
    sid = started.session_id
    pid = started.problem.problem_id
    worst_ms = 0.0
    for i in range(8):
        answer = _CORRECT if i % 2 == 0 else _WRONG
        start = time.perf_counter()
        resp = store.process_turn(_answer(sid, pid, answer))
        worst_ms = max(worst_ms, (time.perf_counter() - start) * 1000.0)
        assert resp.help_need is not None and resp.next_problem is not None
        pid = resp.next_problem.problem_id
    assert worst_ms < 100.0, f"slowest turn {worst_ms:.1f}ms exceeded the 100ms budget"
