"""Behavioral tests for KC_volume_fractional_edges — a Grade-6 (Unit 6) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope right-rectangular-prism item with FRACTIONAL edge
lengths (everything an exact SymPy ``Rational``, no float); the verifier confirms the correct
volume V = l*w*h and classifies the add-edges misconception (summing l + w + h instead of
multiplying); the worked example lands on the answer; and generation is deterministic
(PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: CCSS 6.G.2 — volume of
a right rectangular prism with fractional edge lengths.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, add_edges_instead_of_multiplying
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_volume_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_volume_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with three positive edge operands; answer = l*w*h."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 3
    length, width, height = problem.operands
    assert length > 0 and width > 0 and height > 0
    assert problem.correct_value == length * width * height


def test_at_least_one_edge_is_fractional() -> None:
    """Across seeds some item carries a genuinely fractional edge (q != 1) — 6.G.2's point."""
    saw_fraction = False
    for seed in range(1, 40):
        operands = _problem(seed).operands
        assert operands is not None
        if any(edge.q != 1 for edge in operands):
            saw_fraction = True
            break
    assert saw_fraction


def test_correct_volume_verifies_correct() -> None:
    """The product l*w*h is graded correct by the tutor's own oracle, as an exact Rational."""
    for seed in range(1, 16):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_add_edges_misconception_is_classified() -> None:
    """Summing the edges (l + w + h) is flagged OPERATION + the add-edges misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — added the edges
    instead of multiplying them. The generator guarantees l + w + h != l * w * h, so the summed
    value is always DISTINCT from the correct volume and the match is always diagnostic.
    """
    for seed in range(1, 16):
        problem = _problem(seed)
        assert problem.operands is not None
        length, width, height = problem.operands
        wrong = add_edges_instead_of_multiplying(length, width, height)
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.ADD_EDGES_ERROR


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_volume() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_known_example_multiplies_to_the_fraction() -> None:
    """Spot check the canonical example: 3/2 * 2 * 5/2 = 15/2, not the sum 6."""
    length, width, height = Rational(3, 2), Rational(2), Rational(5, 2)
    assert length * width * height == Rational(15, 2)
    assert add_edges_instead_of_multiplying(length, width, height) == Rational(6)
