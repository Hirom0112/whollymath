"""Behavioral tests for KC_dependent_vars — Grade-6 Unit 4/5 (CCSS 6.EE.9 / TEKS 6.6A/6.6B).

Use variables to represent two quantities that change in relationship, write the equation, and
analyze the dependent vs. independent variable. The gradeable form anchors on a relationship
equation ``y = a*x``: given the INDEPENDENT value x, find the DEPENDENT value y. This KC offers
TWO REAL live surfaces answered from the SAME relationship, so it is MASTERABLE (the §3.4 rule-2
representation-diversity gate is reachable live, like KC_evaluate_expressions):

  - SYMBOLIC (default) — the scalar dependent value y, entered in the NUMBER_ENTRY editor
    ("y = 3x. What is y when x = 4?" -> "12"); graded NUMERIC by SymPy substitute-and-evaluate.
  - COORDINATE_PLANE — plot the point (x, y) that satisfies the relationship for the given x
    ("y = 3x. Plot the point (x, y) when x = 4." -> "(4,12)"); REUSES the live coordinate widget
    and the existing order-insensitive coordinate verifier.

Every assertion runs through the SAME oracle the tutor uses (the SymPy verifier), so "correct" /
"wrong" means exactly what it does in production (ARCHITECTURE.md §9). SymPy/domain decides — never
an LLM (CLAUDE.md §8.2). Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.lesson_spec import WidgetId, widget_for_representation
from app.domain.misconceptions import (
    MisconceptionId,
    add_instead_of_applying_rate,
    swap_coordinates,
)
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import is_masterable_live, live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.DEPENDENT_VARS


def _problem(seed: int, surface: Representation | None = None) -> Problem:
    return generate_problem(_KC, seed, surface)


def test_dependent_vars_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it — and so u4_l6
    ("Independent & dependent variables") and u5_l5 ("Two-variable relationships") go live."""
    assert _KC in LIVE_KCS


def test_symbolic_item_is_a_clean_scalar_substitution() -> None:
    """The SYMBOLIC surface yields a NUMERIC item with (a, x) operands; answer = a*x.

    a >= 2 and x >= 2 (with the single a == x == 2 case excluded), so the additive-confusion
    slip a + x always differs from the multiplicative answer a*x — keeping it diagnostic.
    """
    problem = _problem(7, Representation.SYMBOLIC)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.surface_format is Representation.SYMBOLIC
    assert problem.operands is not None and len(problem.operands) == 2
    a, x = problem.operands
    assert a >= 2 and x >= 2
    assert all(operand.q == 1 for operand in problem.operands)  # whole-number operands
    assert problem.correct_value == a * x


def test_symbolic_routes_to_number_entry_not_fraction_editor() -> None:
    """A scalar-answer KC: the SYMBOLIC surface uses the single-box NUMBER_ENTRY (not the two-box
    fraction editor) — this routes the answer to NUMBER_ENTRY per the widget contract."""
    assert widget_for_representation(Representation.SYMBOLIC, _KC) is WidgetId.NUMBER_ENTRY


def test_correct_dependent_value_verifies_correct() -> None:
    """The substitute-and-evaluate value (a*x) is graded correct by the tutor's own oracle."""
    for seed in range(1, 25):
        problem = _problem(seed, Representation.SYMBOLIC)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_dependent_independent_swap_is_classified() -> None:
    """The additive-confusion value (a + x, treating the multiplicative rule as additive) is
    flagged OPERATION + the dependent-independent-swap misconception — the wrong PROCEDURE the
    lesson is designed to surface. The slip a + x is always DISTINCT from the correct a*x."""
    for seed in range(1, 25):
        problem = _problem(seed, Representation.SYMBOLIC)
        assert problem.operands is not None
        a, x = problem.operands
        wrong = add_instead_of_applying_rate(int(a), int(x))
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.DEPENDENT_INDEPENDENT_SWAP


