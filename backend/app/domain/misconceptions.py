"""Layer-1 misconception catalog + deterministic wrong-answer generators.

This is Slice 1.2 of the domain model (ARCHITECTURE.md §5 Layer 1; PROJECT.md
§4.1, §4.2). It hangs off the KC registry (`knowledge_components.py`, Slice 1.1)
and is the single source of truth for *the named ways a learner gets a fraction
problem wrong*. The mastery model, the persona behavioral simulator (Layer 3),
and the transfer test all reference these same misconception ids, exactly as they
all reference the same KC ids — keeping them in one registry is what makes that
reference unambiguous.

Two things live here, and nothing else:

  (a) the five named misconceptions as typed, immutable domain objects, with ids
      matching `diagnostic_gems.json` `_meta.misconception_catalog` verbatim; and
  (b) deterministic functions that, given a fraction problem, produce the SPECIFIC
      wrong answer that misconception yields.

Each generator is grounded in RESEARCH.md §1.2 (the fraction-misconception
catalog) and is verified against the gem bank's SymPy-computed
`wrong_answer_produced` oracle values (RESEARCH.md §6) in the test suite.

SymPy IS used here for fraction arithmetic — this is `domain/`, the one place
math correctness lives (CLAUDE.md §7, ARCHITECTURE.md §14 invariant 5), and we use
`sympy.Rational` to stay consistent with the verifier (Slice 1.4). There is NO LLM
and NO DB anywhere in this module (CLAUDE.md §8.1/§8.2): the generators are pure
and deterministic — same input, same output, every time, which is what makes the
persona harness reproducible (ARCHITECTURE.md §5 Layer 3).

A note on what these generators are NOT: they are not problem generators (Slice
1.3) and not the answer verifier (Slice 1.4). They take a problem's operands as
input and return the wrong answer a misconception produces; building the problems
and judging correctness are separate, later slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId

# A yes/no judgment is the answer type for the relational "are these the same
# amount?" items (the gem bank's `type: yes_no`). Aliased for readability.
YesNo = Literal["yes", "no"]


class MisconceptionId(StrEnum):
    """Stable misconception identifiers, matching the gem bank verbatim.

    The string VALUES match `diagnostic_gems.json` `_meta.misconception_catalog`
    exactly; they are the join key between this module, the bank, and the persona
    configs (Layer 2). As with ``KnowledgeComponentId``, ``StrEnum`` lets a member
    serialize as its catalog string while still giving typed code a real handle.
    Changing a VALUE is a breaking change to that contract.
    """

    NATURAL_NUMBER_BIAS = "natural-number-bias"
    ADD_ACROSS_ERROR = "add-across-error"
    REDUCE_MEANS_SMALLER = "reduce-means-smaller"
    EQUAL_SIGN_AS_PROCEDURAL = "equal-sign-as-procedural"
    PROCEDURE_WITHOUT_CONCEPT = "procedure-without-concept"
    # Grade-6 content build (2026-05-30): misconceptions for the new KCs are NOT in the
    # fraction-only diagnostic_gems bank — they enter with their lesson (the bank's verbatim
    # match holds only for the five fraction misconceptions above).
    RATE_INVERSION = "rate-inversion"
    ADDITIVE_RATIO = "additive-ratio"
    PERCENT_AS_AMOUNT = "percent-as-amount"
    # Unit 2 (T2): treating fraction multiplication like addition (x as +).
    MULTIPLY_AS_ADD = "multiply-as-add"
    # Unit 1: applying the conversion factor upside-down — dividing (or flipping the factor)
    # when converting to the SMALLER unit, where you should multiply.
    CONVERSION_INVERSION = "conversion-inversion"
    # Unit 1 (6.RP.1): confusing a part-part ratio with a part-whole ratio (and vice versa).
    PART_PART_WHOLE_CONFUSION = "part-part-whole-confusion"


@dataclass(frozen=True)
class Misconception:
    """One named misconception: a documented way learners get fractions wrong.

    Frozen because Layer 1 is a source of truth, not mutable state — nothing
    downstream may rewrite what a misconception *is* at runtime (ARCHITECTURE.md
    §14, CLAUDE.md §8.4). ``applicable_kcs`` is a tuple (not a list) so the object
    is hashable and genuinely immutable; it references ``KnowledgeComponentId`` so
    the misconception and the KC registry speak the same ids.

    The fields are the minimal Slice-1.2 surface: a stable id, human-readable name
    and description (each traceable to RESEARCH.md §1.2), and which KCs the
    misconception can show up on. The wrong-answer *behavior* is the generator
    functions below, not data stored on the object — a misconception's effect
    depends on the specific problem, so it cannot be a fixed field.
    """

    id: MisconceptionId
    name: str
    description: str
    applicable_kcs: tuple[KnowledgeComponentId, ...]


# The five misconceptions, in the gem-bank catalog order (PROJECT.md §4.2,
# RESEARCH.md §1.2). The ``applicable_kcs`` for each reflect how the bank actually
# probes them (RESEARCH.md §6.1 "Items per misconception" table), which in turn
# traces to the persona designs (PROJECT.md §4.2):
#
#   - natural-number-bias is the headline misconception and the umbrella mechanism
#     behind operate-on-parts-separately errors, so it spans comparison/equivalence,
#     common-denominator finding, subtraction, and number-line placement.
#   - add-across-error is reserved strictly for the literal tops+tops / bottoms+
#     bottoms ADDITION error (RESEARCH.md §6.4) — KC_addition_unlike only.
#   - reduce-means-smaller and equal-sign-as-procedural are equivalence-judgment
#     errors (KC_equivalence).
#   - procedure-without-concept can occur on any KC where a procedure can be run
#     rotely; the bank probes it on equivalence, common-denominator, subtraction,
#     and number-line items.
_MISCONCEPTIONS: tuple[Misconception, ...] = (
    Misconception(
        id=MisconceptionId.NATURAL_NUMBER_BIAS,
        name="Natural-number bias",
        description=(
            "Treats a fraction's numerator and denominator as two independent "
            "whole numbers, so a bigger denominator is read as a bigger amount "
            "(believing 1/6 > 1/2 because 6 > 2). Drives magnitude/comparison "
            "errors, number-line misplacement, and the operate-on-the-parts-"
            "separately errors in common-denominator finding and subtraction."
        ),
        applicable_kcs=(
            KnowledgeComponentId.EQUIVALENCE,
            KnowledgeComponentId.COMMON_DENOMINATOR,
            KnowledgeComponentId.SUBTRACTION_UNLIKE,
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        ),
    ),
    Misconception(
        id=MisconceptionId.ADD_ACROSS_ERROR,
        name="Add-across error",
        description=(
            "Adds the numerators and the denominators separately, so "
            "a/b + c/d becomes (a+c)/(b+d) — e.g. 1/4 + 1/4 = 2/8. A special case "
            "of treating the parts as independent whole numbers, reserved here for "
            "the literal addition form."
        ),
        applicable_kcs=(KnowledgeComponentId.ADDITION_UNLIKE,),
    ),
    Misconception(
        id=MisconceptionId.REDUCE_MEANS_SMALLER,
        name="Reduce-means-smaller",
        description=(
            "Believes that naming a fraction with smaller numbers (e.g. simplifying "
            "6/8 to 3/4) makes it a smaller amount, so two equal fractions written "
            "differently are judged unequal."
        ),
        applicable_kcs=(KnowledgeComponentId.EQUIVALENCE,),
    ),
    Misconception(
        id=MisconceptionId.EQUAL_SIGN_AS_PROCEDURAL,
        name="Equal-sign-as-procedural",
        description=(
            "Reads '=' as 'compute and write the answer' rather than as a relational "
            "'these name the same amount'. On an 'are these the same?' item there is "
            "nothing to compute, so the learner has no procedure to run and defaults "
            "to 'no'."
        ),
        applicable_kcs=(KnowledgeComponentId.EQUIVALENCE,),
    ),
    Misconception(
        id=MisconceptionId.PROCEDURE_WITHOUT_CONCEPT,
        name="Procedure-without-concept",
        description=(
            "Runs a memorized algorithm correctly but cannot say why it works, "
            "cannot judge whether an answer is reasonable, and fails error-finding "
            "items. Produces the CORRECT numeric answer on routine items — the "
            "tell is the missing justification, not a wrong number."
        ),
        applicable_kcs=(
            KnowledgeComponentId.EQUIVALENCE,
            KnowledgeComponentId.COMMON_DENOMINATOR,
            KnowledgeComponentId.ADDITION_UNLIKE,
            KnowledgeComponentId.SUBTRACTION_UNLIKE,
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        ),
    ),
    Misconception(
        id=MisconceptionId.RATE_INVERSION,
        name="Rate inversion",
        description=(
            "Forms the rate with the quantities upside-down — divides the per-unit "
            "count by the total instead of the total by the count, so '$6 for 3 lbs' "
            "becomes 3/6 = $0.50 per lb instead of 6/3 = $2 per lb. The learner sets up "
            "the ratio but loses track of which quantity is 'per 1'."
        ),
        applicable_kcs=(KnowledgeComponentId.UNIT_RATE,),
    ),
    Misconception(
        id=MisconceptionId.ADDITIVE_RATIO,
        name="Additive ratio reasoning",
        description=(
            "Scales a ratio by ADDING the same amount to both terms instead of "
            "MULTIPLYING — so 3:4 = ?:12 becomes 11 (add 8 to each) rather than 9 "
            "(multiply by 3). The classic additive-vs-multiplicative error: the learner "
            "preserves the difference instead of the multiplicative relationship."
        ),
        applicable_kcs=(KnowledgeComponentId.EQUIVALENT_RATIOS,),
    ),
    Misconception(
        id=MisconceptionId.PERCENT_AS_AMOUNT,
        name="Percent as amount",
        description=(
            "Reports the percent NUMBER itself as the answer instead of computing that "
            "percent OF the whole — '30% of 50' becomes 30, not 15. The learner does not "
            "engage the base; the percent is read as an absolute count."
        ),
        applicable_kcs=(KnowledgeComponentId.PERCENT,),
    ),
    Misconception(
        id=MisconceptionId.MULTIPLY_AS_ADD,
        name="Multiply as add",
        description=(
            "Treats fraction multiplication like addition: instead of multiplying the "
            "numerators and denominators (2/3 x 3/4 = 6/12), the learner adds the fractions "
            "(2/3 + 3/4). The operation is confused, so the result is too big — a product of "
            "two proper fractions is smaller than either factor, never larger."
        ),
        applicable_kcs=(KnowledgeComponentId.MULTIPLY_FRACTIONS,),
    ),
    Misconception(
        id=MisconceptionId.CONVERSION_INVERSION,
        name="Conversion-factor inversion",
        description=(
            "Applies the conversion factor the wrong way round when converting to the smaller "
            "unit: DIVIDES by the factor (or flips it) instead of multiplying, so '4 feet' at "
            "12 inches per foot becomes 4/12 instead of 4 x 12 = 48. The learner has the right "
            "factor but loses track of which way the conversion goes."
        ),
        applicable_kcs=(KnowledgeComponentId.UNIT_CONVERSION,),
    ),
    Misconception(
        id=MisconceptionId.PART_PART_WHOLE_CONFUSION,
        name="Part-part vs part-whole confusion",
        description=(
            "Confuses a part-to-part ratio with a part-to-whole ratio. Asked for the "
            "part-OF-the-whole (3 red of 8 total = 3/8), the learner reports the "
            "part-TO-part comparison instead (3 red to 5 blue = 3/5). The two quantities "
            "are both legitimate ratios, but they answer different questions — the learner "
            "loses track of whether the comparison is against the other part or the whole."
        ),
        applicable_kcs=(KnowledgeComponentId.RATIO_LANGUAGE,),
    ),
)


class MisconceptionRegistry:
    """The single, ordered, deduplicated home for the five misconceptions.

    Mirrors ``KnowledgeComponentRegistry`` (Slice 1.1): construction enforces id
    uniqueness so a duplicate fails fast at import time; lookups accept either a
    ``MisconceptionId`` or its raw catalog string, because both the bank/DB
    (strings) and typed code (enum) need to resolve a misconception.
    """

    def __init__(self, misconceptions: tuple[Misconception, ...]) -> None:
        by_id: dict[MisconceptionId, Misconception] = {}
        for misconception in misconceptions:
            if misconception.id in by_id:
                raise ValueError(f"Duplicate misconception id: {misconception.id.value}")
            by_id[misconception.id] = misconception
        # Preserve declared (catalog) order for deterministic iteration.
        self._by_id = by_id

    def all(self) -> tuple[Misconception, ...]:
        """Every misconception, in the registry's declared (catalog) order."""
        return tuple(self._by_id.values())

    def get(self, misconception_id: MisconceptionId | str) -> Misconception:
        """Resolve a misconception by enum member or raw catalog string.

        Raises ``KeyError`` naming the offending id on an unknown misconception,
        so callers get a clear failure instead of a silent ``None`` (CLAUDE.md
        §8.5: write for the reader).
        """
        if isinstance(misconception_id, MisconceptionId):
            return self._by_id[misconception_id]
        try:
            resolved = MisconceptionId(misconception_id)
        except ValueError as exc:
            raise KeyError(f"Unknown misconception id: {misconception_id!r}") from exc
        return self._by_id[resolved]


