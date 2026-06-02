"""Display-only PERCENT HUNDRED-GRID stimulus: a 10x10 grid the surface shades to show a percent.

Reading a percent as a "rate per 100" (CCSS 6.RP.A.3c) is exactly what a 10x10 grid of 100 cells
makes concrete: "30%" is 30 of the 100 little squares filled in. KC_percent asks "what is p% of
whole?"; this module turns the SAME ``p`` the prompt names into a structured, display-only
``PercentGridStimulus`` the surface can draw as a shaded hundred-grid beside the answer box, so the
picture carries the meaning of the percent for the learner.

Single source of truth (the §8.4 anti-drift rule): the stimulus is DERIVED from the problem's
``operands`` — ``(percent, whole)``, the exact pair the generator also formats into the prompt text
("What is {percent}% of {whole}?") — so the picture and the words can never disagree. Nothing here
recomputes or invents data.

This is DISPLAY-ONLY, like ``SetModelStimulus`` / ``StatsStimulus``: it carries the QUESTION INPUT
(the percent, as a count of shaded cells out of 100), NEVER the ANSWER. The answer ``p*whole/100``
(e.g. 18 for "30% of 60") lives only in ``Problem.correct_value`` and never enters the stimulus —
shading the percent leaks nothing the prompt text doesn't already say. Grading stays with the SymPy
verifier server-side (CLAUDE.md §8.2); this changes nothing about grading.

No SymPy decision-making and no LLM here — a pure projection of already-decided domain data into a
renderable shape (CLAUDE.md §7, §8.2). It lives in ``domain/`` because it reads the domain's operand
encoding. Keyed on the KC so a second percent KC can plug a grid picture in for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId


@dataclass(frozen=True)
class PercentGridStimulus:
    """A 10x10 hundred-grid with the named percent shaded — the "rate per 100" made visible.

    ``shaded`` is how many of the 100 cells to fill (it equals ``percent`` for an integer percent in
    [0, 100]). ``percent`` is the raw percent the prompt names, carried so the surface can caption
    "{percent} per 100" without re-parsing the statement. Both come straight off the operands.
    """

    kind: Literal["percent_grid"]
    percent: int
    shaded: int


def percent_grid_for(
    kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None
) -> PercentGridStimulus | None:
    """The display-only hundred-grid for a problem, derived from its ``operands``; ``None`` for any
    problem that names no percent (every KC except KC_percent).

    KC_percent encodes ``operands = (percent, whole)`` — index 0 is the percent ``p`` the prompt
    asks about, index 1 is the whole. Only the percent drives the picture (the grid is always 100
    cells; the whole is irrelevant to "p per 100"), so the whole is not read. The shaded count is
    clamped to [0, 100] defensively so a malformed percent never draws more than a full grid.
    """
    if kc is not KnowledgeComponentId.PERCENT:
        return None
    if operands is None or len(operands) != 2:
        return None  # defensive: a malformed operand tuple draws no picture rather than crashing
    percent = int(operands[0])
    shaded = max(0, min(100, percent))
    return PercentGridStimulus(kind="percent_grid", percent=percent, shaded=shaded)
