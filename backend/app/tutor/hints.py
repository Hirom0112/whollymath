"""Nudge-level hints — pre-written conceptual prompts, no LLM, no SymPy (Slice 3.8).

This is phase 1 of the locked hint design (PROJECT.md §8 decision 0.D.3: hint levels
are ``nudge`` / ``partial_step`` / ``worked_step``; "nudge (pre-written, no LLM, no
SymPy)", "partial_step and worked_step (LLM slot-fill → SymPy-validated → ≤2 retries →
pre-written fallback)"; phased "nudges weeks 2-3, LLM-validated levels week 4"). This
module ships the FIRST, working hint path: the nudge level only. The LLM-filled,
SymPy-validated ``partial_step`` / ``worked_step`` levels are Slice 5.6 — they are NOT
built here; ``select_nudge`` raises ``NotImplementedError`` if asked for one (fail
loudly rather than return a hollow hint, CLAUDE.md §8.5).

A nudge is a CONCEPTUAL PROMPT in the spirit of PROJECT.md §3.7's example ("what does
the denominator tell us about each piece?"): it orients the learner toward the concept
WITHOUT revealing an answer. Because of that, a nudge carries no symbolic content — no
numeric answer, no specific fraction, no arithmetic claim — and so needs no SymPy
validation (PROJECT.md §3.10: SymPy validates the symbolic content of LLM hints, which
nudges do not have). Each nudge string is deliberately free of digits and bare math
glyphs; the test suite scans the whole bank to keep that property true, which is what
makes "no SymPy needed" sound rather than asserted.

WHERE a nudge surfaces is NOT this module's concern. The WHEN-gate (refuse-rule 5,
"never auto-help in the first 60s except on a wrong answer or explicit request") lives
in ``policy/refuse_rules.py`` (``may_auto_help``), and the inline-render rule
(refuse-rule 6, "render help inline, not a dialog") is a frontend concern. This module
only owns the CONTENT and a deterministic SELECTION over it. Wiring into the session
loop / policy is done by the caller, not here.

Hard boundaries (CLAUDE.md §8.1/§8.2): NO LLM, NO SymPy, NO DB, NO network — pre-written
strings and a deterministic selector. Determinism (PROJECT.md §4.1): the same inputs
yield the identical ``NudgeHint`` every call, so a nudge is reproducible as part of the
persona integration runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.verifier import ErrorCategory


class HintLevel(StrEnum):
    """The three locked hint levels (PROJECT.md §8 decision 0.D.3).

    A ``StrEnum`` so a level reads/serializes as its stable string (logs, the decision
    record the reviewer sees). All three members exist to PIN the 0.D.3 vocabulary, but
    only ``NUDGE`` is implemented in this slice; ``PARTIAL_STEP`` and ``WORKED_STEP`` are
    the LLM-slot-fill, SymPy-validated levels built in Slice 5.6. The string VALUES are
    the contract with that later slice and the API and must not drift.
    """

    NUDGE = "nudge"
    PARTIAL_STEP = "partial_step"
    WORKED_STEP = "worked_step"


@dataclass(frozen=True)
class NudgeHint:
    """One pre-written nudge: a conceptual prompt for a KC, with no math claim.

    Frozen — a banked nudge is a fact about the content, not mutable state (matches the
    Layer-1 / transfer-probe convention; CLAUDE.md §8.4). Named ``NudgeHint`` (not
    ``Nudge``) deliberately: ``policy/transitions.py`` already owns a ``Nudge`` type that
    is an idle-transition (the §3.6 idle row), a DIFFERENT concept; colliding the names
    would mislead a reader. Fields:

    - ``kc``     which knowledge component this nudge orients toward.
    - ``level``  always ``HintLevel.NUDGE`` here — the field exists so a nudge carries
      its level in the same shape the later ``partial_step`` / ``worked_step`` hints
      will, but this slice only produces ``NUDGE``.
    - ``text``   the kid-friendly conceptual prompt. No digits, no fractions, no
      arithmetic claim — see the module docstring for why.
    """

    kc: KnowledgeComponentId
    level: HintLevel
    text: str


def _nudge(kc: KnowledgeComponentId, text: str) -> NudgeHint:
    """Construct a NUDGE-level ``NudgeHint`` for ``kc`` (the only level this slice makes)."""
    return NudgeHint(kc=kc, level=HintLevel.NUDGE, text=text)


# The nudge bank: 2-4 pre-written conceptual prompts per KC (TODO.md 3.8.1). Each is a
# question or orientation in the spirit of PROJECT.md §3.7 ("what does the denominator
# tell us about each piece?") — it points at the concept and never states a number, a
# fraction, or an arithmetic result. Kid-friendly, no curriculum jargon. The prompts
# per KC target that KC's own concept (e.g. addition nudges orient toward same-size
# pieces before combining; number-line nudges orient toward where the amount sits).
NUDGE_BANK: dict[KnowledgeComponentId, tuple[NudgeHint, ...]] = {
    KnowledgeComponentId.EQUIVALENCE: (
        _nudge(
            KnowledgeComponentId.EQUIVALENCE,
            "If you shade in each fraction, do the shaded parts cover the same amount?",
        ),
        _nudge(
            KnowledgeComponentId.EQUIVALENCE,
            "What happens to the amount if you cut every piece into smaller, equal pieces?",
        ),
        _nudge(
            KnowledgeComponentId.EQUIVALENCE,
            "Two fractions can look different and still name the same amount. How could you check?",
        ),
    ),
    KnowledgeComponentId.COMMON_DENOMINATOR: (
        _nudge(
            KnowledgeComponentId.COMMON_DENOMINATOR,
            "What does the bottom number tell us about the size of each piece?",
        ),
        _nudge(
            KnowledgeComponentId.COMMON_DENOMINATOR,
            "Could you cut both fractions so every piece is the same size?",
        ),
        _nudge(
            KnowledgeComponentId.COMMON_DENOMINATOR,
            "It is hard to compare pieces of different sizes. How could you make the pieces match?",
        ),
    ),
    KnowledgeComponentId.ADDITION_UNLIKE: (
        _nudge(
            KnowledgeComponentId.ADDITION_UNLIKE,
            "Before you add, are the pieces the same size? You can only count pieces that match.",
        ),
        _nudge(
            KnowledgeComponentId.ADDITION_UNLIKE,
            "What does the bottom number tell us about each piece? Should it change when you add?",
        ),
        _nudge(
            KnowledgeComponentId.ADDITION_UNLIKE,
            "If you put both amounts together on the same picture, how much is shaded?",
        ),
    ),
    KnowledgeComponentId.SUBTRACTION_UNLIKE: (
        _nudge(
            KnowledgeComponentId.SUBTRACTION_UNLIKE,
            "Before you take some away, are the pieces the same size?",
        ),
        _nudge(
            KnowledgeComponentId.SUBTRACTION_UNLIKE,
            "What does the bottom number tell us about each piece? Should it change "
            "when you take some away?",
        ),
        _nudge(
            KnowledgeComponentId.SUBTRACTION_UNLIKE,
            "If you start with the first amount and take the second away, how much is left shaded?",
        ),
    ),
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT: (
        _nudge(
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
            "Is this amount closer to nothing, to one whole, or somewhere in between?",
        ),
        _nudge(
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
            "Think about how big the amount is, not the digits you see. Where would that much sit?",
        ),
        _nudge(
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
            "How many equal jumps fit between the ends, and how far along is this one?",
        ),
    ),
}


# A deterministic, fixed mapping from an error kind to a nudge index for a KC. The §3.6
# policy routes a MAGNITUDE error toward the magnitude-exposing representation and an
# OPERATION/FORMAT error toward the operation-exposing one (verifier.py module
# docstring); we mirror that intent at the nudge level — a magnitude slip pulls the
# "how big is this amount" prompt, an operation/format slip pulls the "are the pieces
# the same size" prompt. Categories with no special prompt (NONE / OTHER) fall through
# to index 0. Indices are taken modulo the KC's bank size in ``select_nudge``, so a KC
# with fewer banked nudges than the largest index still resolves deterministically.
_ERROR_CATEGORY_INDEX: dict[ErrorCategory, int] = {
    ErrorCategory.MAGNITUDE: 1,
    ErrorCategory.OPERATION: 0,
    ErrorCategory.FORMAT: 0,
    ErrorCategory.NONE: 0,
    ErrorCategory.OTHER: 0,
}


def select_nudge(
    kc: KnowledgeComponentId,
    *,
    error_category: ErrorCategory | None = None,
    index: int = 0,
    level: HintLevel = HintLevel.NUDGE,
) -> NudgeHint:
    """Pick one nudge for ``kc`` — deterministic, same inputs ⇒ same nudge (§4.1).

    Selection rule (in priority order):

    - ``level`` other than ``NUDGE`` raises ``NotImplementedError``: ``partial_step`` /
      ``worked_step`` are Slice 5.6 (LLM slot-fill, SymPy-validated). We fail loudly
      rather than return a stub (CLAUDE.md §8.5).
    - If an ``error_category`` is given, it maps (via ``_ERROR_CATEGORY_INDEX``) to a
      fixed nudge for the KC — mirroring the §3.6 magnitude-vs-operation routing intent
      at the nudge level. ``None`` behaves like the plain default.
    - Otherwise ``index`` selects directly into the KC's banked nudges.

    The chosen position is taken modulo the KC's bank size, so any index (or an
    error-category index larger than a small KC's bank) wraps deterministically back
    into range instead of raising — there is always a nudge to show. Returns the banked
    ``NudgeHint`` unchanged (the bank is the single source of truth for the text).
    """
    if level is not HintLevel.NUDGE:
        raise NotImplementedError(
            f"hint level {level.value!r} is not implemented in this slice; "
            "partial_step / worked_step are Slice 5.6 (LLM slot-fill, SymPy-validated)"
        )

    nudges = NUDGE_BANK[kc]
    chosen_index = _ERROR_CATEGORY_INDEX[error_category] if error_category is not None else index
    return nudges[chosen_index % len(nudges)]


__all__ = [
    "NUDGE_BANK",
    "HintLevel",
    "NudgeHint",
    "select_nudge",
]