# The module-level registry is the single source of truth referenced across the
# system. Built once at import; immutable contents.
MISCONCEPTION_REGISTRY = MisconceptionRegistry(_MISCONCEPTIONS)


def get_misconception(misconception_id: MisconceptionId | str) -> Misconception:
    """Module-level shortcut for ``MISCONCEPTION_REGISTRY.get`` (the common case)."""
    return MISCONCEPTION_REGISTRY.get(misconception_id)


# ─── Wrong-answer result types ──────────────────────────────────────────────
#
# These small frozen types are what the generators return. They are deliberately
# richer than a bare value so a downstream caller (the persona simulator, the
# tutor's diagnostic log) can see BOTH the raw, possibly-impossible form the
# learner produced AND its rational value. The bank records both (RESEARCH.md
# §6.5: "records both the raw student-produced form and its reduced value"), so
# we preserve both rather than normalizing the impossibility away.


@dataclass(frozen=True)
class WrongFraction:
    """A fraction a learner produced, kept in its RAW (unreduced, possibly-

    impossible) form. The across errors can yield a zero or negative denominator
    (e.g. 1/-3 from subtracting bottoms); that impossibility is the diagnostic
    signal, so we never silently normalize it. ``as_rational`` gives the SymPy
    value for comparison and verification.
    """

    numerator: int
    denominator: int

    def as_rational(self) -> Rational:
        """The SymPy value of this raw fraction (reduces/normalizes sign).

        Used for VALUE comparison against the bank's oracle (e.g. raw 2/8 == 1/4).
        ``Rational`` happily represents a negative denominator as a negative value
        (1/-3 -> -1/3); a zero denominator is genuinely undefined and SymPy raises,
        which correctly surfaces the impossibility rather than hiding it.
        """
        return Rational(self.numerator, self.denominator)


