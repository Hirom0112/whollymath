"""Tests for the turn-loop service boundary — the SessionStore seam (Slices 1.9, 2.6).

The route is thin (CLAUDE.md §7): it resolves a per-app ``SessionStore`` and
delegates. These tests pin the seam's behavior directly (no HTTP), so the contract
the route depends on is guarded in one place:

  - ``start`` creates a session and returns its Turn-1 calibration problem.
  - ``process_turn`` verifies a real answer, advances to a fresh next problem, and
    keeps the journey deterministic.
  - an unknown session id raises the named ``SessionNotFoundError`` (→ 404 at the route).
  - a hint request returns a nudge without advancing or changing state.

The domain/mastery/policy internals are NOT re-tested here — they have their own
suites; this guards the orchestration seam.
"""

from __future__ import annotations

import pytest
from app.api.schemas import (
    ActionType,
    ErrorType,
    StartSessionResponse,
    SurfaceState,
    TurnRequest,
)
from app.api.service import SessionNotFoundError, SessionStore, UnknownRouteError
from app.domain.knowledge_components import KnowledgeComponentId, Representation

_ADDITION_ROUTE_KEY = "combine"
_ADDITION_CORRECT_ANSWER = "7/12"


def _turn(session_id: str, problem_id: str, answer: str = _ADDITION_CORRECT_ANSWER) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.SUBMIT_ANSWER,
        submitted_answer=answer,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=3000,
        hint_used=False,
    )


def test_start_creates_a_session_with_a_calibration_problem() -> None:
    """start() returns an opaque id, the S1 starting state, and a Turn-1 problem."""
    store = SessionStore()
    started = store.start(_ADDITION_ROUTE_KEY)
    assert started.session_id
    assert started.surface_state is SurfaceState.SYMBOLIC_FOCUS
    assert started.problem.problem_id


def test_start_rejects_unknown_route_key() -> None:
    """An unknown route key fails loudly rather than inventing a route (§8.5)."""
    store = SessionStore()
    with pytest.raises(UnknownRouteError):
        store.start("teleport")


def test_process_turn_verifies_and_advances() -> None:
    """A correct answer is verified by the domain and a fresh next problem is served."""
    store = SessionStore()
    started = store.start(_ADDITION_ROUTE_KEY)
    response = store.process_turn(_turn(started.session_id, started.problem.problem_id))
    assert response.correct is True
    assert response.error_type is ErrorType.NONE
    assert response.next_problem is not None
    assert response.next_problem.problem_id != started.problem.problem_id


def _walk_first_n_followon_problems(
    store: SessionStore, started: StartSessionResponse, n: int
) -> list[str]:
    """Walk a started session forward ``n`` answer turns, collecting each served
    next-problem id. Always submits a wrong answer so the served-problem variety check
    is not confounded by a probe/state transition; the ids are what we compare."""
    ids: list[str] = []
    problem_id = started.problem.problem_id
    for _ in range(n):
        resp = store.process_turn(_turn(started.session_id, problem_id, answer="0"))
        assert resp.next_problem is not None
        problem_id = resp.next_problem.problem_id
        ids.append(problem_id)
    return ids


def test_two_sessions_get_different_problem_sequences() -> None:
    """Fix A — problem VARIETY: two fresh sessions on the SAME route get DIFFERENT problem
    sequences (the seed is derived from the session id, not just the turn index), so a learner
    no longer sees the identical problems every time. This is the corrected contract; it
    deliberately supersedes the old "two sessions yield the same problem" assertion, which
    encoded the reported bug.
    """
    store = SessionStore()
    a = store.start(_ADDITION_ROUTE_KEY)
    b = store.start(_ADDITION_ROUTE_KEY)

    seq_a = _walk_first_n_followon_problems(store, a, 4)
    seq_b = _walk_first_n_followon_problems(store, b, 4)
    assert seq_a != seq_b  # different sessions → different problems


