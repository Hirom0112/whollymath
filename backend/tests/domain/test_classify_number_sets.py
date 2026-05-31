"""Behavioral tests for KC_classify_number_sets — Grade-6 (TEKS 6.2A), the number-set classifier.

This KC introduces a NEW answer kind whose answer is neither a numeric magnitude nor an algebraic
expression: a SET of number-system labels (natural ⊂ whole ⊂ integer ⊂ rational) the given number
belongs to. The frozen widget contract (matches the frontend ClassifySets widget exactly):

    widget_id = "classify_sets"
    answer string = a comma-separated canonical list ordered SMALL set → LARGE set,
                    e.g. "integer,rational" or "natural,whole,integer,rational".

Grading is by ORDER-INSENSITIVE SET comparison in the domain verifier: the SET of chosen labels
against the correct membership for the given number (-3 → {integer, rational}; 5 → {natural, whole,
integer, rational}; 1/2 → {rational}). Unknown/unparseable labels grade wrong, never crash
(CLAUDE.md §8.2). No LLM decides membership — a fixed domain label vocabulary + SymPy on the value.

Pins (all through the SAME oracle the tutor uses, ARCHITECTURE.md §9): the generator emits a
classify item carrying the canonical membership string; the verifier grades the correct membership
right (any order) and a wrong membership wrong; the "an integer isn't rational" misconception
(dropping ``rational`` from an integer's set) is flagged CONCEPTUAL; garbage labels grade wrong, not
a crash; the worked example lands on the canonical set; generation is deterministic. Mandatory-TDD
domain Layer 1 (CLAUDE.md §2). Skill: TEKS 6.2A — classify whole/integer/rational number sets.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.lesson_spec import WidgetId, widget_for_representation
from app.domain.misconceptions import (
    NUMBER_SET_LABELS,
    MisconceptionId,
    classify_sets_for_value,
    omit_rational_for_integer,
)
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.CLASSIFY_NUMBER_SETS


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_classify_number_sets_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_answer_kind_has_number_sets_member() -> None:
    """The wire contract: AnswerKind gains NUMBER_SETS (value 'number_sets')."""
    assert AnswerKind.NUMBER_SETS.value == "number_sets"


def test_widget_id_for_number_sets_is_the_frozen_literal() -> None:
    """The FROZEN widget contract: the NUMBER_SETS representation maps to widget_id 'classify_sets'
    (frontend selectWidget routes widget_id==='classify_sets' → the ClassifySets widget)."""
    assert widget_for_representation(Representation.NUMBER_SETS) is WidgetId.CLASSIFY_SETS
    assert WidgetId.CLASSIFY_SETS.value == "classify_sets"


def test_label_vocabulary_is_the_fixed_small_to_large_order() -> None:
    """The canonical label vocabulary is fixed and ordered small set → large set (a domain
    constant, no LLM): natural ⊂ whole ⊂ integer ⊂ rational."""
    assert NUMBER_SET_LABELS == ("natural", "whole", "integer", "rational")


def test_membership_is_correct_for_representative_values() -> None:
    """The pure membership function returns the right ordered set for known values.

    The nested-subset rule (TEKS 6.2A): every natural is whole is integer is rational; a negative
    integer is integer+rational but NOT whole/natural; a non-integer rational is rational only.
    """
    assert classify_sets_for_value(Rational(5)) == ("natural", "whole", "integer", "rational")
    assert classify_sets_for_value(Rational(0)) == ("whole", "integer", "rational")
    assert classify_sets_for_value(Rational(-3)) == ("integer", "rational")
    assert classify_sets_for_value(Rational(1, 2)) == ("rational",)
    assert classify_sets_for_value(Rational(-7, 4)) == ("rational",)


def test_generated_problem_is_a_number_sets_item() -> None:
    """A NUMBER_SETS item: the surface is NUMBER_SETS, the answer is the canonical set string."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMBER_SETS
    assert problem.surface_format is Representation.NUMBER_SETS
    assert problem.correct_sets is not None and problem.correct_sets.strip()
    # The canonical answer is a comma-separated subset of the vocabulary, in small→large order.
    labels = problem.correct_sets.split(",")
    assert all(label in NUMBER_SET_LABELS for label in labels)
    assert labels == [lab for lab in NUMBER_SET_LABELS if lab in labels]  # ordered
    assert problem.statement


