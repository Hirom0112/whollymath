"""Behavioral tests for KC_percent — Grade-6 Unit 1 (2026-05-30).

Exercises the KC through the SAME oracle the tutor uses (the SymPy verifier). Pins: the
generator builds a "percent of a quantity" item; the verifier confirms the correct value and
flags the percent-as-amount misconception (answering the percent itself); the worked example
lands on the answer; generation is deterministic. Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.PERCENT


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_percent_is_live() -> None:
    assert _KC in LIVE_KCS


def test_generated_problem_is_percent_of_a_whole() -> None:
    problem = _problem(6)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    percent, whole = (int(o) for o in problem.operands)
    assert problem.correct_value == Rational(percent * whole, 100)


def test_correct_value_verifies_correct() -> None:
    for seed in range(1, 12):
        problem = _problem(seed)
        assert verify(problem, str(problem.correct_value)).is_correct


def test_percent_as_amount_is_classified() -> None:
    """Answering the percent NUMBER itself is flagged OPERATION + percent-as-amount."""
    for seed in range(1, 12):
        problem = _problem(seed)
        assert problem.operands is not None
        percent = int(problem.operands[0])
        # The generator excludes whole == 100, so the percent itself is always wrong here.
        assert Rational(percent) != problem.correct_value
        result = verify(problem, str(percent))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.PERCENT_AS_AMOUNT


def test_generation_is_deterministic() -> None:
    assert generate_problem(_KC, 8).statement == generate_problem(_KC, 8).statement
    assert generate_problem(_KC, 8).correct_value == generate_problem(_KC, 8).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    problem = _problem(2)
    assert worked_example_for(problem).final_value == problem.correct_value


def test_nudge_bank_covers_percent() -> None:
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
