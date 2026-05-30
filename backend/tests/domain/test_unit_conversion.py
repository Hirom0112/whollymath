"""Behavioral tests for KC_unit_conversion — Grade-6 Unit 1 (2026-05-30).

Convert units via ratio reasoning (TEKS 6.4H / partial CCSS 6.RP.3d): given a conversion
factor ("12 inches = 1 foot") and a quantity in the larger unit, find the quantity in the
smaller unit (4 feet -> 48 inches). Exercises the KC through the SAME oracle the tutor uses
(the SymPy verifier), so "correct"/"wrong" means exactly what it means in production
(ARCHITECTURE.md §9). Pins: the generator builds a clean, in-scope conversion; the verifier
confirms the correct product and classifies the conversion-factor-inversion misconception (an
OPERATION error — dividing/flipping when you should multiply); the worked example lands on the
answer; and generation is deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1
(CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, invert_conversion
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.UNIT_CONVERSION


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_unit_conversion_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_conversion_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with a (quantity, factor) pair and a positive answer."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    quantity, factor = problem.operands
    # Convert UP the count: smaller-unit amount = quantity * factor (4 feet * 12 = 48 inches).
    assert problem.correct_value == quantity * factor
    assert problem.correct_value > 0
    # The factor is a genuine conversion (more than 1 small unit per large unit), so the
    # inversion error is always a DIFFERENT, smaller value.
    assert factor > 1


def test_correct_conversion_verifies_correct() -> None:
    """The SymPy product (quantity * factor) is graded correct by the tutor's own oracle."""
    for seed in range(1, 12):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_conversion_inversion_is_classified() -> None:
    """The inverted answer (quantity/factor) is flagged OPERATION + the inversion misconception."""
    for seed in range(1, 12):
        problem = _problem(seed)
        assert problem.operands is not None
        quantity, factor = problem.operands
        inverted = invert_conversion(int(quantity), int(factor))
        # The inverted value is genuinely a DIFFERENT, wrong value here: factor > 1 and
        # quantity > 0 ⇒ quantity*factor != quantity/factor.
        assert inverted != problem.correct_value
        result = verify(problem, str(inverted))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.CONVERSION_INVERSION


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_unit_conversion() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