@dataclass(frozen=True)
class NumberLineMisplacement:
    """Where natural-number-bias drops a fraction's marker vs. where it belongs.

    ``true_value`` is the correct position on the 0–1 line; ``biased_position`` is
    where the bias places it by reading the digits (typically the denominator) as
    a whole-number position. The two differing is the whole point.
    """

    true_value: Rational
    biased_position: Rational


@dataclass(frozen=True)
class EqualSignVerdict:
    """The equal-sign-as-procedural answer on a relational same-amount item.

    ``answer`` is the yes/no the learner gives; ``tried_to_compute`` records
    whether they found an operation to run. On a relational item there is nothing
    to compute, so they default to 'no' with ``tried_to_compute=False`` — that is
    the operational-reading signature (RESEARCH.md §1.2; McNeil et al. 2006).
    """

    answer: YesNo
    tried_to_compute: bool


@dataclass(frozen=True)
class ProcedureWithoutConceptResult:
    """The procedure-without-concept marker (PROJECT.md §4.2 Persona 2 — Priya).

    Crucially this is NOT a fabricated wrong number. The procedural learner gets
    the routine answer RIGHT (``answer`` is the correct value), but cannot justify
    it and fails error-finding — so ``can_justify`` is always ``False``. Modeling
    this as a marker, not a wrong value, is the nuance the brief calls out: the
    mastery model must distinguish procedural fluency from conceptual understanding
    (PROJECT.md §3.4, §3.9), and it can only do that if the persona's *answer* is
    correct while a separate flag reports the missing justification.
    """

    answer: object
    can_justify: bool


