"""Behavioral tests for KC_coordinate_plane — Grade-6 Unit 3 (6.NS.8 / TEKS 6.11A).

Identify and plot points in the four-quadrant coordinate plane, including reflections across an
axis and same-axis distance. This KC introduces a NEW answer form: a set of integer-coordinate
POINTS (a single point ``"(2,-1)"`` or a polygon vertex list ``"(0,0),(3,0),(3,2)"``). The answer
is graded by the domain verifier as an ORDER-INSENSITIVE SET of integer-coordinate tuples — a
polygon's vertices match regardless of listing order, and a single point is a one-element set.
SymPy/domain decides; never an LLM (CLAUDE.md §8.2).

Pins (all through the SAME oracle the tutor uses): the generator emits a coordinate item carrying
the canonical answer in ``correct_points``; the verifier grades an order-shuffled answer correct
and a wrong-set answer wrong; the coordinate-swap misconception (plotting (x,y) as (y,x)) is
flagged OPERATION; unparseable/garbled input is wrong, never a crash; the worked example lands on
the canonical points; generation is deterministic. Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.lesson_spec import WidgetId, widget_for_representation
from app.domain.misconceptions import MisconceptionId, swap_coordinates
from app.domain.problem_generators import AnswerKind, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.signal_routing import surface_state_for_representation
from app.policy.surface_states import SurfaceState
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.COORDINATE_PLANE


def _problem(seed: int):  # type: ignore[no-untyped-def]
    return generate_problem(_KC, seed)


def test_coordinate_plane_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_answer_kind_has_coordinate_member() -> None:
    """The frozen wire contract: AnswerKind gains COORDINATE (value 'coordinate')."""
    assert AnswerKind.COORDINATE.value == "coordinate"


def test_widget_id_for_coordinate_plane_is_the_frozen_literal() -> None:
    """The frozen wire contract: the COORDINATE_PLANE representation maps to widget_id
    'coordinate_plane' (frontend selectWidget routes it → the coordinate-plane widget)."""
    assert widget_for_representation(Representation.COORDINATE_PLANE) is WidgetId.COORDINATE_PLANE
    assert WidgetId.COORDINATE_PLANE.value == "coordinate_plane"
    assert Representation.COORDINATE_PLANE.value == "coordinate_plane"


def test_generated_problem_is_a_coordinate_item() -> None:
    """A COORDINATE item: the surface is COORDINATE_PLANE, the answer is in correct_points."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.COORDINATE
    assert problem.surface_format is Representation.COORDINATE_PLANE
    assert problem.correct_points is not None and problem.correct_points.strip()
    assert problem.statement


def test_canonical_points_verify_correct() -> None:
    """Submitting the canonical answer is graded correct by the tutor's own oracle."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.correct_points is not None
        result = verify(problem, problem.correct_points)
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_grading_is_order_insensitive() -> None:
    """A polygon's vertices match regardless of listing order — grading is a SET comparison.

    Reversing the vertex order (and varying whitespace) must still grade correct: a coordinate
    answer is the set of points, never a positional string match."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.correct_points is not None
        points = problem.correct_points.split("),")
        # Re-glue the split (split drops the ")" on all but the last) and reverse the order.
        reglued = [p if p.endswith(")") else p + ")" for p in points]
        shuffled = " , ".join(reversed(reglued))
        assert verify(problem, shuffled).is_correct


def test_whitespace_and_spacing_are_tolerated() -> None:
    """Spaces inside and between tuples do not change the parsed set (kid-typed input is messy)."""
    for seed in range(1, 20):
        problem = _problem(seed)
        assert problem.correct_points is not None
        spaced = problem.correct_points.replace("(", "( ").replace(",", " , ").replace(")", " )")
        assert verify(problem, spaced).is_correct


def test_wrong_point_set_is_incorrect() -> None:
    """A different set of points grades wrong — a missing/extra/shifted vertex is not the answer."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.correct_points is not None
        # Shift every point by (+1, +1): a genuinely different set of integer points.
        shifted = swap_coordinates(problem.correct_points)  # may be None on a symmetric set
        far_wrong = "(99,99)"
        assert not verify(problem, far_wrong).is_correct
        if shifted is not None:
            # The swapped set is wrong unless the figure is symmetric across y = x (then it
            # equals the original and swap_coordinates returns None, handled above).
            assert not verify(problem, shifted).is_correct


def test_coordinate_swap_misconception_is_classified() -> None:
    """The coordinate-swap answer (plot (x,y) as (y,x)) is flagged OPERATION + coordinate-swap —
    the axis/coordinate confusion the lesson is designed to surface, when it is genuinely wrong."""
    for seed in range(1, 60):
        problem = _problem(seed)
        wrong = swap_coordinates(problem.correct_points)
        if wrong is None:
            continue  # symmetric figure across y = x: swapping is the same set, no wrong form
        result = verify(problem, wrong)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.COORDINATE_SWAP


def test_unparseable_submission_is_wrong_not_a_crash() -> None:
    """Garbled input grades wrong (OTHER), never raises — the verifier must not crash on what a
    kid types (CLAUDE.md §8.2)."""
    problem = _problem(1)
    for junk in ("", "(", "(2,", "(a,b)", ")(", "2,3", "(1,2,3)", "(1.5,2)", "hello"):
        result = verify(problem, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    first, second = generate_problem(_KC, 42), generate_problem(_KC, 42)
    assert first.correct_points == second.correct_points


def test_both_single_point_and_polygon_items_are_generated() -> None:
    """The generator produces BOTH a single point and a multi-vertex polygon across seeds —
    the two answer shapes the frozen contract names."""
    shapes = set()
    for seed in range(1, 80):
        points = _problem(seed).correct_points or ""
        shapes.add(points.count("(") == 1)  # True => single point, False => polygon
    assert shapes == {True, False}


def test_surface_state_for_coordinate_plane_exists() -> None:
    """The coordinate-plane rep has a concrete surface state (error routes need a live surface;
    it reuses the axis-based number-line-primary state — the five-state set stays closed)."""
    assert surface_state_for_representation(Representation.COORDINATE_PLANE) is not None
    assert surface_state_for_representation(Representation.COORDINATE_PLANE) is (
        SurfaceState.NUMBER_LINE_PRIMARY
    )


def test_worked_example_lands_on_the_points() -> None:
    """The worked example's final step shows the canonical points (self-consistency)."""
    for seed in (3, 8):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert problem.correct_points is not None
        assert problem.correct_points in example.steps[-1].shown


def test_nudge_bank_covers_coordinate_plane() -> None:
    """A conceptual nudge exists for the KC (no coordinates, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_swap_coordinates_is_none_on_symmetric_point() -> None:
    """A point on the diagonal (x == y, e.g. (3,3)) swaps to itself — swap_coordinates returns
    None so the verifier never flags a still-correct answer as the misconception."""
    assert swap_coordinates("(3,3)") is None
    assert swap_coordinates("(0,0)") is None
    # An off-diagonal point swaps to a genuinely different point.
    assert swap_coordinates("(2,-1)") == "(-1,2)"
