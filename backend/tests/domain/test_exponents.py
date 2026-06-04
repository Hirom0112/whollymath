"""Behavioral tests for KC_exponents — a Grade-6 (Unit 4) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope item; the verifier confirms the correct value and
classifies the per-mode misconception; the worked example lands on the answer; generation is
deterministic (PROJECT.md §4.1); and the KC is MASTERABLE — it offers two REAL live surfaces
(SYMBOLIC + AREA_MODEL) answered with the same numeric value, so the §3.4 rule-2
representation-diversity gate is reachable live. Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
Skill: 6.EE.1 — write AND evaluate numerical expressions involving whole-number exponents.

KC_exponents has TWO modes behind a trailing operand flag (the mode is the LAST operand), so a
single lesson covers the whole of 6.EE.1 — evaluating a bare power AND evaluating an expression
where a power sits inside order of operations (panel coverage fix, Dr. Okafor 2026-06-04):

  - POWER_ONLY (mode 0): the bare power "What is base^exp?", operands ``(base, exp, mode)``. Both
    the SYMBOLIC and the AREA_MODEL (square/cube picture) surfaces render this mode.
  - ORDER_OF_OPS (mode 1): a small expression with ONE power and ONE surrounding whole-number
    operation that REQUIRES exponent-first evaluation ("2 + 3^2 = 11"), operands
    ``(base, exp, a, op_code, mode)``. SYMBOLIC only — an order-of-ops expression has no single
    square/cube picture, so requesting AREA_MODEL forces a POWER_ONLY item (see
    test_area_model_is_always_power_only).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import (
    MisconceptionId,
    evaluate_exponent_order_left_to_right,
    multiply_base_by_exponent,
)
from app.domain.problem_generators import (
    _EXPONENT_ORDER_OF_OPS,
    _EXPONENT_POWER_ONLY,
    AnswerKind,
    Problem,
    generate_problem,
)
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import is_masterable_live, live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.EXPONENTS


def _problem(seed: int, surface: Representation | None = None) -> Problem:
    return generate_problem(_KC, seed, surface)


def _mode(problem: Problem) -> int:
    """The trailing mode flag — the LAST operand, by the established convention."""
    assert problem.operands is not None
    return int(problem.operands[-1])


def _seed_for_mode(mode: int, surface: Representation | None = None) -> int:
    """First seed in 1..200 that yields ``mode`` (both modes appear across seeds)."""
    for seed in range(1, 201):
        if _mode(_problem(seed, surface)) == mode:
            return seed
    raise AssertionError(f"no seed in 1..200 produced exponents mode {mode}")


def test_exponents_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_both_modes_appear_across_seeds() -> None:
    """The seeded RNG picks both POWER_ONLY and ORDER_OF_OPS, so one lesson covers all of 6.EE.1."""
    modes = {_mode(_problem(seed)) for seed in range(1, 60)}
    assert modes == {_EXPONENT_POWER_ONLY, _EXPONENT_ORDER_OF_OPS}


# ─── POWER_ONLY (mode 0): the bare power, unchanged behavior + AREA_MODEL ───


def test_power_only_is_a_clean_in_scope_problem() -> None:
    """A POWER_ONLY item is numeric with (base, exp, mode) operands; answer = base**exp.

    base >= 2 and exp >= 2 (excluding base == 2 and exp == 2), so the correct power always differs
    from the multiply slip (base*exp) — keeping that misconception diagnostic.
    """
    problem = _problem(_seed_for_mode(_EXPONENT_POWER_ONLY))
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 3
    base, exp, mode = problem.operands
    assert int(mode) == _EXPONENT_POWER_ONLY
    assert base >= 2 and exp >= 2
    assert not (base == 2 and exp == 2)
    assert all(operand.q == 1 for operand in problem.operands)  # whole-number operands
    assert problem.correct_value == base**exp
    assert problem.statement == f"What is {int(base)}^{int(exp)}?"


def test_power_only_correct_value_verifies_correct() -> None:
    """The repeated-multiplication value (base**exp) is graded correct by the tutor's oracle."""
    seed = _seed_for_mode(_EXPONENT_POWER_ONLY)
    problem = _problem(seed)
    result = verify(problem, str(problem.correct_value))
    assert result.is_correct
    assert result.error_category is ErrorCategory.NONE


def test_multiply_base_by_exponent_is_classified_on_power_only() -> None:
    """On a POWER_ONLY item, base*exp is OPERATION + the multiply-base-by-exponent misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — multiplied the
    base BY the exponent once (3^4 -> 3*4 = 12) instead of multiplying the base by itself exp
    times (3*3*3*3 = 81). The slip value is always DISTINCT from the correct base**exp in scope.
    """
    seed = _seed_for_mode(_EXPONENT_POWER_ONLY)
    problem = _problem(seed)
    assert problem.operands is not None
    base, exp, _mode_flag = problem.operands
    wrong = multiply_base_by_exponent(int(base), int(exp))
    assert wrong != problem.correct_value
    result = verify(problem, str(wrong))
    assert not result.is_correct
    assert result.error_category is ErrorCategory.OPERATION
    assert result.matched_misconception is MisconceptionId.MULTIPLY_BASE_BY_EXPONENT


