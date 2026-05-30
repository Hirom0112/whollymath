"""Behavioral tests for KC_equivalent_expressions — Grade-6 Unit 4 (6.EE.3 / 6.EE.4).

This KC REUSES the expression-answer contract established by KC_write_expressions
(answer_kind="expression", widget_id="expression", graded by SymPy EQUIVALENCE — see
test_write_expressions.py). It is the SECOND expression-answer KC: the learner is shown a
GIVEN expression and must type an EQUIVALENT one — expand a product like ``3(x + 2)`` into
``3x + 6``, or combine like terms like ``2x + 5x`` into ``7x``. Grading is by equivalence, so
any algebraically equal form is correct.

The named misconception is the DISTRIBUTIVE ERROR (6.EE.3): distributing the multiplier onto
only the first term — ``3(x + 2) -> 3x + 2`` — flagged OPERATION + distributive-error, but
ONLY when it is genuinely wrong (it is harmless on a single-term product, where the verifier
never flags a still-correct form).

Pins (all through the SAME oracle the tutor uses): the generator emits an expression item
carrying the canonical answer in ``correct_expression`` and the GIVEN expression in
``source_expression``; the verifier grades an equivalent answer correct and an inequivalent
one wrong; the distributive-error answer is flagged OPERATION; unparseable input is wrong, not
a crash; the worked example lands on the canonical expression; generation is deterministic.
Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, distributive_error
from app.domain.problem_generators import AnswerKind, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.EQUIVALENT_EXPRESSIONS


def _problem(seed: int):  # type: ignore[no-untyped-def]
    return generate_problem(_KC, seed)


def test_equivalent_expressions_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_problem_is_an_expression_item() -> None:
    """An EXPRESSION item: the surface is EXPRESSION, the answer is in correct_expression, and
    the GIVEN expression to transform is carried in source_expression."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.EXPRESSION
    assert problem.surface_format is Representation.EXPRESSION
    assert problem.correct_expression is not None and problem.correct_expression.strip()
    assert problem.source_expression is not None and problem.source_expression.strip()
    assert problem.statement


def test_canonical_expression_verifies_correct() -> None:
    """Submitting the canonical answer is graded correct by the tutor's own oracle."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.correct_expression is not None
        result = verify(problem, problem.correct_expression)
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_source_expression_is_equivalent_to_the_answer() -> None:
    """Self-consistency: the GIVEN expression and the canonical answer are algebraically equal —
    the learner is asked to REWRITE, not to change the value (submitting the source is correct)."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.source_expression is not None
        # The unsimplified source IS an equivalent expression, so it grades correct too.
        assert verify(problem, problem.source_expression).is_correct


def test_equivalent_but_reordered_expression_is_correct() -> None:
    """Grading is by SymPy EQUIVALENCE, not string match: a commuted/again-equal form is correct.

    Wrapping the canonical answer in a SymPy-equal rephrasing (add 0) must still grade correct —
    that is the whole point of the equivalence path (3x+6 ≡ 6+3x ≡ 3x+6+0)."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.correct_expression is not None
        equivalent = f"({problem.correct_expression}) + 0"
        assert verify(problem, equivalent).is_correct


def test_distributive_error_misconception_is_classified() -> None:
    """The distributive-error answer (e.g. 3x+2 for 3(x+2), which is 3x+6) is flagged OPERATION +
    distributive-error — the misconception the lesson is designed to surface, when genuinely
    wrong. On a problem whose distributive error happens to be equivalent (single-term product),
    the function returns None and we skip — the verifier must never flag a still-correct form."""
    saw_at_least_one = False
    for seed in range(1, 60):
        problem = _problem(seed)
        wrong = distributive_error(problem.source_expression)
        if wrong is None:
            continue
        result = verify(problem, wrong)
        # Skip the (rare) case where the "error" form is coincidentally still equivalent.
        if result.is_correct:
            continue
        saw_at_least_one = True
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.DISTRIBUTIVE_ERROR
    assert saw_at_least_one, "expected at least one genuinely-wrong distributive-error case"


def test_unparseable_submission_is_wrong_not_a_crash() -> None:
    """A garbled expression grades wrong (OTHER), never raises — the verifier must not crash on
    what a kid types (CLAUDE.md §8.2)."""
    problem = _problem(1)
    for junk in ("", "x +", ")(", "= = =", "x x x"):
        result = verify(problem, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    first, second = generate_problem(_KC, 42), generate_problem(_KC, 42)
    assert first.statement == second.statement
    assert first.correct_expression == second.correct_expression
    assert first.source_expression == second.source_expression


def test_worked_example_lands_on_the_expression() -> None:
    """The worked example's final step shows the canonical expression (self-consistency)."""
    for seed in (3, 8, 15):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert problem.correct_expression is not None
        assert problem.correct_expression in example.steps[-1].shown


def test_nudge_bank_covers_equivalent_expressions() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_distributive_error_function_is_none_on_a_non_product() -> None:
    """The misconception is defined only for a distributable product a*(b + c). A source with no
    such structure (e.g. a like-terms sum '2*x + 5*x') has no distributive-error form, so the
    function returns None — the verifier never fabricates a wrong-but-still-equivalent match."""
    assert distributive_error("2*x + 5*x") is None
    assert distributive_error(None) is None
