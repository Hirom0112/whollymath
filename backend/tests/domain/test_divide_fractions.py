"""Behavioral tests for KC_divide_fractions — a Grade-6 (Unit 2, T2) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope division of two proper fractions; the verifier confirms
the correct invert-and-multiply quotient and classifies the multiply-without-inverting
misconception; the worked example lands on the answer; and generation is deterministic
(PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: 6.NS.1 — divide a
fraction by a fraction (invert and multiply).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, multiply_without_inverting
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.DIVIDE_FRACTIONS


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_divide_fractions_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_division_is_a_clean_in_scope_problem() -> None:
    """The generator yields a fraction item with a (dividend, divisor) pair and the quotient.

    The quotient is dividend / divisor = dividend * (1/divisor) — invert and multiply.
    """
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    dividend, divisor = problem.operands
    assert divisor != 0
    assert problem.correct_value == dividend / divisor


def test_correct_quotient_verifies_correct() -> None:
    """The SymPy quotient (invert-and-multiply) is graded correct by the tutor's own oracle."""
    for seed in range(1, 12):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_multiply_without_inverting_is_classified() -> None:
    """The multiply-across-no-invert answer is flagged OPERATION + the divide misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — multiplied the two
    fractions straight across instead of inverting the divisor first (a/b ÷ c/d done as a/b × c/d).
    The no-invert value ``(a*c)/(b*d)`` is always DISTINCT from the correct ``(a*d)/(b*c)`` because
    the divisor c/d is proper (c < d ⇒ c != d), so the two only coincide when c == d — never here.
    """
    for seed in range(1, 12):
        problem = _problem(seed)
        assert problem.operands is not None
        dividend, divisor = problem.operands
        wrong = multiply_without_inverting(dividend, divisor)
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.MULTIPLY_WITHOUT_INVERTING


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_divide_fractions() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