def test_coordinate_item_plots_the_satisfying_point() -> None:
    """The COORDINATE_PLANE surface yields a COORDINATE item: plot the (x, y) on the relationship.

    The canonical answer is "(x,y)" with y = a*x, graded by the existing order-insensitive
    coordinate verifier, and rendered by the live coordinate-plane widget."""
    for seed in range(1, 25):
        problem = _problem(seed, Representation.COORDINATE_PLANE)
        assert problem.answer_kind is AnswerKind.COORDINATE
        assert problem.surface_format is Representation.COORDINATE_PLANE
        assert problem.correct_points is not None and problem.correct_points.strip()
        # The plotted point is (x, a*x): the dependent value sits at the given independent value.
        assert problem.operands is not None
        a, x = (int(op) for op in problem.operands)
        assert problem.correct_points == f"({x},{a * x})"
        result = verify(problem, problem.correct_points)
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_coordinate_swap_on_the_plotted_point_is_classified() -> None:
    """On the COORDINATE surface, transposing the point ((x,y) plotted as (y,x)) is flagged
    OPERATION + coordinate-swap (when genuinely wrong) — the axis-order confusion the verifier
    already models for coordinate answers."""
    for seed in range(1, 40):
        problem = _problem(seed, Representation.COORDINATE_PLANE)
        wrong = swap_coordinates(problem.correct_points)
        if wrong is None:
            continue  # x == y (a == 1 would do it, but a >= 2 here only at x small); skip
        result = verify(problem, wrong)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.COORDINATE_SWAP


def test_two_live_surfaces_share_the_same_relationship() -> None:
    """SYMBOLIC and COORDINATE_PLANE are BOTH live and built from the SAME (a, x) relationship,
    so the KC is masterable (§3.4 rule 2 reachable live). The symbolic answer is the dependent
    value a*x; the coordinate answer is the point (x, a*x) — the same relationship, two surfaces."""
    assert set(live_representations(_KC)) == {
        Representation.SYMBOLIC,
        Representation.COORDINATE_PLANE,
    }
    assert is_masterable_live(_KC)
    for seed in range(1, 25):
        symbolic = _problem(seed, Representation.SYMBOLIC)
        coordinate = _problem(seed, Representation.COORDINATE_PLANE)
        assert symbolic.operands == coordinate.operands  # same relationship + independent value
        a, x = (int(op) for op in symbolic.operands)  # type: ignore[union-attr]
        assert symbolic.correct_value == a * x
        assert coordinate.correct_points == f"({x},{a * x})"
        assert symbolic.statement != coordinate.statement  # genuinely different framing
        assert verify(symbolic, str(symbolic.correct_value)).is_correct
        assert verify(coordinate, coordinate.correct_points).is_correct


def test_unparseable_submissions_are_wrong_not_a_crash() -> None:
    """Garbled input grades wrong on both surfaces, never raises (CLAUDE.md §8.2)."""
    symbolic = _problem(1, Representation.SYMBOLIC)
    for junk in ("", "abc", "y", "/"):
        result = verify(symbolic, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER
    coordinate = _problem(1, Representation.COORDINATE_PLANE)
    for junk in ("", "(", "(a,b)", "2,3"):
        result = verify(coordinate, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER


def test_generation_is_deterministic() -> None:
    """Same seed (and surface) => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    first = generate_problem(_KC, 42, Representation.COORDINATE_PLANE)
    second = generate_problem(_KC, 42, Representation.COORDINATE_PLANE)
    assert first.correct_points == second.correct_points


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example is self-consistent on both surfaces: the symbolic example's final value
    equals correct_value; the coordinate example's last step shows the canonical point."""
    symbolic = _problem(3, Representation.SYMBOLIC)
    assert worked_example_for(symbolic).final_value == symbolic.correct_value
    coordinate = _problem(3, Representation.COORDINATE_PLANE)
    assert coordinate.correct_points is not None
    assert coordinate.correct_points in worked_example_for(coordinate).steps[-1].shown


def test_nudge_bank_covers_dependent_vars() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
