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
from app.domain.misconceptions import (
    MisconceptionId,
    forget_trapezoid_half,
    forget_triangle_half,
)
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.AREA_POLYGONS
_TRIANGLE_MODE = 0
_PARALLELOGRAM_MODE = 1
_TRAPEZOID_MODE = 2


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _mode(problem: Problem) -> int:
    # The mode flag is always the LAST operand: 3-tuple (base, height, mode) for triangle/
    # parallelogram, 4-tuple (base1, base2, height, mode) for trapezoid (it needs two bases).
    assert problem.operands is not None
    return int(problem.operands[-1])


def test_area_polygons_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_area_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with whole-number side operands across every mode.

    Triangle/parallelogram carry a 3-tuple (base, height, mode); a trapezoid carries a 4-tuple
    (base1, base2, height, mode) — it needs two parallel sides. Every side is a positive whole
    number and the area lands whole (the generator forces the relevant product even)."""
    for seed in range(1, 60):
        problem = _problem(seed)
        assert problem.kc is _KC
        assert problem.answer_kind is AnswerKind.NUMERIC
        assert problem.operands is not None
        *sides, mode = problem.operands
        assert int(mode) in (_TRIANGLE_MODE, _PARALLELOGRAM_MODE, _TRAPEZOID_MODE)
        if int(mode) == _TRAPEZOID_MODE:
            assert len(problem.operands) == 4  # (base1, base2, height, mode)
        else:
            assert len(problem.operands) == 3  # (base, height, mode)
        for side in sides:
            assert side > 0
            assert side.q == 1  # whole-number sides (a sign-free, fraction-free area item)
        # The area is a whole number in scope (the generator keeps the halved product even).
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


def test_all_three_shape_modes_are_generated() -> None:
    """Across seeds the generator produces triangles, parallelograms, AND trapezoids.

    The trapezoid mode is the Slice-4c addition: the U6.L3 (6.G.1) lesson promises trapezoids,
    so the seeded RNG must pick all three shapes (a wider range than the old two-mode flag)."""
    modes = {_mode(_problem(seed)) for seed in range(1, 80)}
    assert modes == {_TRIANGLE_MODE, _PARALLELOGRAM_MODE, _TRAPEZOID_MODE}


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


def _trapezoid_seed() -> int:
    """The first seed that yields a trapezoid item (mode 2) — kept small for fast tests."""
    for seed in range(1, 80):
        if _mode(_problem(seed)) == _TRAPEZOID_MODE:
            return seed
    raise AssertionError("no trapezoid item produced in seed range")  # pragma: no cover


def test_trapezoid_area_is_half_sum_of_bases_times_height() -> None:
    """A trapezoid item's correct value is 1/2 · (base1 + base2) · height — the 6.G.1 formula.

    A trapezoid carries TWO parallel sides, so its operands are a 4-tuple (base1, base2, height,
    mode); the area is the average of the two bases times the height. The bases are distinct,
    positive whole numbers and the area lands whole (the generator keeps the product even)."""
    seen_trapezoid = False
    for seed in range(1, 80):
        problem = _problem(seed)
        if _mode(problem) != _TRAPEZOID_MODE:
            continue
        seen_trapezoid = True
        assert problem.operands is not None and len(problem.operands) == 4
        base1, base2, height, _ = problem.operands
        assert base1 > 0 and base2 > 0 and height > 0
        assert base1 != base2  # two DISTINCT parallel sides (a genuine trapezoid)
        assert problem.correct_value == Rational((base1 + base2) * height, 2)
        assert problem.correct_value.q == 1  # whole-number area (clean grade-6 answer)
    assert seen_trapezoid


def test_trapezoid_surfaces_share_operands_for_the_same_seed() -> None:
    """SYMBOLIC and AREA_MODEL trapezoid items generate from the SAME operands for one seed.

    The math is sampled before the surface is chosen, so a learner answers the one trapezoid two
    ways with the same numeric area (the representation-diversity contract, PROJECT.md §3.4)."""
    seed = _trapezoid_seed()
    symbolic = generate_problem(_KC, seed, Representation.SYMBOLIC)
    area_model = generate_problem(_KC, seed, Representation.AREA_MODEL)
    assert symbolic.operands == area_model.operands
    assert symbolic.correct_value == area_model.correct_value
    assert _mode(symbolic) == _TRAPEZOID_MODE  # both surfaces stayed on the trapezoid
    assert verify(area_model, str(area_model.correct_value)).is_correct


def test_forgot_the_half_is_classified_on_trapezoids() -> None:
    """Answering (base1+base2)·height (no 1/2) on a TRAPEZOID is flagged OPERATION + the error.

    Parallel to the triangle case: the learner summed the bases and multiplied by the height but
    skipped the averaging 1/2 (a trapezoid's area is the AVERAGE of the bases times the height).
    The un-halved (b1+b2)·h is always DISTINCT from the correct 1/2·(b1+b2)·h because the sum and
    height are positive."""
    seen_trapezoid = False
    for seed in range(1, 80):
        problem = _problem(seed)
        if _mode(problem) != _TRAPEZOID_MODE:
            continue
        seen_trapezoid = True
        wrong = forget_trapezoid_half(problem.operands)  # type: ignore[arg-type]
        assert wrong is not None
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.FORGOT_TRAPEZOID_HALF
    assert seen_trapezoid


def test_correct_trapezoid_answer_is_not_flagged() -> None:
    """The computed trapezoid area is graded correct (no misconception), the same oracle path."""
    seed = _trapezoid_seed()
    problem = _problem(seed)
    result = verify(problem, str(problem.correct_value))
    assert result.is_correct
    assert result.error_category is ErrorCategory.NONE
    assert result.matched_misconception is None


def test_triangle_and_trapezoid_half_errors_stay_distinct() -> None:
    """forgot-triangle-half never fires on a trapezoid; forgot-trapezoid-half never on a triangle.

    The two half-dropping errors are mode-scoped by operand ARITY: the triangle predictor reads
    a 3-tuple and returns None off triangle mode; the trapezoid predictor reads a 4-tuple and
    returns None off trapezoid mode. They must not cross-classify."""
    triangle_seed = next(s for s in range(1, 80) if _mode(_problem(s)) == _TRIANGLE_MODE)
    trapezoid_seed = _trapezoid_seed()
    triangle = _problem(triangle_seed)
    trapezoid = _problem(trapezoid_seed)
    # The trapezoid predictor must not apply to a triangle's 3-tuple (defensive arity gate).
    assert forget_trapezoid_half(triangle.operands) is None  # type: ignore[arg-type]
    # The triangle predictor must not apply to a trapezoid's 4-tuple (defensive arity gate).
    assert forget_triangle_half(trapezoid.operands) is None  # type: ignore[arg-type]


def test_worked_example_lands_on_a_trapezoid_answer() -> None:
    """The worked example's final step equals a trapezoid item's correct value (consistency)."""
    seed = _trapezoid_seed()
    problem = _problem(seed)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


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
