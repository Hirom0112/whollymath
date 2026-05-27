"""Tests for the turn-loop service boundary stub (Slice 1.9).

The route is thin (CLAUDE.md §7): it delegates to ``process_turn``. These tests
pin the boundary's *contract* so later slices can swap the real verify -> mastery
-> policy pipeline in behind the same signature without breaking callers:

  - ``process_turn`` takes a TurnRequest and returns a TurnResponse (the seam).
  - The stub makes no fabricated verdict (honest "nothing decided yet").
  - ``run_real_turn_loop`` still raises the named not-implemented marker, so no
    real pipeline is silently assumed to exist.

These are not business-behavior tests — there is no business behavior yet. They
guard the seam itself.
"""

from __future__ import annotations

import pytest
from app.api.schemas import (
    ActionType,
    ErrorType,
    SurfaceState,
    TurnRequest,
    TurnResponse,
)
from app.api.service import (
    TurnLoopNotImplementedError,
    process_turn,
    run_real_turn_loop,
)


def _request() -> TurnRequest:
    return TurnRequest(
        session_id="sess-1",
        problem_id="prob-1",
        action=ActionType.SUBMIT_ANSWER,
        submitted_answer="1/2",
        surface_state=SurfaceState.NUMBER_LINE_PRIMARY,
        latency_ms=3000,
        hint_used=False,
    )


def test_process_turn_returns_turn_response() -> None:
    """The seam's signature is TurnRequest -> TurnResponse (the stable contract)."""
    result = process_turn(_request())
    assert isinstance(result, TurnResponse)


def test_stub_does_not_fabricate_a_verdict() -> None:
    """The stub reports no real verdict: not correct, no error, empty mastery.

    This keeps the placeholder honest — it must not ship a fake "correct" that
    downstream could mistake for real evidence (ARCHITECTURE.md §2: rules decide
    what happened; nothing is decided yet here).
    """
    result = process_turn(_request())
    assert result.correct is False
    assert result.error_type is ErrorType.NONE
    assert result.mastery == []


def test_stub_does_not_invent_a_state_transition() -> None:
    """With no policy yet, next state echoes the current state (no invented move)."""
    request = _request()
    result = process_turn(request)
    assert result.next_surface_state == request.surface_state


def test_real_turn_loop_marker_still_raises() -> None:
    """The real pipeline is not wired yet and says so via the named marker."""
    with pytest.raises(TurnLoopNotImplementedError):
        run_real_turn_loop(_request())