def test_same_session_is_reproducible_problem_for_problem() -> None:
    """Fix A — within ONE session the walk stays fully deterministic: replaying the same
    session id with the same answers yields the identical problem sequence (PROJECT.md §4.1).
    Two independent stores are seeded with the SAME session id to prove reproducibility comes
    from the session id, not store identity.
    """
    fixed_id = "fixedsession00000000000000000001"
    store_a, store_b = SessionStore(), SessionStore()
    a = store_a.start(_ADDITION_ROUTE_KEY, session_id=fixed_id)
    b = store_b.start(_ADDITION_ROUTE_KEY, session_id=fixed_id)

    seq_a = _walk_first_n_followon_problems(store_a, a, 4)
    seq_b = _walk_first_n_followon_problems(store_b, b, 4)
    assert seq_a == seq_b  # same session id → identical, reproducible walk


def test_wrong_answer_re_practices_the_same_kc() -> None:
    """Fix B — adaptive re-practice: after a WRONG answer the next problem stays on the SAME
    KC the learner just struggled on (more practice on the shaky skill), instead of rotating
    to a different KC. The addition route's first follow-on is KC_addition_unlike; missing it
    must serve another KC_addition_unlike item, not the interleaved companion.
    """
    store = SessionStore()
    started = store.start(_ADDITION_ROUTE_KEY)
    problem_id = started.problem.problem_id
    # Keep answering WRONG for several turns — including past the §0.D.5 cadence turn (the 3rd
    # follow-on), which the PLAIN scheduler would hand to the subtraction companion. Under
    # re-practice every served problem must stay on the struggling KC (addition).
    for _ in range(5):
        resp = store.process_turn(_turn(started.session_id, problem_id, answer="0"))
        assert resp.correct is False
        assert resp.next_problem is not None
        assert resp.next_problem.kc is KnowledgeComponentId.ADDITION_UNLIKE
        problem_id = resp.next_problem.problem_id


def test_correct_answer_is_not_pinned_by_re_practice() -> None:
    """Fix B does not break interleaving: a CORRECT answer routes the next problem through the
    UNCHANGED interleaving path (``next_spec_after_outcome`` with ``last_correct=True`` ==
    ``next_spec``), so the cadence/representation rotation the mastery model relies on (§3.4
    rule 4) is preserved. Re-practice pins ONLY on a wrong answer (the other tests cover that).
    """
    from app.policy.scheduler import next_spec, next_spec_after_outcome

    # The wiring contract: a correct last turn must defer to the plain interleaving schedule.
    for i in range(12):
        assert next_spec_after_outcome(
            KnowledgeComponentId.ADDITION_UNLIKE,
            i,
            last_correct=True,
            last_kc=KnowledgeComponentId.ADDITION_UNLIKE,
            last_format=Representation.SYMBOLIC,
        ) == next_spec(KnowledgeComponentId.ADDITION_UNLIKE, i)

    # And end-to-end: a correct calibration answer serves a fresh, different problem (it does
    # not crash or stall), confirming the correct-path wiring runs.
    store = SessionStore()
    started = store.start(_ADDITION_ROUTE_KEY)
    resp = store.process_turn(
        _turn(started.session_id, started.problem.problem_id, answer=_ADDITION_CORRECT_ANSWER)
    )
    assert resp.correct is True
    assert resp.next_problem is not None
    assert resp.next_problem.problem_id != started.problem.problem_id


def test_unknown_session_raises_named_error() -> None:
    """A turn on an id the store never issued raises the named not-found marker."""
    store = SessionStore()
    with pytest.raises(SessionNotFoundError):
        store.process_turn(_turn("never-started", "prob-x"))


def test_hint_request_returns_nudge_without_advancing() -> None:
    """A hint request returns a nudge, keeps the state, and stays on the same problem."""
    store = SessionStore()
    started = store.start(_ADDITION_ROUTE_KEY)
    request = _turn(started.session_id, started.problem.problem_id)
    request = request.model_copy(
        update={"action": ActionType.REQUEST_HINT, "submitted_answer": None}
    )
    response = store.process_turn(request)
    assert response.hint
    assert response.next_surface_state is started.surface_state
    assert response.next_problem is not None
    assert response.next_problem.problem_id == started.problem.problem_id
