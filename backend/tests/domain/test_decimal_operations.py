"""Behavioral tests for KC_decimal_operations — Grade-6 Unit 2 (2026-05-30).

Add, subtract, multiply, AND divide multi-digit decimals and read the answer's place value
(CCSS 6.NS.3 / TEKS 6.3E). Exercises the KC through the SAME oracle the tutor uses (the SymPy
verifier), so "correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9).
Pins: the generator builds a clean, in-scope decimal item in any of the four operations; the
verifier confirms the correct answer (entered as a DECIMAL string — the capability added in the
prior commit) and classifies the decimal-point-misplacement misconception (multiply only); the
worked example lands on the answer; and generation is deterministic (PROJECT.md §4.1).
Mandatory-TDD domain Layer 1 (CLAUDE.md §2).

Coverage fix (panel audit 2026-06-04, Slice 4a): the generator previously ONLY multiplied, so the
lesson covered a quarter of its standard. It now emits all four operations; the operand tuple
carries a mode flag ``(first, second, mode)`` so the same item renders identically across surfaces
and the verifier can gate the multiply-specific misconception.

Misconception classification choice (justified): point-misplacement leaves the DIGITS right
but the SIZE wrong — the wrong value is the correct one off by a power of ten — so it is a
MAGNITUDE error (routes to the size-exposing surface, §3.6), not OPERATION. The lead's brief
explicitly allows MAGNITUDE "if the value is off by a power of ten"; it is, by construction. The
misconception is MULTIPLY-SPECIFIC (it models placing the product's point by the longer factor's
place count), so it must NOT fire on add/subtract/divide items — pinned below.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, decimal_point_misplacement
from app.domain.problem_generators import (
    _DECIMAL_ADD,
    _DECIMAL_DIVIDE,
    _DECIMAL_MULTIPLY,
    _DECIMAL_SUBTRACT,
    AnswerKind,
    Problem,
    generate_problem,
)
from app.domain.scene import scene_for
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.DECIMAL_OPERATIONS

# Enough consecutive seeds to be sure every operation mode is exercised (the seeded RNG spreads the
# four modes across this range; 1..40 hits each many times).
_SEEDS = range(1, 41)


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _mode(problem: Problem) -> int:
    """The operation-mode flag, the third operand, as a plain int."""
    assert problem.operands is not None and len(problem.operands) == 3
    return int(problem.operands[2])


def _sympy_result(first: Rational, second: Rational, mode: int) -> Rational:
    """The reference value for an item, computed straight from SymPy (the independent oracle)."""
    if mode == _DECIMAL_ADD:
        return Rational(first + second)
    if mode == _DECIMAL_SUBTRACT:
        return Rational(first - second)
    if mode == _DECIMAL_DIVIDE:
        return Rational(first / second)
    return Rational(first * second)  # _DECIMAL_MULTIPLY


def test_decimal_operations_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_area_model_is_the_same_item_with_a_picture() -> None:
    """AREA_MODEL serves the SAME numeric answer as SYMBOLIC (same operands + value, INCLUDING the
    mode flag), now with a place-value display scene attached — the masterable second
    representation, no new input widget (EVALUATE_EXPRESSIONS pattern). Closes the practice-only gap
    flagged in the panel audit (2026-06-04)."""
    sym = generate_problem(_KC, seed=5, surface_format=Representation.SYMBOLIC)
    area = generate_problem(_KC, seed=5, surface_format=Representation.AREA_MODEL)
    assert area.surface_format is Representation.AREA_MODEL
    assert area.operands == sym.operands  # same operands AND same mode flag across surfaces
    assert area.correct_value == sym.correct_value
    assert scene_for(_KC, area.operands) is not None


def test_all_four_operation_modes_appear_across_seeds() -> None:
    """The generator covers the WHOLE of 6.NS.3 — add, subtract, multiply, AND divide — not just
    multiplication (the coverage gap the panel flagged, 2026-06-04)."""
    modes = {_mode(_problem(seed)) for seed in _SEEDS}
    assert modes == {_DECIMAL_MULTIPLY, _DECIMAL_ADD, _DECIMAL_SUBTRACT, _DECIMAL_DIVIDE}


def test_generated_item_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with two decimal operands and a mode flag, whose answer
    equals the SymPy operation for that mode."""
    for seed in _SEEDS:
        problem = _problem(seed)
        assert problem.kc is _KC
        assert problem.answer_kind is AnswerKind.NUMERIC
        assert problem.operands is not None and len(problem.operands) == 3
        first, second, _ = problem.operands
        mode = _mode(problem)
        assert problem.correct_value == _sympy_result(first, second, mode)
        # Both numeric operands are genuine decimals (denominator a power of ten > 1 before the
        # operation), so place value in the answer is non-trivial.
        assert first.q > 1 and second.q > 1


def test_subtract_result_is_non_negative() -> None:
    """SUBTRACT items never ask for a negative answer (out of scope for 6.NS.3, which is whole-
    decimal arithmetic) — the generator orders operands so the result is >= 0."""
    saw_subtract = False
    for seed in _SEEDS:
        problem = _problem(seed)
        if _mode(problem) == _DECIMAL_SUBTRACT:
            saw_subtract = True
            assert problem.correct_value >= 0
    assert saw_subtract  # the mode is actually exercised in the seed range


def test_divide_result_is_an_exact_finite_decimal() -> None:
    """DIVIDE items have an EXACT terminating-decimal quotient (denominator a power of ten after
    reduction), so the answer is a clean decimal string — never a repeating decimal."""
    saw_divide = False
    for seed in _SEEDS:
        problem = _problem(seed)
        if _mode(problem) == _DECIMAL_DIVIDE:
            saw_divide = True
            assert _is_power_of_ten_denominator(problem.correct_value)
    assert saw_divide


