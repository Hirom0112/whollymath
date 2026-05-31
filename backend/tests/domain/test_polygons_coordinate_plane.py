"""Behavioral tests for KC_polygons_coordinate_plane — Grade-6 Unit 6 (CCSS 6.G.3).

Draw polygons in the coordinate plane given vertices, and use coordinates to solve problems: give
the missing vertex of a rectangle from three corners, or name the vertices of a rectangle. This KC
REUSES the coordinate point-set answer contract introduced by KC_coordinate_plane (6.NS.8): the
answer kind is ``AnswerKind.COORDINATE``, the surface is ``Representation.COORDINATE_PLANE`` (widget
``coordinate_plane``), and grading is the SAME order-insensitive integer-point set comparison the
verifier already does (``parse_points`` / ``_verify_coordinate``) — NO new answer kind, widget, or
grading path. The misconception is the SAME coordinate-swap (plot/read (x,y) as (y,x)); for the
missing-vertex item that means transposing the new corner. SymPy/domain decides; never an LLM
(CLAUDE.md §8.2).

Pins (all through the SAME oracle the tutor uses): the generator emits a COORDINATE item carrying
the canonical answer in ``correct_points``; the verifier grades an order-shuffled answer correct and
a wrong-set answer wrong; the coordinate-swap answer is flagged OPERATION + coordinate-swap;
unparseable input is wrong (OTHER), never a crash; the worked example lands on the canonical points;
generation is deterministic; both the single-vertex (missing corner) and multi-vertex (name the
rectangle) item shapes are produced. Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.lesson_spec import WidgetId, get_lesson_spec, widget_for_representation
from app.domain.misconceptions import MISCONCEPTION_REGISTRY, MisconceptionId, swap_coordinates
from app.domain.prerequisites import SPINE_ORDER, prerequisites_of
from app.domain.problem_generators import AnswerKind, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import live_representations
from app.policy.signal_routing import surface_state_for_representation
from app.policy.surface_states import SurfaceState
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.POLYGONS_COORDINATE_PLANE


def _problem(seed: int):  # type: ignore[no-untyped-def]
    return generate_problem(_KC, seed)


def test_polygons_coordinate_plane_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_reuses_the_coordinate_answer_contract() -> None:
    """No new answer kind/widget: the KC rides KC_coordinate_plane's frozen contract —
    answer_kind COORDINATE + the COORDINATE_PLANE representation → widget_id 'coordinate_plane'."""
    problem = _problem(7)
    assert problem.answer_kind is AnswerKind.COORDINATE
    assert problem.surface_format is Representation.COORDINATE_PLANE
    assert widget_for_representation(Representation.COORDINATE_PLANE) is WidgetId.COORDINATE_PLANE


def test_generated_problem_is_a_coordinate_item() -> None:
    """A COORDINATE item: the surface is COORDINATE_PLANE, the answer is in correct_points."""
    problem = _problem(7)
    assert problem.kc is _KC
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
    """A polygon's vertices match regardless of listing order — grading is a SET comparison."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.correct_points is not None
        points = problem.correct_points.split("),")
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
    """A genuinely different set of points grades wrong."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.correct_points is not None
        assert not verify(problem, "(99,99)").is_correct


def test_coordinate_swap_misconception_is_classified() -> None:
    """The coordinate-swap answer (plot (x,y) as (y,x)) is flagged OPERATION + coordinate-swap —
    the axis/coordinate-order confusion 6.G.3 surfaces, when it is genuinely wrong."""
    flagged_at_least_once = False
    for seed in range(1, 80):
        problem = _problem(seed)
        wrong = swap_coordinates(problem.correct_points)
        if wrong is None:
            continue  # symmetric across y = x: swapping is the same set, no wrong form
        result = verify(problem, wrong)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.COORDINATE_SWAP
        flagged_at_least_once = True
    assert flagged_at_least_once, "expected at least one seed to produce a swappable answer"


def test_unparseable_submission_is_wrong_not_a_crash() -> None:
    """Garbled input grades wrong (OTHER), never raises (CLAUDE.md §8.2)."""
    problem = _problem(1)
    for junk in ("", "(", "(2,", "(a,b)", ")(", "2,3", "(1,2,3)", "(1.5,2)", "hello"):
        result = verify(problem, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    first, second = generate_problem(_KC, 42), generate_problem(_KC, 42)
    assert first.statement == second.statement
    assert first.correct_points == second.correct_points


def test_both_missing_vertex_and_named_rectangle_items_are_generated() -> None:
    """The generator produces BOTH a single missing vertex and a multi-vertex named rectangle —
    the two 6.G.3 item shapes (give the 4th corner vs name the four corners)."""
    shapes = set()
    for seed in range(1, 80):
        points = _problem(seed).correct_points or ""
        shapes.add(points.count("(") == 1)  # True => single missing vertex, False => full polygon
    assert shapes == {True, False}


def test_coordinate_swap_misconception_applies_to_this_kc() -> None:
    """The shared coordinate-swap misconception declares this KC applicable (no new id added)."""
    swap = MISCONCEPTION_REGISTRY.get(MisconceptionId.COORDINATE_SWAP)
    assert _KC in swap.applicable_kcs


def test_lesson_spec_routes_operation_to_a_surface_with_state() -> None:
    """Error route targets COORDINATE_PLANE — a rep WITH a surface state — never WORD_PROBLEM."""
    spec = get_lesson_spec(_KC)
    assert spec.error_routes
    for route in spec.error_routes:
        assert surface_state_for_representation(route.representation) is not None


def test_surface_state_for_coordinate_plane_exists() -> None:
    """The answer surface has a concrete state (it reuses number-line-primary, the five-state set
    stays closed)."""
    assert surface_state_for_representation(Representation.COORDINATE_PLANE) is (
        SurfaceState.NUMBER_LINE_PRIMARY
    )


def test_practice_only_one_live_representation() -> None:
    """PRACTICE-ONLY: COORDINATE_PLANE is the single live rep (the coordinate-plane widget is the
    only surface that accepts a plotted point set; WORD_PROBLEM has no surface state)."""
    live = live_representations(_KC)
    assert live == (Representation.COORDINATE_PLANE,)


def test_prerequisite_and_spine_are_wired() -> None:
    """Forward-unlocks on the live KC_coordinate_plane, and sits on the teaching spine."""
    assert KnowledgeComponentId.COORDINATE_PLANE in prerequisites_of(_KC)
    assert _KC in SPINE_ORDER


def test_worked_example_lands_on_the_points() -> None:
    """The worked example's final step shows the canonical points (self-consistency)."""
    for seed in (3, 8):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert problem.correct_points is not None
        assert problem.correct_points in example.steps[-1].shown


def test_nudge_bank_covers_the_kc() -> None:
    """A conceptual nudge exists for the KC (no coordinates, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
