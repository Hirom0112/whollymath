"""Hint orchestration — nudge bank (no LLM/SymPy) + validated LLM hint levels (Slices 3.8, 5.6).

This module owns the locked hint design (PROJECT.md §8 decision 0.D.3: hint levels are
``nudge`` / ``partial_step`` / ``worked_step``; "nudge (pre-written, no LLM, no SymPy)",
"partial_step and worked_step (LLM slot-fill → SymPy-validated → ≤2 retries → pre-written
fallback)"). It has two paths, by level:

  - **NUDGE (Slice 3.8)** — ``select_nudge`` over the pre-written ``NUDGE_BANK``: a
    conceptual prompt with NO LLM and NO SymPy (a nudge carries no numeric claim, so there
    is nothing to validate). ``select_nudge`` refuses the other two levels.
  - **PARTIAL_STEP / WORKED_STEP (Slice 5.6)** — ``build_validated_hint``: the domain's
    canonical worked-example text (``tutor/worked_example.py``) is rephrased warmly by the
    LLM (``persona_surface/hint_renderer.py``), then the rephrase must pass the SymPy
    numeric gate (``domain/hint_validation.py``) before it is shown; ≤2 retries, then the
    pre-written canonical text is the fallback. This path NEVER raises on a bad LLM result —
    it falls back (invariant 4). It refuses NUDGE (those come from ``select_nudge``).

This module is ORCHESTRATION only: it does NOT import SymPy or the LLM directly. SymPy
validation lives in ``domain/hint_validation.py`` (the only place SymPy is allowed besides
the rest of ``domain/``; CLAUDE.md §7); the LLM rephrase lives in
``persona_surface/hint_renderer.py`` (the only place an LLM is reached; §8.1). Both run on
help moments, off the sub-100ms turn loop.

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

from app.domain.hint_validation import extract_rationals, numeric_claims_preserved
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import Problem
from app.domain.verifier import ErrorCategory
from app.llm.provider import LLMProvider
from app.persona_surface.hint_renderer import render_hint_text
from app.tutor.worked_example import worked_example_for


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
    # Grade-6 Unit 1: index 0 (operation) orients toward comparing against the WHOLE, not the
    # other part; index 1 (magnitude) toward a part-of-the-whole being less than the whole.
    KnowledgeComponentId.RATIO_LANGUAGE: (
        _nudge(
            KnowledgeComponentId.RATIO_LANGUAGE,
            "A part OF the whole compares one colour to ALL the counters, not to the other colour.",
        ),
        _nudge(
            KnowledgeComponentId.RATIO_LANGUAGE,
            "Part of the whole is less than the whole — is your bottom number all of them?",
        ),
        _nudge(
            KnowledgeComponentId.RATIO_LANGUAGE,
            "Count every counter for the bottom; put just the asked colour on the top.",
        ),
    ),
    # Grade-6 Unit 1: index 0 (operation) orients toward which quantity is "per one"; index 1
    # (magnitude) toward the size of one share.
    KnowledgeComponentId.UNIT_RATE: (
        _nudge(
            KnowledgeComponentId.UNIT_RATE,
            "A unit rate is 'how much for ONE'. Which amount are you sharing, and across how many?",
        ),
        _nudge(
            KnowledgeComponentId.UNIT_RATE,
            "If that many together cost that much, is just one bigger or smaller than the total?",
        ),
        _nudge(
            KnowledgeComponentId.UNIT_RATE,
            "Split the total evenly into that many equal shares. How big is a single share?",
        ),
    ),
    # index 0 (operation) orients toward multiplying both parts by the same number; index 1
    # (magnitude) toward keeping the ratio's size.
    KnowledgeComponentId.EQUIVALENT_RATIOS: (
        _nudge(
            KnowledgeComponentId.EQUIVALENT_RATIOS,
            "To keep a ratio equal, do the SAME thing to both numbers. What did you do below?",
        ),
        _nudge(
            KnowledgeComponentId.EQUIVALENT_RATIOS,
            "Did you ADD the same amount, or MULTIPLY by the same amount? Only one keeps it equal.",
        ),
        _nudge(
            KnowledgeComponentId.EQUIVALENT_RATIOS,
            "How many times bigger is the new second number? Grow the first by that same many.",
        ),
    ),
    # index 0 (operation) orients toward "OF the whole, not the percent alone"; index 1 (magnitude).
    KnowledgeComponentId.PERCENT: (
        _nudge(
            KnowledgeComponentId.PERCENT,
            "A percent is a part OF the whole (out of one hundred), not the percent number alone.",
        ),
        _nudge(
            KnowledgeComponentId.PERCENT,
            "Is your answer bigger than the whole? A part of it should be smaller than the whole.",
        ),
        _nudge(
            KnowledgeComponentId.PERCENT,
            "Think of the whole as one hundred equal pieces. How many of those do you take?",
        ),
    ),
    # Grade-6 Unit 2 (T2): index 0 (operation) orients toward multiply-not-add; index 1
    # (magnitude) toward "a part of a part is smaller".
    KnowledgeComponentId.MULTIPLY_FRACTIONS: (
        _nudge(
            KnowledgeComponentId.MULTIPLY_FRACTIONS,
            "Multiply the tops, then the bottoms. You don't need a common denominator.",
        ),
        _nudge(
            KnowledgeComponentId.MULTIPLY_FRACTIONS,
            "A fraction OF a fraction is smaller. If your answer grew, you likely added.",
        ),
        _nudge(
            KnowledgeComponentId.MULTIPLY_FRACTIONS,
            "Two thirds of three quarters: multiply across, then simplify the result.",
        ),
    ),
    # Grade-6 Unit 2 (T2): index 0 (operation) orients toward flipping the divisor before
    # multiplying; index 1 (magnitude) toward "dividing by a part-of-one makes it bigger".
    KnowledgeComponentId.DIVIDE_FRACTIONS: (
        _nudge(
            KnowledgeComponentId.DIVIDE_FRACTIONS,
            "To divide by a fraction, FLIP the second one and multiply. Did you flip it?",
        ),
        _nudge(
            KnowledgeComponentId.DIVIDE_FRACTIONS,
            "Dividing by less than a whole makes the answer BIGGER. If yours shrank, did you flip?",
        ),
        _nudge(
            KnowledgeComponentId.DIVIDE_FRACTIONS,
            "How many of the second fraction fit inside the first? That count is the quotient.",
        ),
    ),
    # Grade-6 Unit 1: index 0 (operation) orients toward multiplying by the factor, not dividing;
    # index 1 (magnitude) toward "smaller units means MORE of them".
    KnowledgeComponentId.UNIT_CONVERSION: (
        _nudge(
            KnowledgeComponentId.UNIT_CONVERSION,
            "How many small units fit in ONE big unit? Build up from there for all of them.",
        ),
        _nudge(
            KnowledgeComponentId.UNIT_CONVERSION,
            "Smaller units means you need MORE of them. Did your answer get bigger or smaller?",
        ),
        _nudge(
            KnowledgeComponentId.UNIT_CONVERSION,
            "Each big unit is made of several small ones. Do you multiply by that many, or split?",
        ),
    ),
    # Grade-6 Unit 2: index 0 (operation) orients toward "factors versus multiples — which is
    # asked"; index 1 (magnitude) toward the relative size of each.
    KnowledgeComponentId.GCF_LCM: (
        _nudge(
            KnowledgeComponentId.GCF_LCM,
            "Are you asked for a factor (divides into both) or a multiple (both divide into it)?",
        ),
        _nudge(
            KnowledgeComponentId.GCF_LCM,
            "A common factor is no bigger than either number; a common multiple is no smaller.",
        ),
        _nudge(
            KnowledgeComponentId.GCF_LCM,
            "For the greatest common factor, find the biggest number that divides both evenly.",
        ),
    ),
    # Grade-6 Unit 2: index 0 (operation) orients toward "how many times does the divisor fit";
    # index 1 (magnitude) toward checking the place value of the quotient.
    KnowledgeComponentId.MULTI_DIGIT_DIVISION: (
        _nudge(
            KnowledgeComponentId.MULTI_DIGIT_DIVISION,
            "How many whole times does the divisor fit into the number? Work it place by place.",
        ),
        _nudge(
            KnowledgeComponentId.MULTI_DIGIT_DIVISION,
            "Check each quotient digit's place — a stray or missing zero throws the size way off.",
        ),
        _nudge(
            KnowledgeComponentId.MULTI_DIGIT_DIVISION,
            "Multiply your answer back by the divisor — does it land on the number you began with?",
        ),
    ),
    # Grade-6 Unit 2: index 0 (operation) orients toward counting place values; index 1
    # (magnitude) toward the size of the product when both factors are below one.
    KnowledgeComponentId.DECIMAL_OPERATIONS: (
        _nudge(
            KnowledgeComponentId.DECIMAL_OPERATIONS,
            "Count the decimal places in BOTH numbers — the product has that many altogether.",
        ),
        _nudge(
            KnowledgeComponentId.DECIMAL_OPERATIONS,
            "Two numbers below one multiply to something smaller — is the point in the right spot?",
        ),
        _nudge(
            KnowledgeComponentId.DECIMAL_OPERATIONS,
            "Multiply as whole numbers first, then place the point by the digits sitting after it.",
        ),
    ),
    # Grade-6 Unit 3: index 0 (operation) orients toward "distance from zero"; index 1 (magnitude)
    # toward "a distance is never negative".
    KnowledgeComponentId.ABSOLUTE_VALUE: (
        _nudge(
            KnowledgeComponentId.ABSOLUTE_VALUE,
            "Absolute value asks how FAR from zero a number sits — count the steps either way.",
        ),
        _nudge(
            KnowledgeComponentId.ABSOLUTE_VALUE,
            "A distance is never negative. Should your answer carry a minus sign?",
        ),
        _nudge(
            KnowledgeComponentId.ABSOLUTE_VALUE,
            "Picture the number on the line — how many steps back to zero, ignoring the side?",
        ),
    ),
    # Grade-6 Unit-INT: index 0 (operation) orients toward combining WITH the signs, not adding
    # magnitudes; index 1 (magnitude) toward "opposite signs partly cancel, so it's smaller".
    KnowledgeComponentId.INTEGER_ADD_SUBTRACT: (
        _nudge(
            KnowledgeComponentId.INTEGER_ADD_SUBTRACT,
            "Opposite signs pull in opposite directions — they partly cancel, not pile up.",
        ),
        _nudge(
            KnowledgeComponentId.INTEGER_ADD_SUBTRACT,
            "Start at the first number and move by the second — which way does its sign send you?",
        ),
        _nudge(
            KnowledgeComponentId.INTEGER_ADD_SUBTRACT,
            "If you just added the sizes, you ignored the signs. The result should be smaller.",
        ),
    ),
    # Grade-6 Unit 3: index 0 (operation) orients toward flipping the sign across zero; index 1
    # (magnitude) toward "same distance from zero, other side".
    KnowledgeComponentId.SIGNED_NUMBERS: (
        _nudge(
            KnowledgeComponentId.SIGNED_NUMBERS,
            "The opposite flips the sign across zero — a negative becomes positive, and back.",
        ),
        _nudge(
            KnowledgeComponentId.SIGNED_NUMBERS,
            "An opposite sits the same distance from zero, on the other side. Did the sign change?",
        ),
        _nudge(
            KnowledgeComponentId.SIGNED_NUMBERS,
            "If you wrote the same number back, you forgot to flip it to the other side of zero.",
        ),
    ),
    # Grade-6 Unit 4: index 0 (operation) orients toward the operation AND its order; index 1
    # reinforces that order matters for subtraction and division.
    KnowledgeComponentId.WRITE_EXPRESSIONS: (
        _nudge(
            KnowledgeComponentId.WRITE_EXPRESSIONS,
            "Which operation do the words name, and which quantity comes first?",
        ),
        _nudge(
            KnowledgeComponentId.WRITE_EXPRESSIONS,
            "For 'less than' or 'divided by', the order flips — start from what you take from.",
        ),
        _nudge(
            KnowledgeComponentId.WRITE_EXPRESSIONS,
            "Let a letter stand for the unknown, then build the phrase piece by piece.",
        ),
    ),
    # Grade-6 Unit 4: index 0 (operation) orients toward precedence — multiply before you add;
    # index 1 reinforces substituting first, then evaluating in the right order.
    KnowledgeComponentId.EVALUATE_EXPRESSIONS: (
        _nudge(
            KnowledgeComponentId.EVALUATE_EXPRESSIONS,
            "Multiply before you add — handle the times part first, then add what's left.",
        ),
        _nudge(
            KnowledgeComponentId.EVALUATE_EXPRESSIONS,
            "Put the value in for the letter first, then work the operations in the right order.",
        ),
        _nudge(
            KnowledgeComponentId.EVALUATE_EXPRESSIONS,
            "If you added before multiplying, the order slipped — the times part comes first.",
        ),
    ),
    # Grade-6 Unit 5: index 0 (operation) orients toward the INVERSE that undoes the equation;
    # index 1 (magnitude) toward checking x by putting it back in.
    KnowledgeComponentId.ONE_STEP_EQUATIONS: (
        _nudge(
            KnowledgeComponentId.ONE_STEP_EQUATIONS,
            "To get x alone, do the OPPOSITE of what is done to it — undo adding by subtracting, "
            "undo multiplying by dividing.",
        ),
        _nudge(
            KnowledgeComponentId.ONE_STEP_EQUATIONS,
            "Whatever you do to one side, do to the other so the equation stays balanced.",
        ),
        _nudge(
            KnowledgeComponentId.ONE_STEP_EQUATIONS,
            "Put your value for x back in — if both sides come out equal, you solved it.",
        ),
    ),
    # Grade-6 Unit 4: index 0 (operation) orients toward distributing to EVERY term; index 1
    # reinforces that the value must stay the same.
    KnowledgeComponentId.EQUIVALENT_EXPRESSIONS: (
        _nudge(
            KnowledgeComponentId.EQUIVALENT_EXPRESSIONS,
            "Multiply the outside number by EVERY term inside the parentheses, not just the first.",
        ),
        _nudge(
            KnowledgeComponentId.EQUIVALENT_EXPRESSIONS,
            "An equivalent expression has the same value — try a number for the letter to check.",
        ),
        _nudge(
            KnowledgeComponentId.EQUIVALENT_EXPRESSIONS,
            "Like terms (same letter) combine; a letter term and a plain number do not.",
        ),
    ),
    # Grade-6 Unit 5: index 0 (operation) orients toward the DIRECTION of the inequality; the others
    # reinforce boundary inclusion and naming the unknown.
    KnowledgeComponentId.INEQUALITIES: (
        _nudge(
            KnowledgeComponentId.INEQUALITIES,
            "Which way should it point — are the allowed values above or below the number?",
        ),
        _nudge(
            KnowledgeComponentId.INEQUALITIES,
            "Does the boundary count? 'At least' and 'at most' include it; 'more than' does not.",
        ),
        _nudge(
            KnowledgeComponentId.INEQUALITIES,
            "Let a letter stand for the number, then ask which values the words allow.",
        ),
    ),
    # Grade-6 Unit 3: index 0 orients to the (x, y) order; index 1 to the sign-per-quadrant idea;
    # index 2 to reflection as a sign flip on one axis.
    KnowledgeComponentId.COORDINATE_PLANE: (
        _nudge(
            KnowledgeComponentId.COORDINATE_PLANE,
            "The first number moves you across (x); the second moves you up or down (y).",
        ),
        _nudge(
            KnowledgeComponentId.COORDINATE_PLANE,
            "A negative coordinate means left (for x) or down (for y) from the center.",
        ),
        _nudge(
            KnowledgeComponentId.COORDINATE_PLANE,
            "Reflecting across an axis flips the sign of just one coordinate — keep the other.",
        ),
    ),
    # Grade-6 Unit 3 (TEKS 6.2A): index 0 (operation) orients toward the nested-subset rule; index
    # 1 reinforces that every integer (and whole number) is also rational.
    KnowledgeComponentId.CLASSIFY_NUMBER_SETS: (
        _nudge(
            KnowledgeComponentId.CLASSIFY_NUMBER_SETS,
            "The sets nest — a number in a smaller set is in every set that contains it.",
        ),
        _nudge(
            KnowledgeComponentId.CLASSIFY_NUMBER_SETS,
            "Every integer can be written as a fraction over one, so every integer is rational.",
        ),
        _nudge(
            KnowledgeComponentId.CLASSIFY_NUMBER_SETS,
            "Counting numbers are whole; whole numbers add zero; integers add the negatives.",
        ),
    ),
    # Grade-6 Unit 4 (6.EE.2b): index 0 (operation) orients toward which part is being named; the
    # rest separate the coefficient (the number multiplying the variable) from the constant (the
    # number on its own) and the terms (the parts joined by + or -).
    KnowledgeComponentId.EXPRESSION_PARTS: (
        _nudge(
            KnowledgeComponentId.EXPRESSION_PARTS,
            "Read which part is asked — the coefficient, the constant, or how many terms.",
        ),
        _nudge(
            KnowledgeComponentId.EXPRESSION_PARTS,
            "The coefficient is the number multiplying a variable; the constant stands on its own.",
        ),
        _nudge(
            KnowledgeComponentId.EXPRESSION_PARTS,
            "Terms are the parts joined by plus or minus signs — count those to find how many.",
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
      ``worked_step`` are NOT nudges — they are built by ``build_validated_hint`` (Slice
      5.6: LLM slot-fill → SymPy-validated → fallback). Asking ``select_nudge`` for one is
      a caller error, so we fail loudly (CLAUDE.md §8.5) and point at the right path.
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
            f"hint level {level.value!r} is not a nudge; "
            "partial_step / worked_step are built by build_validated_hint (Slice 5.6)"
        )

    nudges = NUDGE_BANK[kc]
    chosen_index = _ERROR_CATEGORY_INDEX[error_category] if error_category is not None else index
    return nudges[chosen_index % len(nudges)]


# ─── Slice 5.6: the LLM-rephrased, SymPy-validated hint levels ───────────────


@dataclass(frozen=True)
class Hint:
    """One ``partial_step`` / ``worked_step`` hint after the 5.6 validate-or-fallback pipeline.

    Frozen and hashable (tuple ``slots``, like ``NudgeHint`` / ``WorkedStep``) — a produced
    hint is a fact about a help moment, not mutable state (CLAUDE.md §8.4). Distinct from
    ``NudgeHint``: a nudge is a banked conceptual prompt with no numbers; a ``Hint`` carries
    the validated math copy and the record of how it was produced. Fields:

    - ``kc``               which knowledge component this hint is for.
    - ``level``            ``PARTIAL_STEP`` or ``WORKED_STEP`` (never ``NUDGE`` here).
    - ``template_id``      the stable id of the path taken: ``<level>_llm_v1`` when an
      LLM rephrase passed the gate, ``<level>_fallback_v1`` when the canonical text was used.
      A decision-log breadcrumb (which surface the learner actually saw).
    - ``slots``            the validated symbolic facts as ``(name, value)`` string pairs —
      the distinct canonical numbers named ``slot0``, ``slot1``, … Kept as a tuple so the
      dataclass stays hashable. This is the record of WHAT was held invariant through the
      rephrase (the numbers the SymPy gate enforced).
    - ``natural_language`` the kid-facing text actually shown: the validated LLM rephrase, or
      the canonical fallback text.
    - ``llm_used``         True iff a gate-passing LLM rephrase is what we returned; False
      when we fell back to the deterministic canonical text.
    """

    kc: KnowledgeComponentId
    level: HintLevel
    template_id: str
    slots: tuple[tuple[str, str], ...]
    natural_language: str
    llm_used: bool


# The maximum length of a piece of free-form hint copy we will show a learner. A worked
# walkthrough of a few short numbered steps is well under this; anything dramatically longer
# is a runaway/garbled completion, not a hint. Named so the bound is reviewable, not magic.
MAX_HINT_COPY_CHARS = 1200


def is_safe_copy(text: str) -> bool:
    """A pure string safety filter on free-form hint copy (decision 5.6.4) — no LLM, no SymPy.

    WHY this exists: ``render_hint_text`` returns model-generated prose, and even after the
    SymPy numeric gate confirms the *numbers* are intact, we still want a cheap, deterministic
    sanity check on the *copy itself* before showing it to a child. This is intentionally
    minimal (CLAUDE.md §8.5/§8.6 — clarity over cleverness, no premature machinery): we
    require the text to be non-empty after stripping and not absurdly long (a runaway
    completion). Numeric correctness is NOT this function's job — that is the SymPy gate's
    (``numeric_claims_preserved``); content faithfulness is the prompt's. Keeping this a tiny,
    obvious string check is the point.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) > MAX_HINT_COPY_CHARS:
        return False
    return True