def test_canonical_membership_verifies_correct() -> None:
    """Submitting the canonical membership is graded correct by the tutor's own oracle."""
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.correct_sets is not None
        result = verify(problem, problem.correct_sets)
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_grading_is_order_insensitive() -> None:
    """Grading is by SET, not string order: the labels in any order grade correct."""
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.correct_sets is not None
        reordered = ",".join(reversed(problem.correct_sets.split(",")))
        assert verify(problem, reordered).is_correct
        # Whitespace and duplicate labels are tolerated (set semantics).
        padded = (
            ", ".join(problem.correct_sets.split(",")) + "," + problem.correct_sets.split(",")[0]
        )
        assert verify(problem, padded).is_correct


def test_wrong_membership_is_wrong() -> None:
    """A genuinely different set (an extra or missing label) grades wrong."""
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.correct_sets is not None
        labels = problem.correct_sets.split(",")
        # Drop one label if there is more than one (always a different set); else add 'natural'.
        if len(labels) > 1:
            wrong = ",".join(labels[:-1])
        else:
            wrong = problem.correct_sets + ",natural"
        # Skip if the perturbation happened to land on the same set (it won't here, but guard).
        if set(wrong.split(",")) == set(labels):
            continue
        result = verify(problem, wrong)
        assert not result.is_correct


def test_integer_not_rational_misconception_is_classified() -> None:
    """Dropping 'rational' from an INTEGER's set (not realizing every integer is rational) is the
    integer-not-rational misconception → CONCEPTUAL (OPERATION routing key), when it is genuinely
    wrong (i.e. the value actually is an integer, so 'rational' belonged in the answer)."""
    seen = 0
    for seed in range(1, 60):
        problem = _problem(seed)
        wrong = omit_rational_for_integer(problem.correct_sets)
        if wrong is None:
            continue  # value is not an integer — the misconception does not apply
        seen += 1
        result = verify(problem, wrong)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.INTEGER_NOT_RATIONAL
    assert seen >= 1, "no integer-valued classify item produced in the seed range"


def test_unparseable_submission_is_wrong_not_a_crash() -> None:
    """A garbled / unknown-label answer grades wrong (OTHER), never raises (CLAUDE.md §8.2)."""
    problem = _problem(1)
    for junk in ("", "   ", "prime,even", "natural;whole", "42", ",,,", "rationalish"):
        result = verify(problem, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER


def test_both_integer_and_non_integer_items_are_generated() -> None:
    """Across seeds the generated number is sometimes an integer (rational membership matters) and
    sometimes a non-integer fraction (rational-only) — the lesson covers both."""
    has_integer = False
    has_fraction = False
    for seed in range(1, 60):
        problem = _problem(seed)
        assert problem.operands is not None
        value = problem.operands[0]
        if value.q == 1:
            has_integer = True
        else:
            has_fraction = True
    assert has_integer and has_fraction


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    first, second = generate_problem(_KC, 42), generate_problem(_KC, 42)
    assert first.correct_sets == second.correct_sets


def test_worked_example_lands_on_the_canonical_set() -> None:
    """The worked example's final step shows the canonical membership (self-consistency)."""
    for seed in (3, 8, 11):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert problem.correct_sets is not None
        # The final shown step names the canonical set (the example's answer).
        for label in problem.correct_sets.split(","):
            assert label in example.steps[-1].shown


def test_nudge_bank_covers_classify_number_sets() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