# ─── Generators ─────────────────────────────────────────────────────────────


def add_across(num1: int, den1: int, num2: int, den2: int) -> WrongFraction:
    """add-across-error: a/b + c/d -> (a+c)/(b+d).

    The learner adds tops and bottoms separately, treating the parts as
    independent whole numbers (RESEARCH.md §1.2; Aksoy & Yazlik 2017; Braithwaite
    & Siegler 2018). E.g. 1/4 + 1/4 -> 2/8, the canonical Surface-Sam error named
    verbatim in PROJECT.md §4.2. The result is returned raw; for 1/2 + 1/4 that is
    2/6 (which reduces to 1/3, smaller than either addend — an impossibility for a
    sum, and exactly the diagnostic tell).
    """
    return WrongFraction(numerator=num1 + num2, denominator=den1 + den2)


def additive_ratio(known_num: int, known_den: int, target_den: int) -> Rational:
    """additive-ratio: scale a:b -> ?:target_den by ADDING (target_den - b) to a, not multiplying.

    The learner preserves the DIFFERENCE instead of the multiplicative relationship, so
    3:4 -> ?:12 gives 3 + (12 - 4) = 11 rather than 3 * 3 = 9. Returned as a Rational so the
    verifier compares values directly (it equals the correct multiplicative answer only in the
    degenerate target_den == 2*b case, which the generator avoids).
    """
    return Rational(known_num + (target_den - known_den))


