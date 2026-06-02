"""Display-only INTEGER NUMBER-LINE stimulus: the horizontal line the surface draws for the
integer-arithmetic family (KC_integer_add_subtract, KC_absolute_value, KC_signed_numbers).

A 6th grader reasons about signed numbers as POSITIONS and MOVES on a line: −3 is three steps left
of 0, |−5| is how far −5 sits from 0, and "5 + (−3)" is a jump of 3 to the left starting at 5.
This module turns the SAME ``operands`` the generator put in the prompt into a structured,
display-only stimulus the surface can draw as a number line — so the picture does the spatial
reasoning a 6th grader is still building (TEKS 6.3C/D, CCSS 6.NS.5–7).

Single source of truth (the §8.4 anti-drift rule): every field is DERIVED from the problem's
``operands`` — the exact ``(a, b)`` / ``(value,)`` / ``(n,)`` the generator also formats into the
prompt text. Nothing here recomputes or invents the problem; the axis range is computed FROM the
operand magnitudes (never hardcoded), so a small problem draws a small line and a large one a wide
line.

DISPLAY-ONLY, like ``SetModelStimulus`` / ``StatsStimulus``: it carries only the QUESTION INPUT
(the operand positions and, for add/subtract, the MOTION), never the ANSWER (CLAUDE.md §8.2). For
add/subtract the stimulus exposes the start and the signed jump (``delta``) but DOES NOT name where
the jump lands — the sum is the answer and lives only in ``Problem.correct_value``, graded by the
SymPy verifier server-side. For absolute value it exposes the point and that the question is its
distance to 0, but not the distance value. For signed numbers it exposes the point(s) only.

No SymPy decision-making and no LLM here — a pure projection of already-decided domain data into a
renderable shape (CLAUDE.md §7, §8.1, §8.2). It lives in ``domain/`` because it reads the domain's
operand encoding. The ``kind`` tag lets the three KCs return the shape each one needs while staying
one cohesive module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId

# How much breathing room (in integer units) to leave past the outermost marked point, so a point
# is never jammed against the end of the axis. The axis ends are always whole integers spanning 0.
_AXIS_PADDING = 1


def _axis_bounds(points: tuple[int, ...]) -> tuple[int, int]:
    """Smallest integer ``[axis_min, axis_max]`` window that contains 0 and every point in
    ``points`` with one unit of padding on each side. DERIVED from the operand magnitudes (never
    hardcoded), so the range scales to the problem.
    """
    lo = min(0, *points) - _AXIS_PADDING
    hi = max(0, *points) + _AXIS_PADDING
    return lo, hi


@dataclass(frozen=True)
class IntegerJumpStimulus:
    """An add/subtract jump: start at ``start``, move ``delta`` (signed) along the line.

    Shows the MOTION, not the landing: the surface draws an arrow from ``start`` of length/direction
    ``delta`` but the endpoint number (the sum) is NOT a field here — that is the answer (§8.2). The
    axis ends are chosen to contain 0, the start, AND the landing point (``start + delta``) so the
    arrow always fits, but the landing is used only to size the axis, never labelled.
    """

    kind: Literal["integer_jump"]
    axis_min: int
    axis_max: int
    start: int
    delta: int


@dataclass(frozen=True)
class AbsoluteValueStimulus:
    """An absolute-value point: mark ``point`` and show its distance to 0 (the bracket/segment from
    ``point`` to 0). The distance VALUE (the answer) is NOT a field — the surface draws the span, it
    does not label its length (§8.2).
    """

    kind: Literal["absolute_value"]
    axis_min: int
    axis_max: int
    point: int


@dataclass(frozen=True)
class SignedPointStimulus:
    """One or more marked integers on the line (the signed-numbers givens). For "opposite of n" the
    single given ``n`` is marked; the opposite (the answer) is NOT marked (§8.2).
    """

    kind: Literal["signed_point"]
    axis_min: int
    axis_max: int
    points: tuple[int, ...]


IntegerLineStimulus = IntegerJumpStimulus | AbsoluteValueStimulus | SignedPointStimulus


def integer_line_for(
    kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None
) -> IntegerLineStimulus | None:
    """The display-only integer-number-line stimulus for a problem, derived from its ``operands``;
    ``None`` for any KC outside the integer-arithmetic family or any malformed operand tuple.

    Operand encodings (quoted from problem_generators.py):

    - KC_integer_add_subtract: ``operands = (a, b)`` (two opposite-sign integers, ``a + b``). Start
      at ``a``, jump by ``b``. The landing ``a + b`` is the answer and is never labelled — only used
      to size the axis so the arrow fits.
    - KC_absolute_value: ``operands = (value,)`` (a single negative integer). Mark ``value`` and
      show its distance to 0; the distance (the answer) is not labelled.
    - KC_signed_numbers: ``operands = (n,)`` (a single nonzero signed integer; the question is its
      opposite). Mark ``n``; the opposite ``-n`` (the answer) is not marked.
    """
    if kc is KnowledgeComponentId.INTEGER_ADD_SUBTRACT:
        if operands is None or len(operands) != 2:
            return None  # defensive: a malformed tuple draws no line rather than crashing
        start, delta = int(operands[0]), int(operands[1])
        # Axis must contain 0, the start, and the landing (start+delta) so the arrow always fits.
        axis_min, axis_max = _axis_bounds((start, start + delta))
        return IntegerJumpStimulus(
            kind="integer_jump",
            axis_min=axis_min,
            axis_max=axis_max,
            start=start,
            delta=delta,
        )

    if kc is KnowledgeComponentId.ABSOLUTE_VALUE:
        if operands is None or len(operands) != 1:
            return None
        point = int(operands[0])
        axis_min, axis_max = _axis_bounds((point,))
        return AbsoluteValueStimulus(
            kind="absolute_value",
            axis_min=axis_min,
            axis_max=axis_max,
            point=point,
        )

    if kc is KnowledgeComponentId.SIGNED_NUMBERS:
        if operands is None or len(operands) != 1:
            return None
        point = int(operands[0])
        axis_min, axis_max = _axis_bounds((point,))
        return SignedPointStimulus(
            kind="signed_point",
            axis_min=axis_min,
            axis_max=axis_max,
            points=(point,),
        )

    return None
