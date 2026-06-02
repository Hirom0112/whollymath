"""Display-only RATIO-TABLE stimulus: a two-row table of equivalent ratios the surface draws.

Grade-6 ratio reasoning (CCSS 6.RP.A.2 / 6.RP.A.3a) lives in the ratio table: two labelled rows
whose columns are all the SAME ratio, scaled up or down. Seeing the given ratio sit next to the
column the question asks about — with the scale arrow between them — is the canonical scaffold for
both finding a unit rate (scale DOWN to one) and finding a missing equivalent term (scale UP by k).
This module turns the SAME ``operands`` the generator put in the prompt into a structured,
display-only ``RatioTableStimulus`` the surface can draw as a real table beside the answer box.

Single source of truth (the §8.4 anti-drift rule): the table is DERIVED from the problem's
``operands`` — the exact numbers the generator also formats into the prompt text — so the table and
the words can never disagree. Nothing here recomputes or invents data.

This is DISPLAY-ONLY, like ``SetModelStimulus`` / ``StatsStimulus``: it carries the QUESTION INPUT
(the given ratio and the scaffold structure), NEVER the answer the student must find. The asked
cell is left BLANK (``None``). For KC_unit_rate the blank is the per-one quantity; for
KC_equivalent_ratios the blank is the missing top term. The answer still lives only in
``Problem.correct_value`` and is graded by the SymPy verifier server-side (CLAUDE.md §8.2); this
changes nothing about grading.

No SymPy decision-making and no LLM here — a pure projection of already-decided domain data into a
renderable shape (CLAUDE.md §7, §8.1, §8.2). It lives in ``domain/`` because it reads the domain's
operand encoding. Keyed on the KC so a second ratio-reasoning KC can plug a table in for free.
"""

from __future__ import annotations

from dataclasses import dataclass

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId

# Row labels for the unit-rate table. The generator picks (noun, unit) from ``_RATE_CONTEXTS`` but
# does NOT encode the choice in ``operands`` — only the numbers are encoded — so the table uses
# neutral, always-correct row labels rather than guessing the context. "Amount" over "Units" reads
# correctly for every context (dollars/pound, miles/hour, ...).
_UNIT_RATE_TOP_LABEL = "Amount"
_UNIT_RATE_BOTTOM_LABEL = "Units"

# Row labels for the equivalent-ratios table: the two terms of the ratio, top : bottom.
_EQUIV_TOP_LABEL = "Top"
_EQUIV_BOTTOM_LABEL = "Bottom"


@dataclass(frozen=True)
class RatioTableColumn:
    """One column of the ratio table: a ``(top, bottom)`` pair.

    Either cell may be ``None``, meaning "the asked, blank cell" — the value the student must find.
    The surface renders ``None`` as an empty / question-marked cell and never as a number, so no
    answer leaks (§8.2). At most one cell across the whole table is ``None``.
    """

    top: int | None
    bottom: int | None


@dataclass(frozen=True)
class RatioTableStimulus:
    """A two-row ratio table — labelled rows, columns of equivalent ratios building from the given.

    ``columns`` are ordered left-to-right as the surface should draw them. ``scale_label`` is the
    multiplicative step BETWEEN the two columns (e.g. ``"×3"`` or ``"÷4"``) — the scaffold
    structure, not the answer — for the surface to draw as an arrow. ``top_label`` and
    ``bottom_label`` head the two rows. The whole thing is the QUESTION INPUT plus its scaffold; the
    asked cell is ``None``.
    """

    kind: str
    top_label: str
    bottom_label: str
    columns: tuple[RatioTableColumn, ...]
    scale_label: str


def ratio_table_for(
    kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None
) -> RatioTableStimulus | None:
    """The display-only ratio table for a problem, derived from its ``operands``; ``None`` for any
    KC that carries no ratio (every KC except the unit-rate / equivalent-ratios family) or whose
    operand tuple is malformed (defensive: draw no table rather than crash).

    KC_unit_rate encodes ``operands = (total, count)`` and asks the per-ONE rate. The table shows
    the unit column ``(?, 1)`` then the given column ``(total, count)``, with the scale-DOWN arrow
    ``÷count`` between them. The blank top-of-unit-column cell is exactly the unit rate the student
    must find — so the table shows the scaffold (scale to one) without the answer.

    KC_equivalent_ratios encodes ``operands = (a, b, target_den)`` and asks the missing top term of
    ``a : b = ? : target_den``. The scale factor ``k = target_den / b`` is integer by construction.
    The table shows the given column ``(a, b)`` then the asked column ``(?, target_den)``, with the
    scale-UP arrow ``×k`` between them. The blank cell is the missing term (= ``a*k``), never shown.
    """
    if kc is KnowledgeComponentId.UNIT_RATE:
        return _unit_rate_table(operands)
    if kc is KnowledgeComponentId.EQUIVALENT_RATIOS:
        return _equivalent_ratios_table(operands)
    return None


def _unit_rate_table(operands: tuple[Rational, ...] | None) -> RatioTableStimulus | None:
    if operands is None or len(operands) != 2:
        return None
    total, count = int(operands[0]), int(operands[1])
    if count <= 0:
        return None  # defensive: a zero/negative count has no meaningful scale-down arrow
    # Unit column first (the asked per-one cell is blank), then the given column. The scale BETWEEN
    # them is ÷count (given → unit). We show the magnitude the student scales by, not the answer.
    return RatioTableStimulus(
        kind="ratio_table",
        top_label=_UNIT_RATE_TOP_LABEL,
        bottom_label=_UNIT_RATE_BOTTOM_LABEL,
        columns=(
            RatioTableColumn(top=None, bottom=1),
            RatioTableColumn(top=total, bottom=count),
        ),
        scale_label=f"÷{count}",
    )


def _equivalent_ratios_table(
    operands: tuple[Rational, ...] | None,
) -> RatioTableStimulus | None:
    if operands is None or len(operands) != 3:
        return None
    a, b, target_den = int(operands[0]), int(operands[1]), int(operands[2])
    if b <= 0 or target_den % b != 0:
        return None  # defensive: k must be a whole-number scale (it always is, by construction)
    k = target_den // b
    # Given column first, then the asked column whose top term is blank. The scale BETWEEN them is
    # ×k (given → asked). k is the structure of the scaffold, NOT the answer (the answer is a*k).
    return RatioTableStimulus(
        kind="ratio_table",
        top_label=_EQUIV_TOP_LABEL,
        bottom_label=_EQUIV_BOTTOM_LABEL,
        columns=(
            RatioTableColumn(top=a, bottom=b),
            RatioTableColumn(top=None, bottom=target_den),
        ),
        scale_label=f"×{k}",
    )