def test_every_answer_is_a_finite_decimal() -> None:
    """Across ALL modes the answer is renderable as a finite decimal (reduced denominator is a power
    of ten), so the symbolic editor accepts it as a decimal string."""
    for seed in _SEEDS:
        problem = _problem(seed)
        assert _is_power_of_ten_denominator(problem.correct_value)


def test_correct_answer_verifies_correct_as_a_decimal_string() -> None:
    """The answer, typed as a DECIMAL string, is graded correct by the tutor's own oracle, for every
    operation mode."""
    for seed in _SEEDS:
        problem = _problem(seed)
        value = problem.correct_value
        decimal_text = _as_decimal_string(value)
        assert Rational(decimal_text) == value  # the rendering is exact (sanity)
        result = verify(problem, decimal_text)
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_point_misplacement_classified_as_magnitude_on_multiply() -> None:
    """The misplaced product (off by a power of ten) is flagged MAGNITUDE + the misconception — on a
    MULTIPLY item, the only place the multiply-specific misconception can apply."""
    saw_multiply = False
    for seed in _SEEDS:
        problem = _problem(seed)
        if _mode(problem) != _DECIMAL_MULTIPLY:
            continue
        saw_multiply = True
        assert problem.operands is not None
        wrong = decimal_point_misplacement(problem.operands)
        assert wrong is not None  # the misconception applies on multiply
        # The misplacement is genuinely a DIFFERENT, wrong value (off by a power of ten > 1).
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.MAGNITUDE
        assert result.matched_misconception is MisconceptionId.DECIMAL_POINT_MISPLACEMENT
    assert saw_multiply


def test_point_misplacement_does_not_apply_off_multiply() -> None:
    """The multiply-specific misconception returns ``None`` (does not apply) off multiply, so it
    can never mislabel an add/subtract/divide item (mirrors the AREA_POLYGONS half-only gate)."""
    saw_non_multiply = False
    for seed in _SEEDS:
        problem = _problem(seed)
        if _mode(problem) == _DECIMAL_MULTIPLY:
            continue
        saw_non_multiply = True
        assert problem.operands is not None
        assert decimal_point_misplacement(problem.operands) is None
    assert saw_non_multiply


def test_correct_answer_is_not_mislabelled_as_a_misconception() -> None:
    """A CORRECT answer on any mode grades correct with NO misconception attached — the gate must
    not let the multiply misconception (or any other) fire on a right add/subtract/divide answer."""
    for seed in _SEEDS:
        problem = _problem(seed)
        result = verify(problem, _as_decimal_string(problem.correct_value))
        assert result.is_correct
        assert result.matched_misconception is None


def test_misplacement_is_off_by_a_power_of_ten() -> None:
    """The modeled wrong value (multiply mode) is the correct one scaled by a power of ten (the
    magnitude tell)."""
    problem = next(p for p in (_problem(s) for s in _SEEDS) if _mode(p) == _DECIMAL_MULTIPLY)
    assert problem.operands is not None
    wrong = decimal_point_misplacement(problem.operands)
    assert wrong is not None
    ratio = wrong / problem.correct_value
    # ratio is a power of ten (here >= 10, since both factors have >= 1 decimal place).
    assert ratio == int(ratio) and int(ratio) % 10 == 0


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1) — statement, value, AND
    operands (including the mode flag)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_statement_uses_the_right_operator_per_mode() -> None:
    """The prompt reads with the operator matching its mode, so the surface matches the answer."""
    for seed in _SEEDS:
        problem = _problem(seed)
        mode = _mode(problem)
        statement = problem.statement
        if mode == _DECIMAL_MULTIPLY:
            assert " x " in statement
        elif mode == _DECIMAL_ADD:
            assert " + " in statement
        elif mode == _DECIMAL_SUBTRACT:
            assert " − " in statement  # unicode minus, consistent within the lesson
        else:  # divide — same phrasing as the MULTI_DIGIT_DIVISION generator
            assert " divided by " in statement


def test_worked_example_lands_on_the_answer_for_every_mode() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency), for
    every operation mode."""
    seen: set[int] = set()
    for seed in _SEEDS:
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value
        seen.add(_mode(problem))
    assert seen == {_DECIMAL_MULTIPLY, _DECIMAL_ADD, _DECIMAL_SUBTRACT, _DECIMAL_DIVIDE}


def test_nudge_bank_covers_decimal_operations() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def _is_power_of_ten_denominator(value: Rational) -> bool:
    """True iff ``value``'s reduced denominator is a power of ten (so it renders as a finite decimal
    with no leftover prime). Pure integer arithmetic, no float."""
    den = value.q
    while den % 2 == 0:
        den //= 2
    while den % 5 == 0:
        den //= 5
    return bool(den == 1)


def _as_decimal_string(value: Rational) -> str:
    """Render an exact rational (reduced denominator a power of ten) as a finite decimal string.

    Helper for the test only (the production answer would come from the UI). Uses Python's
    exact integer arithmetic, never a float, so the rendering itself introduces no fuzz.
    """
    den = value.q
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    assert den == 1, "a decimal-operations answer is a terminating decimal by construction"
    places = max(twos, fives)
    if places == 0:
        return str(value.p)
    scaled = int(value * (10**places))  # exact — value has exactly ``places`` decimal places
    sign = "-" if scaled < 0 else ""
    digits = str(abs(scaled)).zfill(places + 1)
    return f"{sign}{digits[:-places]}.{digits[-places:]}"
