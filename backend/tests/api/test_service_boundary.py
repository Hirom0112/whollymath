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
from app.api.schemas import ActionType, ErrorType, SurfaceState, TurnRequest
from app.api.service import SessionNotFoundError, SessionStore, UnknownRouteError

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


def test_process_turn_is_deterministic() -> None:
    """Two fresh sessions walked identically yield the same next problem (§4.1).

    Only ``session_id`` is non-deterministic (a uuid); the served problem — chosen
    from the deterministic seed = turn count — must be identical across runs.
    """
    store_a, store_b = SessionStore(), SessionStore()
    a = store_a.start(_ADDITION_ROUTE_KEY)
    b = store_b.start(_ADDITION_ROUTE_KEY)
    assert a.problem.problem_id == b.problem.problem_id  # start() is deterministic too

    resp_a = store_a.process_turn(_turn(a.session_id, a.problem.problem_id))
    resp_b = store_b.process_turn(_turn(b.session_id, b.problem.problem_id))
    assert resp_a.next_problem is not None and resp_b.next_problem is not None
    assert resp_a.next_problem.problem_id == resp_b.next_problem.problem_id
    assert resp_a.next_problem.statement == resp_b.next_problem.statement


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
