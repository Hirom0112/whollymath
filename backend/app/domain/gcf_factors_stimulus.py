"""Display-only GCF/LCM FACTOR-VIEW stimulus: the two given whole numbers with their factor lists.

Grade-6 GCF/LCM (CCSS 6.NS.4 / TEKS 6.7A) is made concrete by SEEING the factors of each number
side by side — the shared factors light up the GCF, and the multiples line up the LCM. Words alone
("the GCF of 12 and 18") ask a 6th grader to hold both factor lists in their head; this module
turns the SAME pair the prompt names into a structured, display-only ``GcfFactorsStimulus`` the
surface can draw as two labelled factor rows beside the answer box, so the picture does the listing.

Single source of truth (the §8.4 anti-drift rule): the stimulus is DERIVED from the problem's
``operands`` — the exact ``(a, b, mode)`` the generator also formats into the prompt text — so the
picture and the words can never disagree. The factor lists are recomputed deterministically (trial
division, no SymPy decision-making, no LLM) from the SAME two numbers; nothing here invents data.

This is DISPLAY-ONLY: it carries the QUESTION INPUT (the two given numbers and their own factors),
never the ANSWER. The chosen GCF or LCM the student must find lives only in
``Problem.correct_value`` and never enters the stimulus — listing the factors of the GIVEN numbers
leaks nothing the prompt doesn't already imply, and crucially does NOT state which factor is
greatest-common or which multiple is least-common (no answer leak, CLAUDE.md §8.2). The answer is
still graded by the SymPy verifier server-side; this changes nothing about grading.

It lives in ``domain/`` because it reads the domain's operand encoding (CLAUDE.md §7, §8.2). Keyed
on the KC so the surface asks one function "is there a factor picture for this problem?".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId

# operands carry a mode flag (0 = GCF asked, 1 = LCM asked) — the same encoding the generator uses
# as its single source of truth. Mirrored here so the stimulus can label the view without re-parsing
# the prompt text.
_GCF_MODE = 0
_LCM_MODE = 1


def _factors_of(n: int) -> tuple[int, ...]:
    """All positive divisors of ``n`` in ascending order, by deterministic trial division.

    A pure arithmetic helper (no SymPy decision-making, no LLM) — the factor list is QUESTION INPUT,
    the natural way to make the shared-factor / common-multiple relationship visible.
    """
    return tuple(d for d in range(1, n + 1) if n % d == 0)


@dataclass(frozen=True)
class GcfFactorsStimulus:
    """The two given whole numbers with each one's full factor list — the GCF/LCM factor view.

    ``first``/``second`` are the two numbers the prompt names, in order. ``first_factors`` and
    ``second_factors`` are their ascending divisor lists. ``mode`` is ``"gcf"`` or ``"lcm"`` so the
    surface can frame the view (shared factors vs common multiples) without re-reading the prompt —
    it does NOT state the answer, only which relationship the question is about.
    """

    kind: Literal["gcf_factors"]
    mode: Literal["gcf", "lcm"]
    first: int
    second: int
    first_factors: tuple[int, ...]
    second_factors: tuple[int, ...]


def gcf_factors_for(
    kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None
) -> GcfFactorsStimulus | None:
    """The display-only factor view for a problem, derived from its ``operands``; ``None`` for any
    problem that is not a GCF/LCM item.

    KC_gcf_lcm encodes ``operands = (a, b, mode)`` — ``a``/``b`` are the two whole numbers,
    ``mode`` (0 = GCF, 1 = LCM) frames the view. The factor lists are recomputed from ``a``/``b``.
    """
    if kc is not KnowledgeComponentId.GCF_LCM:
        return None
    if operands is None or len(operands) != 3:
        return None  # defensive: a malformed operand tuple draws no picture rather than crashing
    first, second, raw_mode = int(operands[0]), int(operands[1]), int(operands[2])
    if first < 1 or second < 1:
        return None  # defensive: factors are only defined for positive whole numbers
    mode: Literal["gcf", "lcm"] = "lcm" if raw_mode == _LCM_MODE else "gcf"
    return GcfFactorsStimulus(
        kind="gcf_factors",
        mode=mode,
        first=first,
        second=second,
        first_factors=_factors_of(first),
        second_factors=_factors_of(second),
    )
