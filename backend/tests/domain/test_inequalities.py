"""Behavioral tests for KC_inequalities — Grade-6 Unit 5 (6.EE.8).

Write an inequality of the form ``x OP c`` (>, >=, <, <=) that represents a real-world
constraint: "a number is at least 5" -> ``x>=5``; "you must be under 13" -> ``x<13``. This
KC adds a NEW answer kind (``inequality``) and a NEW Representation (``INEQUALITY``) following
the EXPRESSION precedent — its answer is a typed relational STRING, not a magnitude, so it
exercises a NEW verifier path: grading by relational EQUIVALENCE (sympify the relational,
canonicalize variable/direction/bound; correct iff the same solution set), so ``x>=5`` ==
``5<=x``. Both ``>=``/``<=`` ASCII forms parse.

Pins (all through the SAME oracle the tutor uses): the generator emits an inequality item
carrying the canonical answer in ``correct_inequality``; the verifier grades an equivalent
relational correct and an inequivalent one wrong; the FLIPPED-direction misconception (e.g.
``x<5`` for "at least 5", which is ``x>=5``) is flagged OPERATION; unparseable / non-relational
input is wrong, not a crash; the worked example lands on the canonical inequality; generation is
deterministic. Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.lesson_spec import WidgetId, widget_for_representation
from app.domain.misconceptions import MisconceptionId, flipped_inequality
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.INEQUALITIES


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_inequalities_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_answer_kind_has_inequality_member() -> None:
    """The frozen wire contract: AnswerKind gains INEQUALITY (value 'inequality')."""
    assert AnswerKind.INEQUALITY.value == "inequality"


def test_widget_id_for_inequality_is_the_frozen_literal() -> None:
    """The frozen wire contract: the INEQUALITY representation maps to widget_id 'inequality'
    (the frontend routes widget_id==='inequality' to the inequality input)."""
    assert widget_for_representation(Representation.INEQUALITY) is WidgetId.INEQUALITY
    assert WidgetId.INEQUALITY.value == "inequality"


def test_generated_problem_is_an_inequality_item() -> None:
    """An INEQUALITY item: the surface is INEQUALITY, the answer is in correct_inequality."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.INEQUALITY
    assert problem.surface_format is Representation.INEQUALITY
    assert problem.correct_inequality is not None and problem.correct_inequality.strip()
    assert problem.statement


def test_canonical_inequality_verifies_correct() -> None:
    """Submitting the canonical answer is graded correct by the tutor's own oracle."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.correct_inequality is not None
        result = verify(problem, problem.correct_inequality)
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_equivalent_but_reordered_inequality_is_correct() -> None:
    """Grading is by relational EQUIVALENCE, not string match: the flipped-operand form with the
    same solution set is correct (x>=5 has the same meaning as 5<=x)."""
    # canonical OP -> the equivalent form with the variable on the RIGHT (operator mirrored).
    mirror = {">": "<", ">=": "<=", "<": ">", "<=": ">="}
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.correct_inequality is not None
        canon = problem.correct_inequality
        for op, mir in mirror.items():
            # find the (longest) operator present so ">=" isn't matched as ">".
            if op in (">=", "<="):
                if op in canon:
                    var, bound = canon.split(op)
                    equivalent = f"{bound}{mir}{var}"
                    assert verify(problem, equivalent).is_correct
                    break
        else:
            for op in (">", "<"):
                if op in canon:
                    var, bound = canon.split(op)
                    equivalent = f"{bound}{mirror[op]}{var}"
                    assert verify(problem, equivalent).is_correct
                    break


def test_flipped_direction_misconception_is_classified() -> None:
    """The flipped-direction answer (e.g. x<5 for "at least 5", which is x>=5) is flagged
    OPERATION + flipped-inequality — the direction confusion the lesson is designed to surface."""
    for seed in range(1, 40):
        problem = _problem(seed)
        wrong = flipped_inequality(problem.correct_inequality)
        assert wrong is not None  # every inequality has a well-defined flipped form
        result = verify(problem, wrong)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.FLIPPED_INEQUALITY


def test_strict_vs_nonstrict_is_not_equivalent() -> None:
    """x>3 and x>=3 are DIFFERENT solution sets — a strict/non-strict swap grades wrong."""
    for seed in range(1, 40):
        problem = _problem(seed)
        canon = problem.correct_inequality
        assert canon is not None
        # Build the same-direction-but-strictness-swapped form.
        if ">=" in canon:
            swapped = canon.replace(">=", ">")
        elif "<=" in canon:
            swapped = canon.replace("<=", "<")
        elif ">" in canon:
            swapped = canon.replace(">", ">=")
        else:
            swapped = canon.replace("<", "<=")
        assert not verify(problem, swapped).is_correct


def test_unparseable_or_non_relational_submission_is_wrong_not_a_crash() -> None:
    """A garbled OR a non-relational (plain expression) submission grades wrong (OTHER), never
    raises — the verifier must not crash on what a kid types (CLAUDE.md §8.2)."""
    problem = _problem(1)
    for junk in ("", "x >", ")(", "= = =", "x x x", "x + 3", "5", "x = 3"):
        result = verify(problem, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    first, second = generate_problem(_KC, 42), generate_problem(_KC, 42)
    assert first.correct_inequality == second.correct_inequality


def test_worked_example_lands_on_the_inequality() -> None:
    """The worked example's final step shows the canonical inequality (self-consistency)."""
    for seed in (3, 8, 15):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert problem.correct_inequality is not None
        assert problem.correct_inequality in example.steps[-1].shown


def test_nudge_bank_covers_inequalities() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_flipped_inequality_helper_handles_all_directions() -> None:
    """The misconception helper mirrors direction while KEEPING the bound (the wrong-direction
    error), for every operator, and returns None on non-relational input (never crashes)."""
    assert flipped_inequality("x>=5") == "x <= 5"
    assert flipped_inequality("x<13") == "x > 13"
    assert flipped_inequality("x>3") == "x < 3"
    assert flipped_inequality("x<=7") == "x >= 7"
    assert flipped_inequality(None) is None
    assert flipped_inequality("x + 3") is None  # not a relational
    assert flipped_inequality("garbage)(") is None  # unparseable