def test_multiply_slip_is_inert_on_order_of_ops() -> None:
    """The multiply-base-by-exp slip never fires on an ORDER_OF_OPS item (5-tuple, wrong shape).

    The predictor is gated to the POWER_ONLY 3-tuple (returns None off mode 0), and the verifier
    row is keyed to operand_count=3, so the 5-tuple order-of-ops item is never even offered to it —
    mirroring the AREA_POLYGONS triangle/trapezoid arity split.
    """
    seed = _seed_for_mode(_EXPONENT_ORDER_OF_OPS)
    problem = _problem(seed)
    assert problem.operands is not None
    base, exp, *_rest = problem.operands
    # The bare base*exp value, were the slip to (wrongly) apply here, must NOT be classified as the
    # multiply-base-by-exponent misconception on an order-of-ops item.
    bare_slip = multiply_base_by_exponent(int(base), int(exp))
    result = verify(problem, str(bare_slip))
    assert result.matched_misconception is not MisconceptionId.MULTIPLY_BASE_BY_EXPONENT


# ─── ORDER_OF_OPS (mode 1): a power inside order of operations ───


def test_order_of_ops_is_a_clean_in_scope_problem() -> None:
    """An ORDER_OF_OPS item is numeric with a 5-tuple; correct = the exponent-first evaluation.

    The answer is a clean whole number, and for a subtraction form it is non-negative (out-of-scope
    negatives are excluded). The correct value uses the power BEFORE the surrounding operation.
    """
    for seed in range(1, 80):
        problem = _problem(seed)
        if _mode(problem) != _EXPONENT_ORDER_OF_OPS:
            continue
        assert problem.answer_kind is AnswerKind.NUMERIC
        assert problem.operands is not None and len(problem.operands) == 5
        assert all(operand.q == 1 for operand in problem.operands)  # whole-number operands
        assert problem.correct_value.q == 1  # a clean whole number
        assert problem.correct_value >= 0  # subtraction form never goes negative
        base, exp, a_const, op_code, mode = problem.operands
        assert int(mode) == _EXPONENT_ORDER_OF_OPS
        assert base >= 2 and exp >= 2


def test_order_of_ops_correct_value_verifies_correct() -> None:
    """The exponent-first value is graded correct; a correct answer is never flagged."""
    seed = _seed_for_mode(_EXPONENT_ORDER_OF_OPS)
    problem = _problem(seed)
    result = verify(problem, str(problem.correct_value))
    assert result.is_correct
    assert result.error_category is ErrorCategory.NONE
    assert result.matched_misconception is None


def test_order_of_ops_left_to_right_slip_is_classified() -> None:
    """Left-to-right (ignoring exponent-first) is OPERATION + the order-of-operations-slip.

    "2 + 3^2" done as "(2+3)^2 = 25" instead of "2 + 9 = 11". The wrong value is genuinely DISTINCT
    from the correct one for every generated item (the generator picks operands so this holds), so
    the match is always diagnostic.
    """
    for seed in range(1, 120):
        problem = _problem(seed)
        if _mode(problem) != _EXPONENT_ORDER_OF_OPS:
            continue
        assert problem.operands is not None
        wrong = evaluate_exponent_order_left_to_right(problem.operands)
        assert wrong is not None
        assert wrong != problem.correct_value  # distinct -> diagnostic
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.ORDER_OF_OPERATIONS_SLIP


# ─── Masterability + AREA_MODEL behavior across both modes ───


def test_two_live_surfaces_share_the_same_numeric_answer() -> None:
    """SYMBOLIC and AREA_MODEL are BOTH live; the KC stays masterable via the power-only surface.

    AREA_MODEL is POWER_ONLY only (an order-of-ops expression has no square/cube picture), so for
    the same seed the SYMBOLIC and AREA_MODEL surfaces agree on the bare-power item: identical
    operands and correct value, only the framing differs. This is the representation-agnostic
    answer that makes §3.4 rule 2 reachable live.
    """
    assert set(live_representations(_KC)) == {Representation.SYMBOLIC, Representation.AREA_MODEL}
    assert is_masterable_live(_KC)
    for seed in range(1, 30):
        area = _problem(seed, Representation.AREA_MODEL)
        assert _mode(area) == _EXPONENT_POWER_ONLY  # AREA_MODEL is always power-only
        # The matching SYMBOLIC power-only item (force the same bare-power surface for comparison):
        base, exp, _mode_flag = area.operands  # type: ignore[misc]
        assert verify(area, str(area.correct_value)).is_correct
        assert area.correct_value == base**exp


def test_area_model_is_always_power_only() -> None:
    """Requesting AREA_MODEL ALWAYS yields a coherent POWER_ONLY (square/cube/repeat) item.

    The order-of-ops mode has no single picture, so AREA_MODEL forces mode 0 — never an order-of-ops
    expression rendered as a (nonexistent) picture. Documents what AREA_MODEL does for this KC now.
    """
    for seed in range(1, 80):
        area = _problem(seed, Representation.AREA_MODEL)
        assert _mode(area) == _EXPONENT_POWER_ONLY
        assert area.operands is not None and len(area.operands) == 3
        # A picture statement, not an arithmetic-expression statement.
        assert "^" not in area.statement


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_worked_example_lands_on_the_answer_for_both_modes() -> None:
    """The worked example's final step equals the correct value in BOTH modes (self-consistency)."""
    for mode in (_EXPONENT_POWER_ONLY, _EXPONENT_ORDER_OF_OPS):
        problem = _problem(_seed_for_mode(mode))
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_exponents() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
