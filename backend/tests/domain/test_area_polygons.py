"""Behavioral tests for KC_area_polygons — a Grade-6 (Unit 6) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope "find the area" item over BOTH shape modes
(triangle: 1/2 · b · h; parallelogram/rectangle: b · h) behind an operand-mode flag; the
verifier confirms the correct area and classifies the forgot-the-half misconception (b · h
for a triangle) ONLY on triangle items, never on a parallelogram (where b · h IS correct);
the worked example lands on the answer; the KC is MASTERABLE-LIVE — SYMBOLIC and AREA_MODEL
are both live and answered with the SAME numeric area; and generation is deterministic
(PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: CCSS 6.G.1 — area of
triangles and quadrilaterals by composing/decomposing into rectangles and triangles.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, forget_triangle_half
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.AREA_POLYGONS
_TRIANGLE_MODE = 0
_PARALLELOGRAM_MODE = 1


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _mode(problem: Problem) -> int:
    assert problem.operands is not None
    return int(problem.operands[2])


def test_area_polygons_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_area_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with (base, height, mode) whole-number operands."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 3
    base, height, mode = problem.operands
    assert base > 0 and height > 0
    assert base.q == 1 and height.q == 1  # whole-number base/height (a signed-free area item)
    assert int(mode) in (_TRIANGLE_MODE, _PARALLELOGRAM_MODE)
    # The area is a whole number in scope (the generator keeps b·h even on triangles).
    assert problem.correct_value.q == 1


def test_triangle_area_is_half_base_times_height() -> None:
    """A triangle item's correct value is 1/2 · base · height (the formula the KC teaches)."""
    for seed in range(1, 60):
        problem = _problem(seed)
        if _mode(problem) != _TRIANGLE_MODE:
            continue
        assert problem.operands is not None
        base, height, _ = problem.operands
        assert problem.correct_value == Rational(base * height, 2)
        break
    else:  # pragma: no cover - the generator produces triangles within this range
        raise AssertionError("no triangle item produced in seed range")


def test_parallelogram_area_is_base_times_height() -> None:
    """A parallelogram/rectangle item's correct value is base · height (no halving)."""
    for seed in range(1, 60):
        problem = _problem(seed)
        if _mode(problem) != _PARALLELOGRAM_MODE:
            continue
        assert problem.operands is not None
        base, height, _ = problem.operands
        assert problem.correct_value == base * height
        break
    else:  # pragma: no cover - the generator produces parallelograms within this range
        raise AssertionError("no parallelogram item produced in seed range")


def test_correct_area_verifies_correct() -> None:
    """The computed area is graded correct by the tutor's own oracle, across both modes."""
    for seed in range(1, 40):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_both_shape_modes_are_generated() -> None:
    """Across seeds the generator produces BOTH triangles and parallelograms (the mode flag)."""
    modes = {_mode(_problem(seed)) for seed in range(1, 40)}
    assert modes == {_TRIANGLE_MODE, _PARALLELOGRAM_MODE}


def test_forgot_the_half_is_classified_on_triangles() -> None:
    """Answering b·h (no 1/2) on a TRIANGLE is flagged OPERATION + the forgot-the-half error.

    Routed to OPERATION (not MAGNITUDE): the learner used the WRONG PROCEDURE — applied the
    rectangle formula b·h to a triangle, skipping the 1/2 (decompose: a triangle is half its
    bounding parallelogram). The un-halved area b·h is always DISTINCT from the correct
    1/2·b·h because b·h > 0 (so b·h != b·h/2).
    """
    seen_triangle = False
    for seed in range(1, 60):
        problem = _problem(seed)
        if _mode(problem) != _TRIANGLE_MODE:
            continue
        seen_triangle = True
        wrong = forget_triangle_half(problem.operands)  # type: ignore[arg-type]
        assert wrong is not None
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.FORGOT_TRIANGLE_HALF
    assert seen_triangle


def test_forgot_the_half_does_not_fire_on_parallelograms() -> None:
    """On a parallelogram b·h IS the answer, so the forgot-the-half model must not apply."""
    seen_parallelogram = False
    for seed in range(1, 60):
        problem = _problem(seed)
        if _mode(problem) != _PARALLELOGRAM_MODE:
            continue
        seen_parallelogram = True
        # The predictor returns None for the parallelogram mode (b·h is correct, no error to model).
        assert forget_triangle_half(problem.operands) is None  # type: ignore[arg-type]
    assert seen_parallelogram


def test_area_polygons_is_masterable_live_on_two_representations() -> None:
    """SYMBOLIC and AREA_MODEL are BOTH live and answered with the SAME numeric area.

    Two real live representations meet the mastery model's representation-diversity rule
    (PROJECT.md §3.4 rule 2), so this KC is masterable-live — unlike the practice-only Grade-6
    KCs. The same seed yields the same area in either surface (the math is sampled before the
    surface is applied), so a learner answers the one skill two ways.
    """
    reps = live_representations(_KC)
    assert set(reps) == {Representation.SYMBOLIC, Representation.AREA_MODEL}
    for seed in range(1, 20):
        symbolic = generate_problem(_KC, seed, Representation.SYMBOLIC)
        area_model = generate_problem(_KC, seed, Representation.AREA_MODEL)
        assert symbolic.operands == area_model.operands
        assert symbolic.correct_value == area_model.correct_value
        # Both surfaces grade the SAME numeric answer.
        assert verify(area_model, str(area_model.correct_value)).is_correct


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in (3, 4, 5, 6, 7):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_area_polygons() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
