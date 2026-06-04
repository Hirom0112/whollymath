"""Behavioral tests for KC_multiply_fractions — Grade-6 Unit 2 (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean product of two proper fractions; the verifier confirms the
correct product and classifies the multiply-as-add misconception (treating x as +); the
worked example lands on the answer; and generation is deterministic (PROJECT.md §4.1).
Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.scene import scene_for
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.MULTIPLY_FRACTIONS


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_multiply_fractions_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_area_model_is_the_same_item_with_a_picture() -> None:
    """AREA_MODEL serves the SAME numeric answer as SYMBOLIC (same operands + value), now with a
    display scene attached — the masterable second representation, no new input widget
    (EVALUATE_EXPRESSIONS pattern). Closes the practice-only gap flagged in the panel audit
    (2026-06-04)."""
    sym = generate_problem(_KC, seed=5, surface_format=Representation.SYMBOLIC)
    area = generate_problem(_KC, seed=5, surface_format=Representation.AREA_MODEL)
    assert area.surface_format is Representation.AREA_MODEL
    assert area.operands == sym.operands
    assert area.correct_value == sym.correct_value
    assert scene_for(_KC, area.operands) is not None


def test_generated_problem_is_a_clean_product() -> None:
    """The generator yields a numeric item: a (first, second) pair whose product is the answer."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    first, second = problem.operands
    assert problem.correct_value == first * second
    assert problem.correct_value > 0


def test_correct_product_verifies_correct() -> None:
    """The SymPy product is graded correct by the tutor's own oracle."""
    for seed in range(1, 12):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_multiply_as_add_is_classified() -> None:
    """Adding instead of multiplying (x treated as +) is flagged OPERATION + multiply-as-add."""
    for seed in range(1, 12):
        problem = _problem(seed)
        assert problem.operands is not None
        first, second = problem.operands
        added = first + second  # the "treats x as +" wrong value
        result = verify(problem, str(added))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.MULTIPLY_AS_ADD


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_multiply_fractions() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
