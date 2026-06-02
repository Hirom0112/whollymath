"""Display-only FRACTION AREA-MODEL stimulus: the two OPERAND fractions drawn as partitioned bars.

The four two-operand fraction-arithmetic KCs — add (6.NS via 5.NF carry-forward), subtract,
multiply, and divide unlike-denominator fractions — all read off the SAME idea a 6th grader can
see: a fraction is "this many of that many equal parts of a bar". This module turns the two
OPERAND fractions the generator names ("a/b + c/d", "a/b x c/d", ...) into a structured,
display-only ``FractionAreaStimulus`` the surface draws as area-model bars beside the answer box,
so the partitioning does the imagining for the learner.

Single source of truth (the §8.4 anti-drift rule): the stimulus is DERIVED from the problem's
``operands`` — the exact ``(first, second)`` pair of SymPy ``Rational``s the generator also formats
into the prompt text ("{first.p}/{first.q} ... {second.p}/{second.q}") — so the picture and the
words can never disagree. Nothing here recomputes or invents data.

This is DISPLAY-ONLY, like ``SetModelStimulus`` / ``PercentGridStimulus``: it carries the QUESTION
INPUT (the two operand fractions), NEVER the ANSWER. The sum / difference / product / quotient the
student must find lives only in ``Problem.correct_value`` and never enters the stimulus — showing
the two operand bars leaks nothing the prompt text doesn't already say (CLAUDE.md §8.2). Grading
stays with the SymPy verifier server-side; this changes nothing about grading.

No SymPy decision-making and no LLM here — a pure projection of already-decided domain data into a
renderable shape (CLAUDE.md §7, §8.2). It lives in ``domain/`` because it reads the domain's operand
encoding. The ``op`` field records WHICH operation so the surface can choose its layout (stacked
bars for add/subtract so unlike denominators line up; an area grid for multiply/divide) without
re-parsing the statement — the picture itself never depends on the (hidden) result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId

FractionOp = Literal["add", "subtract", "multiply", "divide"]


@dataclass(frozen=True)
class FractionBarOperand:
    """One operand fraction as an area-model bar: a bar cut into ``denominator`` equal parts with
    ``numerator`` of them shaded. Both come straight off a single operand ``Rational`` (its ``.p``
    / ``.q``), so the bar always matches the fraction the prompt names — no recomputation.
    """

    numerator: int
    denominator: int


@dataclass(frozen=True)
class FractionAreaStimulus:
    """The two operand fractions of an arithmetic item, each as a partitioned area-model bar.

    ``first`` and ``second`` are the two operands in the order the prompt names them. ``op`` records
    the operation (add / subtract / multiply / divide) so the surface can choose stacked bars vs an
    area grid; it is metadata for layout, not a computed result. There is exactly one shape for all
    four KCs — only ``op`` differs — because every one of them carries the identical
    ``operands = (first, second)`` two-fraction encoding.
    """

    kind: Literal["fraction_area"]
    op: FractionOp
    first: FractionBarOperand
    second: FractionBarOperand


# The operation each KC names, used only to pick a layout on the surface — NEVER to compute or
# reveal the answer. Kept as a module table (not inline branches) so adding a fifth two-operand
# fraction KC is a one-line change, mirroring the other stimuli.
_OP_BY_KC: dict[KnowledgeComponentId, FractionOp] = {
    KnowledgeComponentId.ADDITION_UNLIKE: "add",
    KnowledgeComponentId.SUBTRACTION_UNLIKE: "subtract",
    KnowledgeComponentId.MULTIPLY_FRACTIONS: "multiply",
    KnowledgeComponentId.DIVIDE_FRACTIONS: "divide",
}


def fraction_area_for(
    kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None
) -> FractionAreaStimulus | None:
    """The display-only area-model picture for a problem, derived from its ``operands``; ``None``
    for any KC that is not one of the four two-operand fraction-arithmetic KCs.

    Each of those KCs encodes ``operands = (first, second)`` — two proper-fraction SymPy
    ``Rational``s, the exact pair the generator formats into the prompt. Each operand becomes a
    partitioned bar (``.q`` parts, ``.p`` shaded). The operation comes from the KC, not from the
    operands, so the picture stays purely the two GIVENS and never the result the student must find.
    """
    op = _OP_BY_KC.get(kc)
    if op is None:
        return None
    if operands is None or len(operands) != 2:
        return None  # defensive: a malformed operand tuple draws no picture rather than crashing
    first, second = operands[0], operands[1]
    return FractionAreaStimulus(
        kind="fraction_area",
        op=op,
        first=FractionBarOperand(numerator=int(first.p), denominator=int(first.q)),
        second=FractionBarOperand(numerator=int(second.p), denominator=int(second.q)),
    )
