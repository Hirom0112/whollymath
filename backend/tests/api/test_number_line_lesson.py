"""The number-line lesson's 6th-grade ramp end-to-end (CP.B + CCSS 6.NS.6).

Drives the number-line lesson through the real turn loop, answering every problem correctly,
and asserts (a) the ramp actually serves IMPROPER (>1) and NEGATIVE (<0) placements — the
authorized 6th-grade scope (PROJECT.md §3.1) — not just 0–1 proper fractions, (b) every served
number-line item carries axis bounds wide enough to hold its target, and (c) the lesson still
reaches completion. SymPy judges every answer; the target is read straight off the statement.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from app.api.app import create_app

from tests.api.asgi_client import post_json


def _signed_fraction(text: str) -> Fraction | None:
    """The first signed a/b in a statement (e.g. '-6/5', '8/5'), as a Fraction."""
    m = re.search(r"(-?\d+)/(\d+)", text)
    return Fraction(int(m.group(1)), int(m.group(2))) if m else None


def _answer(problem: dict[str, Any]) -> str:
    """Correct answer for any served problem in a number-line lesson."""
    s = problem["statement"]
    if problem["answer_kind"] == "yes_no":  # "is a greater than b?" (incl. negative comparison)
        a, b = re.findall(r"(-?\d+)/(\d+)", s)
        return "yes" if Fraction(int(a[0]), int(a[1])) > Fraction(int(b[0]), int(b[1])) else "no"
    if problem["surface_format"] == "number_line":  # placement: answer IS the target shown
        target = _signed_fraction(s)
        assert target is not None
        return f"{target.numerator}/{target.denominator}"
    if "missing top" in s:  # equivalence companion (fill the top)
        base = _signed_fraction(s)
        assert base is not None
        n = base.numerator * problem["given_denominator"] // base.denominator
        return f"{n}/{problem['given_denominator']}"
    # equivalence word-problem companion (yes/no handled above); fall back to the shown fraction
    target = _signed_fraction(s)
    assert target is not None
    return f"{target.numerator}/{target.denominator}"


def test_number_line_lesson_serves_improper_and_negative_then_completes() -> None:
    app = create_app()
    _, started = post_json(app, "/session", {"kc": "KC_number_line_placement"})
    session_id, problem = started["session_id"], started["problem"]

    saw_improper = saw_negative = completed = False
    surface_state = started["surface_state"]
    for _ in range(60):
        if problem["surface_format"] == "number_line":
            target = _signed_fraction(problem["statement"])
            assert target is not None
            # The axis must be wide enough to hold the target (so the marker can actually reach it).
            assert problem["axis_min"] <= target <= problem["axis_max"], (
                f"axis [{problem['axis_min']},{problem['axis_max']}] cannot hold {target}"
            )
            if target > 1:
                saw_improper = True
            if target < 0:
                saw_negative = True
        body = post_json(
            app,
            "/turn",
            {
                "session_id": session_id,
                "problem_id": problem["problem_id"],
                "action": "submit_answer",
                "submitted_answer": _answer(problem),
                "surface_state": surface_state,
                "latency_ms": 6000,
                "hint_used": False,
            },
        )[1]
        assert body["correct"] is True, f"unexpected wrong answer on: {problem['statement']}"
        surface_state = body["next_surface_state"]
        if body.get("lesson_complete"):
            completed = True
            break
        problem = body["next_problem"]

    assert saw_improper, "the number-line ramp never served an improper (>1) placement"
    assert saw_negative, "the number-line ramp never served a negative (<0) placement"
    assert completed, "the number-line lesson never completed"
