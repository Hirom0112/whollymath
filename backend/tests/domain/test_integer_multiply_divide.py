"""Behavioral tests for KC_integer_multiply_divide — a Grade-6 (Unit-INT) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds clean, in-scope multiply AND divide items (divide always divides evenly,
so the quotient is an integer); the verifier confirms the correct signed result and classifies
the sign-rule misconception (right magnitude, flipped sign — e.g. -3 × 4 -> 12 instead of -12);
the worked example lands on the answer; both operation modes and both like/unlike sign pairs are
generated; and generation is deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1
(CLAUDE.md §2). Skill: TEKS 6.3C/D — multiply & divide signed integers.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, flip_result_sign
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_integer_multiply_divide_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_item_is_clean_and_in_scope() -> None:
    """Each item is numeric with operands (a, b, mode): nonzero integers + a 0/1 mode flag."""
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.kc is _KC
        assert problem.answer_kind is AnswerKind.NUMERIC
        assert problem.operands is not None and len(problem.operands) == 3
        a, b, mode = problem.operands
        assert a != 0 and b != 0  # nonzero, so the result is nonzero (sign-flip is diagnostic)
        assert a.q == 1 and b.q == 1  # signed integers
        assert int(mode) in (0, 1)  # 1 == multiply, 0 == divide
        # The correct value is an integer (a*b, or a/b which divides evenly).
        assert problem.correct_value.q == 1
        assert problem.correct_value != 0


def test_correct_result_verifies_correct() -> None:
    """The signed product/quotient is graded correct by the tutor's own oracle."""
    for seed in range(1, 30):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_multiply_and_divide_results_are_right() -> None:
    """Multiply items answer a*b; divide items answer a/b exactly (an integer)."""
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.operands is not None
        a, b, mode = problem.operands
        if int(mode) == 1:
            assert problem.correct_value == a * b
        else:
            assert problem.correct_value == Rational(a, b)
            assert a == problem.correct_value * b  # even division: dividend = quotient × divisor


def test_sign_rule_error_is_classified() -> None:
    """A right-magnitude, flipped-sign answer is flagged OPERATION + the sign-rule misconception.

    The learner computed the size correctly but applied the wrong sign rule (e.g. -3 × 4 -> 12).
    The flipped value -(result) always differs from the correct result because the result is
    nonzero (both operands nonzero, division even), so the match is always diagnostic.
    """
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.operands is not None
        wrong = flip_result_sign(problem.operands)
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.SIGN_RULE_ERROR


def test_both_operation_modes_are_generated() -> None:
    """Across seeds both multiply (mode 1) and divide (mode 0) items appear."""
    modes = {int(_problem(s).operands[2]) for s in range(1, 60)}  # type: ignore[index]
    assert modes == {0, 1}


def test_both_like_and_unlike_sign_pairs_are_generated() -> None:
    """Across seeds the operand pair takes both like signs and unlike signs (exercises the rule)."""
    same_sign_seen = False
    unlike_sign_seen = False
    for seed in range(1, 60):
        problem = _problem(seed)
        assert problem.operands is not None
        a, b, _ = problem.operands
        if (a > 0) == (b > 0):
            same_sign_seen = True
        else:
            unlike_sign_seen = True
    assert same_sign_seen and unlike_sign_seen


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in (3, 11, 27):  # span multiply and divide modes
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_integer_multiply_divide() -> None:
    """A conceptual nudge exists for the KC (no numbers, just the sign rule)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_unlike_signs_give_a_negative_product() -> None:
    """Spot check: an unlike-sign multiply yields a negative result; like-sign a positive one."""
    saw_negative = False
    saw_positive = False
    for seed in range(1, 60):
        problem = _problem(seed)
        assert problem.operands is not None
        a, b, mode = problem.operands
        if int(mode) != 1:
            continue
        if (a > 0) != (b > 0):  # unlike signs
            assert problem.correct_value < 0
            saw_negative = True
        else:  # like signs
            assert problem.correct_value > 0
            saw_positive = True
    assert saw_negative and saw_positive
