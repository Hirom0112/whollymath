"""The live S5 transfer-probe confirm-gate (PROJECT.md §3.4/§3.9).

Mastery declared in the live loop must be CONFIRMED — provisional (the §3.4 rules) PLUS
the transfer probe passed — not bare provisional. These tests drive the real turn loop
through the API: practise until the goal KC reaches provisional, then assert the probe is
presented and that mastered becomes true ONLY after passing every probe step; and that
failing a probe step demotes (no mastery) rather than confirming. SymPy decides every
answer (we compute the correct response from the statement); no LLM, no mocks.
"""

from __future__ import annotations

import re
from typing import Any

from app.api.app import create_app
from sympy import Rational

from tests.api.asgi_client import post_json

_ADDITION_ROUTE = "combine"


def _fractions(statement: str) -> list[Rational]:
    return [Rational(int(p), int(q)) for p, q in re.findall(r"(\d+)/(\d+)", statement)]


def _correct_answer(problem: dict[str, Any]) -> str:
    """The correct answer string for any served problem (practice or probe step)."""
    s = problem["statement"]
    if problem["answer_kind"] == "yes_no":
        fr = _fractions(s)
        if "Tim says" in s:  # reject step: is "a op b = c" right?
            value = fr[0] + fr[1] if "+" in s else fr[0] - fr[1]
            return "yes" if value == fr[2] else "no"
        if "greater than" in s:
            return "yes" if fr[0] > fr[1] else "no"
        if "into" in s and "took" in s:  # equivalence word problem
            pieces = int(re.search(r"into (\d+) equal", s).group(1))  # type: ignore[union-attr]
            taken = int(re.search(r"took (\d+)", s).group(1))  # type: ignore[union-attr]
            return "yes" if Rational(taken, pieces) == fr[0] else "no"
        return "yes" if fr[0] == fr[1] else "no"  # symbolic equivalence "is a the same as b?"
    if problem["surface_format"] == "number_line":
        seg = problem["tick_segments"]
        fr = _fractions(s)
        value = fr[0] + fr[1] if "Add" in s else fr[0] - fr[1] if "Subtract" in s else fr[0]
        return f"{int(value * seg)}/{seg}"
    if "missing top" in s:
        return (
            f"{int(_fractions(s)[0] * problem['given_denominator'])}/{problem['given_denominator']}"
        )
    fr = _fractions(s)  # symbolic arithmetic ("a + b = ?" / "what does a + b really equal?")
    value = fr[0] + fr[1] if "+" in s else fr[0] - fr[1]
    return f"{value.p}/{value.q}"


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


def _goal_mastered(body: dict[str, Any], goal_kc: str) -> bool:
    return any(m["kc_id"] == goal_kc and m["mastered"] for m in body["mastery"])


def _drive_until_probe(app: Any) -> tuple[str, dict[str, Any]]:
    """Practise the addition route until the S5 probe is presented; return (session_id, the
    first probe problem). Asserts mastery is NOT declared before the probe is passed."""
    _, started = post_json(app, "/session", {"route_key": _ADDITION_ROUTE})
    session_id, problem = started["session_id"], started["problem"]
    for _ in range(40):
        body = _turn(app, session_id, problem, _correct_answer(problem))
        # Provisional must NEVER show as mastered before the probe is passed.
        assert not _goal_mastered(body, "KC_addition_unlike")
        if body["next_surface_state"] == "S5_transfer_probe":
            return session_id, body["next_problem"]
        problem = body["next_problem"]
    raise AssertionError("addition route never reached the transfer probe")


def test_probe_must_be_passed_before_mastery_is_confirmed() -> None:
    """Answering every probe step correctly CONFIRMS mastery — and only then does the
    snapshot report mastered. Before the probe, provisional alone never reads as mastered."""
    app = create_app()
    session_id, probe_problem = _drive_until_probe(app)

    mastered = False
    for _ in range(5):  # the probe is at most 3 steps
        body = _turn(app, session_id, probe_problem, _correct_answer(probe_problem))
        if _goal_mastered(body, "KC_addition_unlike"):
            mastered = True
            break
        probe_problem = body["next_problem"]
    assert mastered, "passing every transfer-probe step should CONFIRM mastery"


def test_failing_a_probe_step_demotes_instead_of_confirming() -> None:
    """A wrong answer on a probe step fails the probe: no mastery is declared, and the next
    problem is practice (not another probe step) — the learner is demoted, not confirmed."""
    app = create_app()
    session_id, probe_problem = _drive_until_probe(app)

    body = _turn(app, session_id, probe_problem, "0/1")  # a wrong answer to the first step
    assert not _goal_mastered(body, "KC_addition_unlike")
    assert body["correct"] is False
    assert body["next_surface_state"] != "S5_transfer_probe"  # back to practice, not the probe