def _canonical_hint_text(problem: Problem, level: HintLevel) -> str:
    """The verified-correct canonical text for a hint ``level``, from the worked example.

    PARTIAL_STEP shows the FIRST canonical step only (a single nudge toward the procedure);
    WORKED_STEP shows the whole canonical procedure as a short numbered walkthrough. Both
    come straight from ``worked_example_for`` — each ``WorkedStep.shown`` is already
    SymPy-grounded canonical text (the correctness authority stays in ``domain/``; §8.2).
    """
    steps = worked_example_for(problem).steps
    if level is HintLevel.PARTIAL_STEP:
        return steps[0].shown
    # WORKED_STEP: a short numbered walkthrough of every canonical step.
    return "\n".join(f"{i}. {step.shown}" for i, step in enumerate(steps, start=1))


def _canonical_slots(canonical_text: str) -> tuple[tuple[str, str], ...]:
    """Name the canonical text's distinct numbers slot0, slot1, … (the validated-facts record).

    The symbolic facts are the distinct ``Rational`` values the SymPy gate holds invariant
    through the rephrase (``extract_rationals`` in ``domain/hint_validation.py``). We sort
    them for a deterministic order (PROJECT.md §4.1) and stringify each as a stable ``a/b``
    (or integer) form, kept as ``(name, value)`` pairs so ``Hint`` stays hashable.
    """
    values = sorted(extract_rationals(canonical_text), key=lambda r: (int(r.p), int(r.q)))
    return tuple(
        (f"slot{i}", str(value) if value.q != 1 else str(int(value.p)))
        for i, value in enumerate(values)
    )


