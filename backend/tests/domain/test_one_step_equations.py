"""Behavioral tests for KC_one_step_equations — a Grade-6 (Unit 5) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). ONE KC
covers BOTH additive equations ``x + b = c`` and multiplicative equations ``a*x = c`` behind
an operand-mode flag, and ONE misconception — the inverse-operation error (applying the WRONG
inverse: adding instead of subtracting for ``x + b = c``, or subtracting ``a`` instead of
dividing for ``a*x = c``). Pins: the generator builds a clean, in-scope solve-for-x item with a
whole-number answer in BOTH modes and BOTH live representations (SYMBOLIC + the WORD_PROBLEM
story framing); the verifier confirms the correct solution and classifies the inverse-operation
misconception; the worked example lands on the answer; and generation is deterministic
(PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: 6.EE.7 — solve one-step
equations of the form ``x + p = q`` and ``px = q``.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, inverse_operation_error
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import is_masterable_live, live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.ONE_STEP_EQUATIONS
_ADDITIVE = Rational(0)
_MULTIPLICATIVE = Rational(1)


def _problem(seed: int, surface_format: Representation | None = None) -> Problem:
    return generate_problem(_KC, seed, surface_format)


def test_one_step_equations_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_item_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric solve-for-x item with a (mode, p, q) operand triple.

    The answer is a whole number (6th-grade scope), and the mode flag selects additive vs
    multiplicative — both produced across seeds (covered separately below).
    """
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 3
    mode, p, q = problem.operands
    assert mode in (_ADDITIVE, _MULTIPLICATIVE)
    assert p != 0
    assert problem.correct_value.q == 1  # a whole-number solution
    if mode == _ADDITIVE:
        assert problem.correct_value == q - p  # x = c - b
    else:
        assert problem.correct_value == q / p  # x = c / a


def test_both_modes_are_generated() -> None:
    """Across seeds the KC produces BOTH additive and multiplicative equations (two modes)."""
    modes = {_problem(s).operands[0] for s in range(1, 40)}  # type: ignore[index]
    assert modes == {_ADDITIVE, _MULTIPLICATIVE}


def test_correct_solution_verifies_correct() -> None:
    """The correct value of x is graded correct by the tutor's own oracle, in both modes."""
    for seed in range(1, 30):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_inverse_operation_error_is_classified() -> None:
    """Applying the wrong inverse is flagged OPERATION + the inverse-operation misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — undid the
    equation with the wrong inverse. For ``x + b = c`` they ADD b (``c + b``) instead of
    subtracting; for ``a*x = c`` they SUBTRACT a (``c - a``) instead of dividing. The generator
    guarantees this wrong value is DISTINCT from the correct one, so the misconception is always
    diagnostic.
    """
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.operands is not None
        wrong = inverse_operation_error(problem.operands)
        assert wrong is not None
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.INVERSE_OPERATION_ERROR


def test_inverse_error_is_classified_in_the_word_problem_surface() -> None:
    """The same numeric inverse-operation error is classified on the WORD_PROBLEM surface too.

    Both live representations answer with the value of x and carry the same operand triple, so the
    diagnostic does not depend on which surface posed the equation (mastery rule 2 / HR.A2).
    """
    for seed in range(1, 30):
        problem = _problem(seed, Representation.WORD_PROBLEM)
        assert problem.surface_format is Representation.WORD_PROBLEM
        assert problem.operands is not None
        wrong = inverse_operation_error(problem.operands)
        assert wrong is not None
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.INVERSE_OPERATION_ERROR


def test_two_live_representations_make_it_masterable() -> None:
    """SYMBOLIC + WORD_PROBLEM are both live, so a learner can be correct in 2 representations.

    This is the first Grade-6 KC built masterable-live (≥2 live representations satisfies mastery
    rule 2 and the within-skill varied-practice path of rule 4)."""
    assert set(live_representations(_KC)) == {
        Representation.SYMBOLIC,
        Representation.WORD_PROBLEM,
    }
    assert is_masterable_live(_KC) is True


def test_correct_solution_verifies_correct_in_both_surfaces() -> None:
    """The same seed solved in either surface grades correct against the same operands."""
    for seed in range(1, 20):
        symbolic = _problem(seed, Representation.SYMBOLIC)
        word = _problem(seed, Representation.WORD_PROBLEM)
        assert symbolic.correct_value == word.correct_value  # same math, two framings
        assert verify(word, str(word.correct_value)).is_correct


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in range(1, 20):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_one_step_equations() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