def part_part_ratio(part: int, other: int) -> Rational:
    """part-part-whole confusion: report the part-TO-part ratio ``part/other`` when the

    part-TO-whole ratio ``part/(part+other)`` was asked. Given "3 red, 5 blue", asked for the
    fraction of counters that are red (3/8), the learner answers the red-to-blue comparison
    instead (3/5). Returned as a SymPy ``Rational`` so the verifier compares values directly; it
    is always distinct from the correct part-whole value because ``other != part + other`` for
    any ``part >= 1``.
    """
    return Rational(part, other)


def invert_rate(total: int, count: int) -> Rational:
    """rate-inversion: form the unit rate upside-down — ``count/total`` not ``total/count``.

    The correct unit rate for ``total`` per ``count`` units is ``total/count`` ("how much for
    ONE"). The learner who inverts divides the other way, getting ``count/total`` — e.g. $6 for
    3 lbs becomes 3/6 = 1/2 instead of 6/3 = 2. Returned as a SymPy ``Rational`` (a rate is a
    single magnitude, not a fraction pair), so the verifier can compare values directly.
    """
    return Rational(count, total)


def invert_conversion(quantity: int, factor: int) -> Rational:
    """conversion-inversion: convert to the smaller unit by DIVIDING by the factor, not multiplying.

    The correct conversion of ``quantity`` larger units to the smaller unit (``factor`` small units
    per large unit) is ``quantity * factor`` ("how many small units"). The learner who inverts
    divides the other way, getting ``quantity/factor`` — e.g. 4 feet at 12 in/ft becomes 4/12 = 1/3
    instead of 48. Returned as a SymPy ``Rational`` so the verifier can compare values directly.
    """
    return Rational(quantity, factor)


def subtract_across(num1: int, den1: int, num2: int, den2: int) -> WrongFraction:
    """natural-number-bias on subtraction: a/b - c/d -> (a-c)/(b-d).

    The subtraction analog of the across error: the learner operates on the parts
    separately (RESEARCH.md §1.2, §6.4 — relabeled natural-number-bias rather than
    add-across, a deliberate citation-honesty choice). The denominator subtraction
    can go zero or negative (e.g. 2/3 - 1/6 -> 1/-3), which is meaningless for a
    piece size; we keep it raw because that impossibility is the signal the bank
    records and the number line / area model expose.
    """
    return WrongFraction(numerator=num1 - num2, denominator=den1 - den2)


