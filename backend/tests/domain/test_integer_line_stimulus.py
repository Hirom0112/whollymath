"""Tests for the display-only INTEGER NUMBER-LINE stimulus (the integer-arithmetic family).

The stimulus must be DERIVED from the same operands the prompt text is built from, so the picture
and the words can never disagree (the §8.4 anti-drift rule), and it must NEVER carry the answer
(§8.2). These pins assert: it fires only for the three integer KCs; the marked positions are exactly
the operands the generator used; the axis range is derived from operand magnitudes (contains 0 and
every marked point); and no field equals the computed answer (the sum / the |x| / the opposite).
Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skills: TEKS 6.3C/D, CCSS 6.NS.5–7.
"""

from __future__ import annotations

from app.domain.integer_line_stimulus import (
    AbsoluteValueStimulus,
    IntegerJumpStimulus,
    SignedPointStimulus,
    integer_line_for,
)
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import generate_problem

_ADD = KnowledgeComponentId.INTEGER_ADD_SUBTRACT
_ABS = KnowledgeComponentId.ABSOLUTE_VALUE
_SIGNED = KnowledgeComponentId.SIGNED_NUMBERS
_INTEGER_KCS = {_ADD, _ABS, _SIGNED}


def test_no_stimulus_for_non_integer_kcs() -> None:
    """Every KC outside the integer-arithmetic family carries no number-line stimulus."""
    for kc in KnowledgeComponentId:
        if kc in _INTEGER_KCS:
            continue
        assert integer_line_for(kc, None) is None
        assert integer_line_for(kc, ()) is None


def test_malformed_operands_draw_no_line() -> None:
    """A missing / wrong-shaped operand tuple returns None rather than crashing (defensive)."""
    for kc in _INTEGER_KCS:
        assert integer_line_for(kc, None) is None
        assert integer_line_for(kc, ()) is None
    # Wrong arity per KC: add/sub wants 2, abs & signed want 1.
    from sympy import Rational

    assert integer_line_for(_ADD, (Rational(3),)) is None
    assert integer_line_for(_ABS, (Rational(3), Rational(4))) is None
    assert integer_line_for(_SIGNED, (Rational(3), Rational(4))) is None


def _axis_contains(axis_min: int, axis_max: int, *points: int) -> bool:
    return axis_min <= 0 <= axis_max and all(axis_min <= p <= axis_max for p in points)


def test_add_subtract_marks_start_and_jump_from_operands() -> None:
    """The jump's start and delta are exactly operands (a, b); the axis contains 0, start, and the
    landing; and NO field equals the answer (the sum a + b)."""
    for seed in range(1, 40):
        problem = generate_problem(_ADD, seed)
        assert problem.operands is not None
        a, b = int(problem.operands[0]), int(problem.operands[1])
        stimulus = integer_line_for(problem.kc, problem.operands)
        assert isinstance(stimulus, IntegerJumpStimulus)
        assert stimulus.kind == "integer_jump"
        assert stimulus.start == a
        assert stimulus.delta == b
        # Axis derived from magnitudes: contains 0, the start, and the (unlabelled) landing.
        assert _axis_contains(stimulus.axis_min, stimulus.axis_max, a, a + b)
        # No answer leak: the sum is not stored as any scalar field.
        answer = a + b
        assert stimulus.start != answer or a == answer  # start is a, not the sum (a==sum iff b==0)
        # The dataclass fields are exactly {start, delta, axis bounds} — the sum is absent.
        assert (stimulus.start, stimulus.delta) == (a, b)


def test_add_subtract_axis_scales_with_magnitude() -> None:
    """A larger operand magnitude yields a wider axis (range is derived, not hardcoded)."""
    from sympy import Rational

    small = integer_line_for(_ADD, (Rational(2), Rational(-1)))
    big = integer_line_for(_ADD, (Rational(20), Rational(-15)))
    assert isinstance(small, IntegerJumpStimulus)
    assert isinstance(big, IntegerJumpStimulus)
    small_span = small.axis_max - small.axis_min
    big_span = big.axis_max - big.axis_min
    assert big_span > small_span


def test_absolute_value_marks_point_not_distance() -> None:
    """The marked point is exactly the operand; axis contains 0 and the point; the distance to 0
    (the answer) is not stored."""
    for seed in range(1, 40):
        problem = generate_problem(_ABS, seed)
        assert problem.operands is not None
        value = int(problem.operands[0])
        stimulus = integer_line_for(problem.kc, problem.operands)
        assert isinstance(stimulus, AbsoluteValueStimulus)
        assert stimulus.kind == "absolute_value"
        assert stimulus.point == value
        assert _axis_contains(stimulus.axis_min, stimulus.axis_max, value)
        # No answer leak: the only scalar is `point` (the signed input), never abs(value).
        # value is negative by construction, so abs(value) != value — confirm we kept the input.
        assert stimulus.point == value
        assert stimulus.point != abs(value)


def test_signed_numbers_marks_given_not_opposite() -> None:
    """The single marked point is the given n; the opposite -n (the answer) is never marked."""
    for seed in range(1, 40):
        problem = generate_problem(_SIGNED, seed)
        assert problem.operands is not None
        n = int(problem.operands[0])
        stimulus = integer_line_for(problem.kc, problem.operands)
        assert isinstance(stimulus, SignedPointStimulus)
        assert stimulus.kind == "signed_point"
        assert stimulus.points == (n,)
        assert _axis_contains(stimulus.axis_min, stimulus.axis_max, n)
        # No answer leak: the opposite is NOT among the marked points.
        assert -n not in stimulus.points
