"""Behavioral tests for KC_signed_numbers — a Grade-6 (Unit 3) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope "opposite of N" item; the verifier confirms the
correct opposite and classifies the sign-error misconception (answering N unchanged — the
"opposite of a negative is still negative" / dropped-the-flip error); the worked example
lands on the answer; and generation is deterministic (PROJECT.md §4.1). Mandatory-TDD domain
Layer 1 (CLAUDE.md §2). Skill: 6.NS.5 — positive & negative numbers, opposites.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, keep_original_sign
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.SIGNED_NUMBERS


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_signed_numbers_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_opposite_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with a single nonzero integer operand; answer = -N."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 1
    n = problem.operands[0]
    assert n != 0
    assert n.q == 1  # a whole-number magnitude (signed integer)
    assert problem.correct_value == -n


def test_correct_opposite_verifies_correct() -> None:
    """The signed opposite (-N) is graded correct by the tutor's own oracle."""
    for seed in range(1, 16):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_sign_error_is_classified() -> None:
    """Answering N unchanged is flagged OPERATION + the keep-original-sign misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — failed to apply
    the opposite (flip the sign) and returned the number as-is, e.g. "the opposite of -7 is -7".
    The magnitude is right; the operation (negation) was not performed. The unchanged value N is
    always DISTINCT from the correct -N because N != 0 (so N != -N).
    """
    for seed in range(1, 16):
        problem = _problem(seed)
        assert problem.operands is not None
        n = problem.operands[0]
        wrong = keep_original_sign(n)
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.SIGN_ERROR


def test_both_signs_are_generated() -> None:
    """Across seeds the operand takes both signs — opposites of positives AND of negatives."""
    signs = {1 if _problem(s).operands[0] > 0 else -1 for s in range(1, 40)}  # type: ignore[index]
    assert signs == {1, -1}


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_signed_numbers() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_opposite_of_a_positive_negates() -> None:
    """A spot check on a positive input: opposite of a positive is its negative."""
    # Find a seed producing a positive operand and confirm the answer is its negation.
    for seed in range(1, 40):
        problem = _problem(seed)
        n = problem.operands[0]  # type: ignore[index]
        if n > 0:
            assert problem.correct_value == Rational(-int(n))
            break
    else:  # pragma: no cover - the generator produces positives within this range
        raise AssertionError("no positive operand produced in seed range")
