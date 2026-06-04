"""Display-only PLACE-VALUE CHART stimulus: the operand decimals laid out in aligned place columns.

KC_decimal_operations (CCSS 6.NS.B.3) is about placing the decimal point by *counting place values*
-- ``0.5 x 0.4 = 0.20`` -- rather than misplacing the point by a power of ten. The representation
that makes that obvious is the place-value chart: each factor's digits dropped into labelled
columns (ones - tenths - hundredths ...) with the decimal points lined up, so a 6th grader SEES
which digit sits in which place before they multiply. This module turns the SAME operands the
generator put in the prompt into a structured, display-only ``DecimalPlaceValueStimulus`` the
surface can draw as a labelled grid beside the answer box.

Single source of truth (the CLAUDE.md §8.4 anti-drift rule): the chart is DERIVED from the
problem's ``operands`` -- the exact ``(first, second)`` Rationals the generator also formats into
the prompt text -- so the chart and the words can never disagree. Nothing here recomputes or invents
data, and (CLAUDE.md §8.2) it carries the QUESTION INPUT (the factor digits) only -- never the
product. Which decimal is the answer lives only in ``Problem.correct_value`` and is graded by the
SymPy verifier server-side; showing the operand digits leaks nothing the prompt doesn't already say.

No SymPy decision-making and no LLM here (CLAUDE.md §8.1, §8.2). SymPy ``Rational`` is used only as
a pure, float-free number carrier so the digit extraction introduces no floating-point fuzz: the
operands are exact finite decimals (power-of-ten origin), so each is scaled by the smallest power
of ten that makes it an integer and the digits are read off that integer. It lives in ``domain/``
because it reads the domain's operand encoding, and is keyed on the KC so a second decimal KC can
plug a place-value chart in for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId

# Place-value column labels, highest magnitude first. ``ones`` is the last whole-number place; the
# decimal point sits immediately after it, before ``tenths``. The chart only ever shows as many
# columns as the operands actually need (computed below), drawn from this ordered vocabulary.
_INTEGER_PLACES: tuple[str, ...] = ("thousands", "hundreds", "tens", "ones")
_FRACTION_PLACES: tuple[str, ...] = ("tenths", "hundredths", "thousandths", "ten-thousandths")

_MAX_SCALE = 12  # defensive cap on the scale-to-integer loop; real operands need <= 4 places


def _decimal_places(value: Rational) -> int:
    """The number of digits after the decimal point in ``value``'s exact finite-decimal form.

    The operands are exact finite decimals (the generator builds them from power-of-ten
    denominators), so multiplying by ``10`` repeatedly clears the fractional part in finitely many
    steps. Pure ``Rational`` arithmetic -- no float -- so no rounding fuzz enters the chart.
    """
    scaled = value
    places = 0
    while scaled.q != 1 and places < _MAX_SCALE:
        scaled = scaled * 10
        places += 1
    return places


@dataclass(frozen=True)
class DecimalPlaceValueRow:
    """One operand's row in the chart: its decimal text and the digit sitting in each column.

    ``digits`` is parallel to the stimulus' ``columns`` (same length, same order): each entry is the
    single digit ("0".."9") in that place for this operand, padded with "0" where the operand has no
    digit in a column. ``decimal_text`` is the operand exactly as the prompt renders it.
    """

    decimal_text: str
    digits: tuple[str, ...]


@dataclass(frozen=True)
class DecimalPlaceValueStimulus:
    """A place-value chart: the operand decimals dropped into aligned, labelled place columns.

    ``columns`` are the place labels (e.g. ``("ones", "tenths", "hundredths")``), highest magnitude
    first; ``point_after`` is the 0-based index of the column the decimal point follows (the last
    integer place, ``ones``), so the surface knows where to draw the aligned point. ``rows`` holds
    one ``DecimalPlaceValueRow`` per operand, in the order the prompt names them.
    """

    kind: Literal["decimal_place_value"]
    columns: tuple[str, ...]
    point_after: int
    rows: tuple[DecimalPlaceValueRow, ...]


def _column_layout(operands: tuple[Rational, ...]) -> tuple[tuple[str, ...], int]:
    """The shared place columns wide enough to hold every operand, plus the decimal-point index.

    Picks just enough integer places (left of the point) and fractional places (right of the point)
    to cover the largest operand on each side, so every row aligns on the same grid and on the
    decimal point. Returns ``(columns, point_after)`` where ``point_after`` indexes the last integer
    column (``ones``).
    """
    int_places = 1  # always at least the ones column, even for a value < 1 (rendered as "0")
    frac_places = 0
    for value in operands:
        frac_places = max(frac_places, _decimal_places(value))
        whole = int(value)  # floor toward zero; operands are non-negative finite decimals
        int_places = max(int_places, len(str(whole)))
    int_places = min(int_places, len(_INTEGER_PLACES))
    frac_places = min(frac_places, len(_FRACTION_PLACES))
    columns = _INTEGER_PLACES[len(_INTEGER_PLACES) - int_places :] + _FRACTION_PLACES[:frac_places]
    point_after = int_places - 1  # 0-based index of the ones column
    return columns, point_after


def _row_for(value: Rational, columns: tuple[str, ...], point_after: int) -> DecimalPlaceValueRow:
    """Lay ``value``'s digits into ``columns``, aligned on the decimal point, padding with "0".

    The value is scaled to the integer ``value * 10**frac_places`` (exact, float-free) and its
    digits are placed right-to-left from the lowest fractional column. ``decimal_text`` rebuilds the
    grid literal from the same digits, so the row text can never drift from the grid it labels.
    """
    frac_places = len(columns) - 1 - point_after
    scale = 10**frac_places
    scaled_int = int(value * scale)  # exact: value is a finite decimal, scale clears the fraction
    raw = str(scaled_int).rjust(len(columns), "0")
    digits = tuple(raw[-len(columns) :])
    int_text = "".join(digits[: point_after + 1]).lstrip("0") or "0"
    frac_text = "".join(digits[point_after + 1 :])
    decimal_text = f"{int_text}.{frac_text}" if frac_text else int_text
    return DecimalPlaceValueRow(decimal_text=decimal_text, digits=digits)


def decimal_place_value_for(
    kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None
) -> DecimalPlaceValueStimulus | None:
    """The display-only place-value chart for a problem, derived from its ``operands``; ``None`` for
    any problem that carries no decimal operands (every KC except the decimal-operations family).

    KC_decimal_operations encodes ``operands = (first, second, mode)`` -- the two exact-decimal
    operands plus an operation-mode flag (multiply/add/subtract/divide). Only the two operands are
    charted: ``mode`` is a routing flag, not a decimal to display, so it is sliced off here (it
    would otherwise draw a spurious "0"/"1"/"2"/"3" row). The chart shows both operand rows on a
    shared place-value grid; it never shows the answer (CLAUDE.md §8.2).
    """
    if kc is not KnowledgeComponentId.DECIMAL_OPERATIONS:
        return None
    if operands is None or len(operands) < 2:
        return None  # defensive: a malformed operand tuple draws no chart rather than crashing
    factors = operands[:2]  # drop the trailing mode flag; only the two operands are decimals
    columns, point_after = _column_layout(factors)
    rows = tuple(_row_for(value, columns, point_after) for value in factors)
    return DecimalPlaceValueStimulus(
        kind="decimal_place_value",
        columns=columns,
        point_after=point_after,
        rows=rows,
    )
