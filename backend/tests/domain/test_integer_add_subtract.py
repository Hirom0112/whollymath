"""Behavioral tests for KC_integer_add_subtract — a Grade-6 (Unit-INT) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope opposite-sign integer addition; the verifier confirms
the correct signed sum and classifies the sign-handling misconception (adding the magnitudes
and ignoring the signs); the worked example lands on the answer; and generation is
deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: TEKS
6.3C/6.3D (adjacent-grade 7.NS.A.1) — add & subtract integers.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, add_magnitudes_ignoring_sign
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.scene import scene_for
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.INTEGER_ADD_SUBTRACT


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_integer_add_subtract_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_number_line_is_the_same_item_with_a_picture() -> None:
    """NUMBER_LINE serves the SAME scalar answer as SYMBOLIC (same operands + value), now with a
    directed-jump scene attached — the masterable second representation, no new input widget.
    Closes the naked-computation gap flagged in the panel audit (2026-06-04)."""
    sym = generate_problem(_KC, seed=5, surface_format=Representation.SYMBOLIC)
    line = generate_problem(_KC, seed=5, surface_format=Representation.NUMBER_LINE)
    assert line.surface_format is Representation.NUMBER_LINE
    assert line.operands == sym.operands
    assert line.correct_value == sym.correct_value
    assert scene_for(_KC, line.operands) is not None


def test_generated_sum_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with two OPPOSITE-sign integer operands; answer = a+b.

    Opposite signs are the hard, diagnostic case (the place the add-the-magnitudes error bites),
    and they guarantee the misconception's value differs from the correct one.
    """
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    a, b = problem.operands
    assert a.q == 1 and b.q == 1  # signed integers
    assert a != 0 and b != 0
    assert (a > 0) != (b > 0)  # opposite signs
    assert problem.correct_value == a + b


def test_correct_sum_verifies_correct() -> None:
    """The signed sum (a + b) is graded correct by the tutor's own oracle."""
    for seed in range(1, 16):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_sign_handling_error_is_classified() -> None:
    """Adding the magnitudes (ignoring signs) is flagged OPERATION + the sign-handling error.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — combined the two
    numbers as if both were positive (whole-number addition of magnitudes, |a| + |b|) rather than
    accounting for the opposite signs. With opposite-sign operands the magnitude sum |a| + |b| is
    always strictly larger than |a + b|, so it is always a DISTINCT, wrong value.
    """
    for seed in range(1, 16):
        problem = _problem(seed)
        assert problem.operands is not None
        a, b = problem.operands
        wrong = add_magnitudes_ignoring_sign(a, b)
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.SIGN_HANDLING_ERROR


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_integer_add_subtract() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