def natural_number_bias_compare(
    frac1: tuple[int, int],
    frac2: tuple[int, int],
) -> tuple[int, int]:
    """natural-number-bias on magnitude: which fraction the learner judges LARGER.

    The learner reads each fraction as two whole numbers. The denominator carries
    the dominant 'how big' signal (the most-documented error — a larger denominator
    is read as a larger amount; RESEARCH.md §1.2, Gabriel et al. 2013), so we
    compare denominators first; on a tie (same bottom) we fall back to comparing
    numerators as whole numbers. Returns whichever fraction the bias deems bigger —
    which is wrong precisely when the bigger-denominator fraction is the smaller
    magnitude (1/6 vs 1/2 -> the bias picks 1/6).
    """
    _, den1 = frac1
    _, den2 = frac2
    if den1 != den2:
        return frac1 if den1 > den2 else frac2
    # Same denominator: the digits that differ are the numerators, so the bias
    # (correctly, here) picks the bigger numerator — but for the same WHOLE-number
    # reason, not magnitude reasoning.
    num1, _ = frac1
    num2, _ = frac2
    return frac1 if num1 >= num2 else frac2


def natural_number_bias_number_line(num: int, den: int) -> NumberLineMisplacement:
    """natural-number-bias on number-line placement: place by the digits.

    The learner reads the denominator as a whole-number position rather than the
    fraction's magnitude, so the marker lands near the denominator value — off the
    0–1 line for 1/2 (lands near 2) and far to the right for 1/8 (reads 8 as
    'big'), though 1/8 is one of the smallest amounts (RESEARCH.md §1.2; Braithwaite
    & Siegler 2018 number-line estimation; Gabriel et al. 2013 large-denominator
    case). ``biased_position`` is expressed as a Rational so it can be compared to
    the true value uniformly.
    """
    return NumberLineMisplacement(
        true_value=Rational(num, den),
        biased_position=Rational(den),  # the denominator read as a whole-number position
    )


def reduce_means_smaller_judges_same(
    frac1: tuple[int, int],
    frac2: tuple[int, int],
) -> YesNo:
    """reduce-means-smaller on an 'are these the same amount?' item.

    Defined over a pair the learner is asked to judge equal. A learner who believes
    that the form with smaller numbers (the reduced form) names a smaller amount
    concludes the two are NOT the same, answering 'no' — even though they are equal
    (RESEARCH.md §1.2; Barbieri et al. 2024). Every reduce-means-smaller probe in
    the bank (EQ-005, EQ-006, EQ-010) is exactly such an equal pair, so the wrong
    answer is uniformly 'no'. The pair is taken as input (rather than hard-coded)
    so the generator is general, but the misconception's verdict on a same-amount
    judgment does not depend on the specific numbers.
    """
    # The arguments document that this applies to a same-amount judgment; the
    # verdict ('no') is the misconception's signature regardless of the pair.
    del frac1, frac2
    return "no"


def equal_sign_as_procedural_relational() -> EqualSignVerdict:
    """equal-sign-as-procedural on a relational 'are these the same?' item.

    There is no operation to run on a same-amount judgment, so the operational
    reader — whose only meaning for '=' is 'compute and write the answer' — has no
    procedure to fall back on and defaults to 'no' (RESEARCH.md §1.2; McNeil et al.
    2006). Takes no arguments because the verdict does not depend on the specific
    fractions: on ANY relational item with nothing to compute, the answer is 'no'
    and ``tried_to_compute`` is ``False``. Every such probe in the bank (EQ-001,
    EQ-002, EQ-010) yields 'no'.
    """
    return EqualSignVerdict(answer="no", tried_to_compute=False)


def procedure_without_concept(correct_answer: object) -> ProcedureWithoutConceptResult:
    """procedure-without-concept: the CORRECT answer, flagged as unjustified.

    This generator is the one that does NOT fabricate a wrong number (the brief's
    nuance). The procedural learner runs the algorithm correctly on routine items,
    so the answer carried is the correct one; the diagnostic tell is that they
    cannot explain it and fail error-finding, captured as ``can_justify=False``
    (PROJECT.md §4.2 Persona 2; RESEARCH.md §1.2; Lenz & Wittmann 2021). On an
    error-finding item the "correct answer" passed in is whatever the learner
    endorses (e.g. the presented-but-wrong 'yes (4/3)' in SUB-005); ``can_justify``
    is still ``False`` because the failure is the absence of a reasonableness check,
    not the production of a specific number. The mastery model uses this flag, not
    a value, to keep procedural fluency from passing as conceptual mastery (§3.4).
    """
    return ProcedureWithoutConceptResult(answer=correct_answer, can_justify=False)
