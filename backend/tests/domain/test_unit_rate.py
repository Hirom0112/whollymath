"""Behavioral tests for KC_unit_rate — the first Grade-6 (Unit 1) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope unit rate; the verifier confirms the correct rate
and classifies the rate-inversion misconception; the worked example lands on the answer;
and generation is deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, invert_rate
from app.domain.problem_generators import AnswerKind, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.UNIT_RATE


def _problem(seed: int):
    return generate_problem(_KC, seed)


def test_unit_rate_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_unit_rate_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with a (total, count) pair and a positive rate."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    total, count = problem.operands
    assert problem.correct_value == total / count
    assert problem.correct_value > 0


def test_correct_rate_verifies_correct() -> None:
    """The SymPy quotient (the unit rate) is graded correct by the tutor's own oracle."""
    for seed in range(1, 12):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_rate_inversion_is_classified() -> None:
    """The inverted rate (count/total) is flagged OPERATION + the rate-inversion misconception."""
    for seed in range(1, 12):
        problem = _problem(seed)
        total, count = problem.operands  # type: ignore[misc]
        inverted = invert_rate(int(total), int(count))
        # Only assert classification when the inverted rate is genuinely a DIFFERENT, wrong value
        # (it always is here: total > count > 0 ⇒ total/count != count/total).
        result = verify(problem, str(inverted))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.RATE_INVERSION


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_unit_rate() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
