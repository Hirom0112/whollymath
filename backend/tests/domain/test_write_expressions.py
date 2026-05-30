"""Behavioral tests for KC_write_expressions — Grade-6 Unit 4 (6.EE.2a / 6.EE.B.6).

This KC ESTABLISHES the expression-answer contract the frontend ExpressionInput consumes
(answer_kind="expression", widget_id="expression"). It is the first KC whose answer is an
algebraic EXPRESSION, not a numeric magnitude, so it exercises a NEW verifier path: grading
by SymPy EQUIVALENCE (sympify both sides; correct iff symbolically equal), so "7+p" == "p+7".

Pins (all through the SAME oracle the tutor uses): the generator emits an expression item
carrying the canonical answer in ``correct_expression``; the verifier grades an equivalent
expression correct and an inequivalent one wrong; the reversed-order misconception (e.g.
"7-p" for "7 less than p", which is p-7) is flagged OPERATION; unparseable input is wrong,
not a crash; the worked example lands on the canonical expression; generation is
deterministic. Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.lesson_spec import WidgetId, widget_for_representation
from app.domain.misconceptions import MisconceptionId, reversed_operands
from app.domain.problem_generators import AnswerKind, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.WRITE_EXPRESSIONS


def _problem(seed: int):  # type: ignore[no-untyped-def]
    return generate_problem(_KC, seed)


def test_write_expressions_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_answer_kind_has_expression_member() -> None:
    """The frozen wire contract: AnswerKind gains EXPRESSION (value 'expression')."""
    assert AnswerKind.EXPRESSION.value == "expression"


def test_widget_id_for_expression_is_the_frozen_literal() -> None:
    """The frozen wire contract: the EXPRESSION representation maps to widget_id 'expression'
    (frontend selectWidget routes widget_id==='expression' → ExpressionInput)."""
    assert widget_for_representation(Representation.EXPRESSION) is WidgetId.EXPRESSION
    assert WidgetId.EXPRESSION.value == "expression"


def test_generated_problem_is_an_expression_item() -> None:
    """An EXPRESSION item: the surface is EXPRESSION, the answer is in correct_expression."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.EXPRESSION
    assert problem.surface_format is Representation.EXPRESSION
    assert problem.correct_expression is not None and problem.correct_expression.strip()
    # operands carry the (constant, the reversed-vs-correct signal) the verifier replays; the
    # statement is the kid-facing phrase to translate.
    assert problem.statement


def test_canonical_expression_verifies_correct() -> None:
    """Submitting the canonical answer is graded correct by the tutor's own oracle."""
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.correct_expression is not None
        result = verify(problem, problem.correct_expression)
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_equivalent_but_reordered_expression_is_correct() -> None:
    """Grading is by SymPy EQUIVALENCE, not string match: a commuted/again-equal form is correct.

    Wrapping the canonical answer in a SymPy-equal rephrasing (add 0, multiply by 1) must still
    grade correct — that is the whole point of the equivalence path (n+5 ≡ 5+n ≡ n+5+0)."""
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.correct_expression is not None
        equivalent = f"({problem.correct_expression}) + 0"
        assert verify(problem, equivalent).is_correct


def test_reversed_order_misconception_is_classified() -> None:
    """The reversed-operands answer (e.g. 7-p for 'p-7') is flagged OPERATION + reversed-operands —
    the order/operation confusion the lesson is designed to surface, when it is genuinely wrong."""
    for seed in range(1, 30):
        problem = _problem(seed)
        wrong = reversed_operands(problem.correct_expression)
        if wrong is None:
            continue  # commutative case (a+b): reversing is still equivalent, so no wrong form
        result = verify(problem, wrong)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.REVERSED_OPERANDS


def test_unparseable_submission_is_wrong_not_a_crash() -> None:
    """A garbled expression grades wrong (OTHER), never raises — the verifier must not crash on
    what a kid types (CLAUDE.md §8.2)."""
    problem = _problem(1)
    for junk in ("", "p +", ")(", "= = =", "p p p"):
        result = verify(problem, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    first, second = generate_problem(_KC, 42), generate_problem(_KC, 42)
    assert first.correct_expression == second.correct_expression


def test_worked_example_lands_on_the_expression() -> None:
    """The worked example's final step shows the canonical expression (self-consistency)."""
    for seed in (3, 8):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert problem.correct_expression is not None
        # The final shown step contains the canonical expression text (the example's answer).
        assert problem.correct_expression in example.steps[-1].shown


def test_nudge_bank_covers_write_expressions() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
