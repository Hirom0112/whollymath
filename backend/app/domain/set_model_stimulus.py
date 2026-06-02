"""Display-only SET-MODEL stimulus: a collection of discrete coloured counters the surface draws.

Grade-6 ratio language (CCSS 6.RP.A.1) is about reading a relationship off a COLLECTION — "3 green
and 6 yellow counters" — and telling a part-to-part comparison from a part-to-whole one. The words
alone make a 6th grader picture the jar in their head; this module turns the SAME collection the
prompt names into a structured, display-only ``SetModelStimulus`` the surface can draw as coloured
dots beside the answer box, so the picture does the imagining for them.

Single source of truth (the §8.4 anti-drift rule): the stimulus is DERIVED from the problem's
``operands`` — the exact ``(mode, colour_idx, part, other)`` the generator also formats into the
prompt text — and reads the SAME ``RATIO_COLOURS`` table the generator picked from, so the picture
and the words can never disagree. Nothing here recomputes or invents data.

This is DISPLAY-ONLY, like ``StatsStimulus`` / ``FigureStimulus``: it carries the QUESTION INPUT
(the counts of each colour), never the ANSWER. Which fraction is correct (part-whole vs part-part)
lives
only in ``Problem.correct_value`` and never enters the stimulus — showing the counters leaks nothing
the prompt text doesn't already say. The answer is still graded by the SymPy verifier server-side
(CLAUDE.md §8.2); this changes nothing about grading.

No SymPy decision-making and no LLM here — a pure projection of already-decided domain data into a
renderable shape (CLAUDE.md §7, §8.2). It lives in ``domain/`` because it reads the domain's operand
encoding. Keyed on the KC so a second part-whole KC can plug a counter picture in for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import RATIO_COLOURS


@dataclass(frozen=True)
class SetModelStimulus:
    """A collection of discrete counters, grouped by colour — the part-to-part / part-to-whole jar.

    ``groups`` pairs each colour name with its count, in the order the prompt names them (the asked
    colour first). ``asked_colour`` is the colour the question is about (always the first group), so
    the surface can mark it without re-parsing the prompt. Colours are plain CSS colour keywords.
    """

    kind: Literal["set_model"]
    groups: tuple[tuple[str, int], ...]
    asked_colour: str


def set_model_for(
    kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None
) -> SetModelStimulus | None:
    """The display-only counter picture for a problem, derived from its ``operands``; ``None`` for
    any problem that carries no two-colour collection (every KC except the ratio-language family).

    KC_ratio_language encodes ``operands = (mode, colour_idx, part, other)`` — ``colour_idx``
    indexes the SAME ``RATIO_COLOURS`` pair the generator named, ``part``/``other`` are the counts.
    The
    ``mode`` (part-whole vs part-part) does not change the picture — the jar is the same either way;
    only the question differs — so it is read but not branched on.
    """
    if kc is not KnowledgeComponentId.RATIO_LANGUAGE:
        return None
    if operands is None or len(operands) != 4:
        return None  # defensive: a malformed operand tuple draws no picture rather than crashing
    colour_idx, part, other = int(operands[1]), int(operands[2]), int(operands[3])
    this_colour, other_colour = RATIO_COLOURS[colour_idx]
    return SetModelStimulus(
        kind="set_model",
        groups=((this_colour, part), (other_colour, other)),
        asked_colour=this_colour,
    )