def build_validated_hint(
    problem: Problem,
    level: HintLevel,
    *,
    provider: LLMProvider | None = None,
    max_retries: int = 2,
) -> Hint:
    """Build a ``partial_step`` / ``worked_step`` hint via the locked 5.6 pipeline.

    The pipeline (decision 0.D.3): take the domain's verified-correct canonical text, let the
    LLM rephrase it warmly (``render_hint_text``), and show the rephrase ONLY if it is safe
    copy (``is_safe_copy``) AND preserves every numeric claim (``numeric_claims_preserved``,
    the SymPy gate). Up to ``1 + max_retries`` attempts; if none pass — or if no provider is
    wired — return the canonical text as the pre-written fallback. This path NEVER raises on a
    bad LLM result; a failed rephrase costs naturalness, never the hint (invariant 4).

    ``level is NUDGE`` raises ``ValueError``: nudges come from ``select_nudge``, not this path.
    Knowledge-state-blind (§8.3): the LLM sees only the canonical text, never mastery state.
    """
    if level is HintLevel.NUDGE:
        raise ValueError(
            "build_validated_hint is for partial_step / worked_step only; "
            "use select_nudge for NUDGE hints"
        )

    canonical_text = _canonical_hint_text(problem, level)
    slots = _canonical_slots(canonical_text)

    def _fallback() -> Hint:
        return Hint(
            kc=problem.kc,
            level=level,
            template_id=f"{level.value}_fallback_v1",
            slots=slots,
            natural_language=canonical_text,
            llm_used=False,
        )

    if provider is None:
        return _fallback()

    for _ in range(1 + max_retries):
        candidate = render_hint_text(canonical_text, provider=provider)
        if is_safe_copy(candidate) and numeric_claims_preserved(canonical_text, candidate):
            return Hint(
                kc=problem.kc,
                level=level,
                template_id=f"{level.value}_llm_v1",
                slots=slots,
                natural_language=candidate,
                llm_used=True,
            )

    return _fallback()


__all__ = [
    "MAX_HINT_COPY_CHARS",
    "NUDGE_BANK",
    "Hint",
    "HintLevel",
    "NudgeHint",
    "build_validated_hint",
    "is_safe_copy",
    "select_nudge",
]
