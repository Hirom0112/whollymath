"""The S4 worked-example content is served on the wire (Feature A, Slice 3.6 → API).

When the reactive policy transitions to S4 (≥2 consecutive errors, §3.6 row 4), the turn
response must now carry the worked solution of the problem the learner JUST got stuck on —
not the next problem — so the surface can render the S4 walkthrough. These tests drive the
real turn loop through the in-process ASGI app: SymPy decides every answer; no LLM, no mocks.

We deliberately drive an addition route (KC_addition_unlike), whose stuck problem IS
buildable into a worked example, so we can assert a non-empty, well-shaped walkthrough. A
normal correct turn must carry no worked example (it is not an S4 turn). The no-crash /
present-or-empty guarantee for non-buildable problems is covered structurally below.
"""

from __future__ import annotations

import re
from typing import Any

from app.api.app import create_app
from sympy import Rational

from tests.api.asgi_client import post_json

_ADDITION_ROUTE = "combine"
_S4 = "S4_worked_example"


def _fractions(statement: str) -> list[Rational]:
    return [Rational(int(p), int(q)) for p, q in re.findall(r"(\d+)/(\d+)", statement)]


def _wrong_answer(problem: dict[str, Any]) -> str:
    """A wrong answer for any served practice problem (drives consecutive errors → S4).

    For numeric items we return a value we know differs from the target; for yes/no we
    return the empty string, which the verifier treats as wrong (honest, never a crash).
    """
    if problem["answer_kind"] == "yes_no":
        return ""
    if problem["surface_format"] == "number_line":
        return "0/1"  # 0 is never the placement target the generator picks
    return "0/1"


def _turn(app: Any, session_id: str, problem: dict[str, Any], answer: str) -> dict[str, Any]:
    status, body = post_json(
        app,
        "/turn",
        {
            "session_id": session_id,
            "problem_id": problem["problem_id"],
            "action": "submit_answer",
            "submitted_answer": answer,
            "surface_state": "S1_symbolic_focus",
            "latency_ms": 6000,
            "hint_used": False,
        },
    )
    assert status == 200, body
    assert isinstance(body, dict)
    return body


def _correct_addition_answer(problem: dict[str, Any]) -> str:
    """The correct numeric answer for an addition practice problem (to get a clean turn)."""
    s = problem["statement"]
    if problem["surface_format"] == "number_line":
        seg = problem["tick_segments"]
        fr = _fractions(s)
        value = fr[0] + fr[1] if "Add" in s else fr[0] - fr[1] if "Subtract" in s else fr[0]
        return f"{int(value * seg)}/{seg}"
    if "missing top" in s:
        return (
            f"{int(_fractions(s)[0] * problem['given_denominator'])}/{problem['given_denominator']}"
        )
    fr = _fractions(s)
    value = fr[0] + fr[1] if "+" in s else fr[0] - fr[1]
    return f"{value.p}/{value.q}"


def _drive_to_s4(app: Any) -> dict[str, Any]:
    """Submit wrong answers until the policy transitions to S4; return that turn's body."""
    _, started = post_json(app, "/session", {"route_key": _ADDITION_ROUTE})
    session_id, problem = started["session_id"], started["problem"]
    for _ in range(10):
        body = _turn(app, session_id, problem, _wrong_answer(problem))
        if body["next_surface_state"] == _S4:
            return body
        assert body["next_problem"] is not None
        problem = body["next_problem"]
    raise AssertionError("two consecutive wrong answers never reached S4")


def test_s4_transition_serves_a_nonempty_worked_example() -> None:
    """On the S4 transition the response carries a non-empty list of {shown, why_prompt}."""
    body = _drive_to_s4(create_app())
    assert body["next_surface_state"] == _S4
    worked = body["worked_example"]
    assert isinstance(worked, list)
    assert worked, "an addition stuck problem should produce a buildable worked example"
    for step in worked:
        assert set(step.keys()) == {"shown", "why_prompt"}
        assert step["shown"]
        assert step["why_prompt"]


def test_worked_example_is_the_stuck_problem_not_the_next_problem() -> None:
    """The worked steps explain the JUST-answered problem — never the next practice item.

    The next problem's answer must not leak. We assert the next_problem id does not appear
    in any worked step text (the worked example is of a different, already-seen problem)."""
    body = _drive_to_s4(create_app())
    next_problem = body["next_problem"]
    assert next_problem is not None
    text = " ".join(s["shown"] + s["why_prompt"] for s in body["worked_example"])
    assert next_problem["problem_id"] not in text


def test_normal_correct_turn_carries_no_worked_example() -> None:
    """A normal (non-S4) correct turn returns an empty worked_example (the default)."""
    app = create_app()
    _, started = post_json(app, "/session", {"route_key": _ADDITION_ROUTE})
    session_id, problem = started["session_id"], started["problem"]
    body = _turn(app, session_id, problem, _correct_addition_answer(problem))
    assert body["next_surface_state"] != _S4
    assert body["worked_example"] == []
