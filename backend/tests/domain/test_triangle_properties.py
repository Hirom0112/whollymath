"""Behavioral tests for KC_triangle_properties — a Grade-6 (Unit 6) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). The KC
carries an item-mode flag: mode 0 finds the MISSING ANGLE of a triangle (the angle sum is
180°, so the third angle is 180 - a - b), and mode 1 finds the AREA from a base and height
(A = ½ · b · h). Both modes answer with a single NUMERIC value in the existing editor (NO new
widget). Pins: the generator builds a clean, in-scope item in each mode; the verifier confirms
the correct value and classifies the triangle-formula error (subtract from 90 instead of 180 for
the angle; drop the ½ for the area); the worked example lands on the answer; and generation is
deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: TEKS 6.8A —
apply the angle sum and the base/height–area relationship of a triangle.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, triangle_formula_error
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.TRIANGLE_PROPERTIES


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _modes(seeds: range) -> set[int]:
    """The set of item modes (operands[2]) produced across ``seeds``."""
    return {int(_problem(s).operands[2]) for s in seeds}  # type: ignore[index]


def test_triangle_properties_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_item_is_clean_and_in_scope() -> None:
    """Each item is NUMERIC with (a, b, mode) whole-number operands and a positive answer."""
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.kc is _KC
        assert problem.answer_kind is AnswerKind.NUMERIC
        assert problem.operands is not None and len(problem.operands) == 3
        a, b, mode = problem.operands
        assert a.q == 1 and b.q == 1  # whole-number measures (degrees or lengths)
        assert int(mode) in (0, 1)
        assert problem.correct_value > 0  # a real angle / a real area
        if int(mode) == 0:  # missing angle: third angle = 180 - a - b
            assert problem.correct_value == 180 - a - b
        else:  # area: ½ · base · height, and it is an integer (the generator keeps b·h even)
            assert problem.correct_value == a * b / 2
            assert problem.correct_value.q == 1


def test_correct_value_verifies_correct() -> None:
    """The correct angle / area is graded correct by the tutor's own oracle, in both modes."""
    for seed in range(1, 40):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_formula_error_is_classified() -> None:
    """The triangle-formula error (90 not 180 / dropped ½) is flagged OPERATION + misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — used 90 as the
    angle sum, or forgot the ½ in the area formula. The wrong value is always DISTINCT from the
    correct one (an angle wrong by 90; an area wrong by a factor of 2), so the match is diagnostic.
    """
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.operands is not None
        wrong = triangle_formula_error(problem.operands)
        assert wrong is not None
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.TRIANGLE_FORMULA_ERROR


def test_both_modes_are_generated() -> None:
    """Across seeds BOTH item modes appear — missing-angle AND base-height-area."""
    assert _modes(range(1, 60)) == {0, 1}


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value, in both modes."""
    angle_seed = next(s for s in range(1, 60) if int(_problem(s).operands[2]) == 0)  # type: ignore[index]
    area_seed = next(s for s in range(1, 60) if int(_problem(s).operands[2]) == 1)  # type: ignore[index]
    for seed in (angle_seed, area_seed):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_triangle_properties() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_formula_error_returns_none_for_bad_shape() -> None:
    """The predictor is defensive: a non-(a, b, mode) operand shape yields None, not a crash."""
    from sympy import Rational

    assert triangle_formula_error((Rational(1), Rational(2))) is None
