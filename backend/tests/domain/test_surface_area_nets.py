"""Behavioral tests for KC_surface_area_nets — a Grade-6 (Unit 6) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope right-rectangular-prism (or cube) item whose net
unfolds to six faces; the verifier confirms the correct surface area SA = 2(lw + lh + wh)
and classifies the half-the-faces misconception (summing only lw + lh + wh — three faces,
forgetting to double); the worked example lands on the answer; and generation is
deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill:
CCSS 6.G.4 — surface area of a right rectangular prism from its net.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, count_three_faces_only
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.SURFACE_AREA_NETS


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_surface_area_nets_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_surface_area_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with three positive edges; answer = 2(lw+lh+wh)."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 3
    length, width, height = problem.operands
    assert length > 0 and width > 0 and height > 0
    assert problem.correct_value == 2 * (length * width + length * height + width * height)


def test_edges_are_whole_numbers() -> None:
    """Every edge is a whole number, so the net's faces have whole-number areas (6.G.4 scope)."""
    for seed in range(1, 40):
        operands = _problem(seed).operands
        assert operands is not None
        assert all(edge.q == 1 for edge in operands)


def test_correct_surface_area_verifies_correct() -> None:
    """The sum of the six face areas is graded correct by the tutor's own oracle."""
    for seed in range(1, 16):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_three_faces_misconception_is_classified() -> None:
    """Summing only lw + lh + wh (three faces) is flagged OPERATION + the count-three-faces error.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — added one of each
    pair of faces instead of doubling for the matching opposite face. Since lw + lh + wh > 0, the
    three-face value is always exactly half the correct surface area, so it is always DISTINCT from
    the correct answer and the match is always diagnostic.
    """
    for seed in range(1, 16):
        problem = _problem(seed)
        assert problem.operands is not None
        length, width, height = problem.operands
        wrong = count_three_faces_only(length, width, height)
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.COUNT_THREE_FACES


def test_a_cube_item_is_generated() -> None:
    """Across seeds some item is a cube (all three edges equal) — the simplest net (6 faces)."""
    saw_cube = False
    for seed in range(1, 60):
        operands = _problem(seed).operands
        assert operands is not None
        length, width, height = operands
        if length == width == height:
            saw_cube = True
            break
    assert saw_cube


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_surface_area_nets() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_known_example_sums_the_six_faces() -> None:
    """Spot check the canonical example: a 2x3x4 prism has SA = 2(6 + 8 + 12) = 52, not 26."""
    length, width, height = Rational(2), Rational(3), Rational(4)
    assert 2 * (length * width + length * height + width * height) == Rational(52)
    assert count_three_faces_only(length, width, height) == Rational(26)
