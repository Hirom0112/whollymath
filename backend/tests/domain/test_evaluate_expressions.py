"""Behavioral tests for KC_evaluate_expressions — a Grade-6 (Unit 4) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope "evaluate a*x + b at x" item; the verifier confirms the
correct value and classifies the order-of-operations slip (adding before multiplying); the
worked example lands on the answer; generation is deterministic (PROJECT.md §4.1); and the KC is
MASTERABLE — it offers two REAL live surfaces (SYMBOLIC + AREA_MODEL) answered with the same
numeric value, so the §3.4 rule-2 representation-diversity gate is reachable live. Mandatory-TDD
domain Layer 1 (CLAUDE.md §2). Skill: 6.EE.2c — evaluate an expression at a given value.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, evaluate_left_to_right
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import is_masterable_live, live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.EVALUATE_EXPRESSIONS


def _problem(seed: int, surface: Representation | None = None) -> Problem:
    return generate_problem(_KC, seed, surface)


def test_evaluate_expressions_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_expression_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with (a, x, b) operands; answer = a*x + b.

    The coefficient a >= 2 and constant b >= 1, so multiply-first (a*x + b) differs from the
    left-to-right slip a*(x + b) — keeping the misconception diagnostic.
    """
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 3
    a, x, b = problem.operands
    assert a >= 2 and b >= 1
    assert all(operand.q == 1 for operand in problem.operands)  # whole-number operands
    assert problem.correct_value == a * x + b


def test_correct_value_verifies_correct() -> None:
    """The multiply-first value (a*x + b) is graded correct by the tutor's own oracle."""
    for seed in range(1, 16):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_order_of_operations_slip_is_classified() -> None:
    """The left-to-right value a*(x + b) is flagged OPERATION + the order-of-ops misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — added before
    multiplying (combined left-to-right) instead of honoring precedence. The slip value a*(x + b)
    is always DISTINCT from the correct a*x + b because a >= 2 and b >= 1 (so a*b != b).
    """
    for seed in range(1, 16):
        problem = _problem(seed)
        assert problem.operands is not None
        a, x, b = problem.operands
        wrong = evaluate_left_to_right(int(a), int(x), int(b))
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.ORDER_OF_OPERATIONS_SLIP


def test_two_live_surfaces_share_the_same_numeric_answer() -> None:
    """SYMBOLIC and AREA_MODEL are BOTH live and answered with the same value (masterable).

    The two surfaces reframe the SAME a*x + b item (the area/array picture vs. the symbolic
    expression); the operands and correct value are identical, only the statement differs. This
    is the representation-agnostic answer that makes §3.4 rule 2 reachable live.
    """
    assert set(live_representations(_KC)) == {Representation.SYMBOLIC, Representation.AREA_MODEL}
    assert is_masterable_live(_KC)
    for seed in range(1, 16):
        symbolic = _problem(seed, Representation.SYMBOLIC)
        area = _problem(seed, Representation.AREA_MODEL)
        assert symbolic.operands == area.operands
        assert symbolic.correct_value == area.correct_value
        assert symbolic.statement != area.statement  # genuinely different framing
        for problem in (symbolic, area):
            assert verify(problem, str(problem.correct_value)).is_correct


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_evaluate_expressions() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
