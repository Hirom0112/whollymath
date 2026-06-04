"""Display-only EXPONENT repeated-product stimulus: base^exp shown as expanded multiplication.

Grade-6 exponents (CCSS 6.EE.1) are *defined* as repeated multiplication — ``2^4`` MEANS
``2 x 2 x 2 x 2`` — and the whole misconception this KC guards against is reading the power as
``base x exp`` (the multiply slip). Seeing the expanded product makes the definition concrete: the
base appears exponent-many times. This module turns the SAME ``(base, exp)`` the prompt names into a
structured, display-only ``ExponentProductStimulus`` the surface can draw as ``base x base x ...``
beside the answer box, so the picture spells out the repeated multiplication.

Single source of truth (the §8.4 anti-drift rule): the stimulus is DERIVED from the problem's
``operands`` — the exact ``(base, exp)`` the generator also uses — so the picture and the words can
never disagree. The factor list is just the base repeated ``exp`` times; nothing here recomputes the
power or invents data. No SymPy decision-making, no LLM — a pure projection of decided domain data.

This is DISPLAY-ONLY: it carries the QUESTION INPUT (the base, the exponent, and the expanded
repeated-multiplication form), never the ANSWER. The evaluated value ``base ** exp`` the student
must find lives only in ``Problem.correct_value`` and never enters the stimulus — showing
``2 x 2 x 2 x 2`` is the input form, NOT the product ``16`` (no answer leak, CLAUDE.md §8.2). The
answer is still graded by the SymPy verifier server-side; this changes nothing about grading.

It lives in ``domain/`` because it reads the domain's operand encoding (CLAUDE.md §7, §8.2). Keyed
on the KC so the surface asks one function "is there a repeated-product picture for this problem?".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId


@dataclass(frozen=True)
class ExponentProductStimulus:
    """``base^exp`` shown as expanded repeated multiplication — the definition made concrete.

    ``base`` and ``exponent`` are the two numbers the prompt names. ``factors`` is the base repeated
    ``exponent`` times (e.g. ``(2, 2, 2, 2)`` for ``2^4``) — the expanded multiplication the surface
    joins with "x". This is the input form only; the product is never computed or stored here.
    """

    kind: Literal["exponent_product"]
    base: int
    exponent: int
    factors: tuple[int, ...]


def exponent_product_for(
    kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None
) -> ExponentProductStimulus | None:
    """The display-only repeated-product view for a problem, derived from its ``operands``;
    ``None`` for any problem that is not an exponent item.

    KC_exponents encodes the base and exponent as the FIRST two operands in either mode: a
    POWER_ONLY item is ``(base, exp, mode)`` and an ORDER_OF_OPS item is
    ``(base, exp, a, op_code, mode)``. In BOTH cases the repeated-product picture spells out the
    power ``base^exp`` — ``base`` is the repeated factor, ``exp`` the number of times it is
    multiplied — so the picture is derived from operands[0:2] regardless of mode. ``factors`` is
    ``base`` repeated ``exp`` times. (A legacy bare ``(base, exp)`` 2-tuple is still accepted so the
    pure unit calls keep working.)
    """
    if kc is not KnowledgeComponentId.EXPONENTS:
        return None
    # Accept the bare (base, exp) 2-tuple and the moded 3-tuple / 5-tuple; reject other shapes.
    if operands is None or len(operands) not in (2, 3, 5):
        return None  # defensive: a malformed operand tuple draws no picture rather than crashing
    base, exponent = int(operands[0]), int(operands[1])
    if exponent < 1:
        return None  # defensive: a non-positive exponent has no repeated-product expansion
    return ExponentProductStimulus(
        kind="exponent_product",
        base=base,
        exponent=exponent,
        factors=tuple(base for _ in range(exponent)),
    )
