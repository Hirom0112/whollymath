"""A lesson must END — the bounded-lesson terminal state (CP.B; PROJECT.md §3.13).

The reported bug: the live loop never finishes. ``_serve_next`` always returns another
problem, so a learner who answers everything correctly and CONFIRMS mastery (passes the S5
transfer probe) is just handed "Next problem" forever — there is no completion signal and no
return-home. These tests pin the fix: once the goal KC is confirmed, the turn carries
``lesson_complete = True`` (the wire signal the surface uses to show the "you finished it"
screen). They reuse the all-correct driver from the transfer-probe live tests; SymPy decides
every answer, no LLM, no mocks.
"""

from __future__ import annotations

from typing import Any

from app.api.app import create_app

from tests.api.test_transfer_probe_live import _correct_answer, _turn

_ADDITION_ROUTE = "combine"


def _drive_all_correct(app: Any, *, max_turns: int = 60) -> list[dict[str, Any]]:
    """Start the addition route and answer every problem (practice AND probe) correctly,
    returning every turn body in order. Stops early once a lesson-complete turn is seen."""
    from tests.api.asgi_client import post_json

    _, started = post_json(app, "/session", {"route_key": _ADDITION_ROUTE})
    session_id, problem = started["session_id"], started["problem"]
    bodies: list[dict[str, Any]] = []
    for _ in range(max_turns):
        body = _turn(app, session_id, problem, _correct_answer(problem))
        bodies.append(body)
        if body.get("lesson_complete"):
            return bodies
        problem = body["next_problem"]
        if problem is None:
            return bodies
    return bodies


def test_all_correct_run_reaches_lesson_complete() -> None:
    """Answering everything correctly must FINISH the lesson within a bounded number of turns
    — the loop cannot run forever (the reported bug)."""
    app = create_app()
    bodies = _drive_all_correct(app)
    assert any(b.get("lesson_complete") for b in bodies), (
        "an all-correct run never reached lesson_complete — the lesson loops forever"
    )


def test_lesson_complete_coincides_with_confirmed_mastery() -> None:
    """The lesson completes exactly when the goal KC is CONFIRMED (mastered=True), never on a
    bare-provisional turn — completion is earned by passing the transfer probe."""
    app = create_app()
    bodies = _drive_all_correct(app)
    complete = next((b for b in bodies if b.get("lesson_complete")), None)
    assert complete is not None, "lesson never completed"
    assert any(m["kc_id"] == "KC_addition_unlike" and m["mastered"] for m in complete["mastery"]), (
        "lesson_complete fired without the goal KC being confirmed-mastered"
    )
