"""Layer-1 problem generators + the shared ``Problem`` type (Slice 1.3).

This is Slice 1.3 of the domain model (ARCHITECTURE.md §5 Layer 1; PROJECT.md
§3.1, §4.1). It implements the LOCKED hybrid problem-generation strategy
(PROJECT.md §8, decision 0.D.1): a procedural generator per KC produces bulk
problems, while the handpicked ``diagnostic_gems.json`` bank supplies research-
cited diagnostic items — and BOTH feed exactly one ``Problem`` type, so the
mastery model, the persona behavioral simulator (Layer 3) and the transfer test
are source-agnostic. They receive a ``Problem`` and never need to know whether it
was generated or handpicked.

What lives here, and nothing else:

  (a) ``Problem`` — the shared, typed, immutable problem record both sources
      conform to (designed so a bank item maps onto it cleanly);
  (b) one deterministic procedural generator per KC, with surface format as a
      PARAMETER (so interleaving across representations is possible and Surface
      Sam can be defeated — decision 0.D.1); and
  (c) a thin adapter that loads a ``diagnostic_gems.json`` item as a ``Problem``.

Scope is the locked PROJECT.md §3.1 scope: POSITIVE fractions only; equivalence,
common-denominator, addition, subtraction, and number-line placement; NO
multiplication or division. The correct answer of every generated problem is
computed with ``sympy.Rational`` — SymPy lives only in ``domain/`` (CLAUDE.md §7,
ARCHITECTURE.md §14 invariant 5). There is NO LLM and NO DB here (CLAUDE.md
§8.1/§8.2): the generators are pure and deterministic — same seed ⇒ same problem,
which is what makes the persona harness reproducible (PROJECT.md §4.1,
ARCHITECTURE.md §5 Layer 3).

What this is NOT: it is not the answer verifier (Slice 1.4) and not any mastery or
policy logic. It builds problems and adapts bank items; judging correctness and
updating mastery are separate, later slices.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from sympy import Add, Expr, Mul, Rational, Symbol, igcd, ilcm, sstr

from app.domain.center_spread import (
    CENTER_MEDIAN,
    SPREAD_IQR,
    SPREAD_RANGE,
    iqr,
    median,
    range_spread,
)
from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc
from app.domain.misconceptions import (
    CATEGORICAL_MODE_CODE,
    DATA_DISPLAY_QUESTION_CODE,
    SUMMARY_STAT_MODE_CODE,
    classify_sets_for_value,
)

# KC_summary_statistics (6.SP.3) encodes its variable-length data set as ``operands =
# (mode_code, *data)`` — a leading stat-mode sentinel followed by the data values. The mode codes
# live in misconceptions (the median misconception decodes them); re-exported here as the module's
# public name for the generator and its tests.
_SUMMARY_STAT_MODE_CODE = SUMMARY_STAT_MODE_CODE

# KC_data_displays (6.SP.4) encodes its variable-length item as ``operands = (question_code, param,
# *data)`` — a leading question-type sentinel, a single parameter, then the data values the textual
# display describes. The codes live in misconceptions (the distinct-value-count misconception
# decodes them); re-exported here as the module's public name for the generator and its tests.
_DATA_DISPLAY_QUESTION_CODE = DATA_DISPLAY_QUESTION_CODE

# KC_categorical_data (TEKS 6.12D) encodes its variable-length item as ``operands = (mode_code,
# *category_counts)`` — a leading mode sentinel followed by the per-category counts. The mode codes
# live in misconceptions (the wrong-denominator misconception decodes them); re-exported here as
# the module's public name for the generator.
_CATEGORICAL_MODE_CODE = CATEGORICAL_MODE_CODE

# ─── The shared Problem type ─────────────────────────────────────────────────


# The truth rule for a yes/no item: an equality judgment ("same amount?") or a magnitude
# comparison ("greater than?"). Default "equal" keeps every existing yes/no item unchanged.
YesNoRelation = Literal["equal", "greater"]


class AnswerKind(StrEnum):
    """How a problem expects to be ANSWERED — distinct from how it is rendered.

    Most items want a numeric magnitude (``a/b`` or an integer): that is ``NUMERIC``,
    the default. A relational judgment — "Is 2/3 the same amount as 4/6?" — wants a
    ``YES_NO``. The truth of a yes/no item is computed by SymPy over ``operands`` (the
    two named fractions), so the verifier still decides correctness, never a stored
    answer (ARCHITECTURE.md §9, §14 invariant 2). The surface uses this to pick the
    answer widget (a fraction editor vs. yes/no buttons); the verifier uses it to pick
    the correctness rule.
    """

    NUMERIC = "numeric"
    YES_NO = "yes_no"
    # An algebraic EXPRESSION string ("p + 7", "3*n") — not a single magnitude. Its truth is
    # SymPy EQUIVALENCE against ``correct_expression`` (so "7+p" == "p+7"), not a Rational match;
    # the surface picks the free-text ExpressionInput widget. Wire contract (frozen, frontend
    # ExpressionInput): answer_kind="expression" + widget_id="expression".
    EXPRESSION = "expression"
    # A one-variable INEQUALITY string ("x>=5", "x<13") — not a magnitude. Its truth is SymPy
    # RELATIONAL EQUIVALENCE against ``correct_inequality`` (same variable, direction, and bound =
    # same solution set, so "x>=5" == "5<=x"), not a Rational match; the surface picks the free-text
    # inequality widget. Wire contract (frozen): answer_kind="inequality" + widget_id="inequality".
    INEQUALITY = "inequality"
    # A set of integer-coordinate POINTS — a single point "(2,-1)" or a polygon vertex list
    # "(0,0),(3,0),(3,2)". Its truth is ORDER-INSENSITIVE SET EQUALITY against ``correct_points``
    # (a polygon's vertices match in any order), graded by the domain verifier — never a Rational
    # match. Wire contract (frozen): answer_kind="coordinate" + widget_id="coordinate_plane".
    COORDINATE = "coordinate"
    # A classification: the SET of number-system labels a value belongs to ("integer,rational"),
    # ordered small→large. Its truth is ORDER-INSENSITIVE SET membership against ``correct_sets``
    # (computed from the value, NUMBER_SET_LABELS vocabulary), not a Rational match; the surface
    # picks the ClassifySets widget. Wire contract (frozen, frontend ClassifySets):
    # answer_kind="number_sets" + widget_id="classify_sets".
    NUMBER_SETS = "number_sets"


@dataclass(frozen=True)
class Problem:
    """One problem, from EITHER the procedural generator OR the gem bank.

    The single shared type required by decision 0.D.1: downstream code (mastery
    model, persona simulator, transfer test) reads these fields without caring
    where the problem came from. Frozen because a presented problem is a fact, not
    mutable state — nothing downstream may rewrite what a problem *is* at runtime
    (ARCHITECTURE.md §14, CLAUDE.md §8.4). Tuple fields keep the object hashable so
    it can go in a set / be used as a dict key (the harness dedupes problems).

    Fields, mapped to how a bank item supplies each (see ``problem_from_bank_item``):

    - ``problem_id``   stable id. Bank: the item ``id`` (e.g. "ADD-001"). Generated:
      a deterministic ``<KC>-gen-<seed>-<format>`` id, unique per distinct problem.
    - ``kc``           the primary knowledge component. Bank: ``kc_primary``.
    - ``surface_format`` the representation the problem is presented in. Bank:
      ``format``. This is the generator PARAMETER that enables interleaving.
    - ``statement``    the kid-friendly text shown to the learner. Bank:
      ``problem_statement.symbolic`` (kid-friendly per the bank's language rule).
    - ``correct_value`` the SymPy-computed correct answer as a ``Rational``. Bank:
      derived from ``correct_answer`` (parsed from its ``value`` / ``sympy_check``).
    - ``representations_available`` the formats this problem can be shown in. Bank:
      ``problem_statement.representations_available``.
    - ``operands``     the operand fractions for arithmetic/placement KCs, so the
      persona simulator can apply a misconception generator (e.g. add-across) and
      the verifier can recompute. ``None`` for items with no clean operand pair
      (e.g. multi-point ordering, structured judgments). Bank: parsed from the
      statement when two fractions are present.
    """

    problem_id: str
    kc: KnowledgeComponentId
    surface_format: Representation
    statement: str
    correct_value: Rational
    representations_available: tuple[Representation, ...]
    operands: tuple[Rational, ...] | None = None
    # How the learner answers: a numeric magnitude (default) or a yes/no relational
    # judgment. A yes/no item's truth is SymPy over ``operands`` — see ``AnswerKind``.
    answer_kind: AnswerKind = AnswerKind.NUMERIC
    # For a "fill in the missing top number" equivalence item ("3/4 is the same as ?/8")
    # the denominator is GIVEN in the question, so only the numerator is the learner's to
    # find. The surface pre-fills and locks this denominator so the widget asks for exactly
    # the one blank the statement names. ``None`` for every other item (a rendering hint,
    # like the number-line ``tick_segments``; the verifier still judges value-equality).
    given_denominator: int | None = None
    # For a YES_NO item: whether its truth is an equality judgment ("same amount?", the
    # default) or a magnitude comparison ("greater than?"). The verifier reads this to pick
    # the comparison; the surface answers both the same way (yes/no buttons).
    yes_no_relation: YesNoRelation = "equal"
    # For an EXPRESSION item (answer_kind=EXPRESSION): the canonical correct answer as a
    # SymPy-parseable string ("p + 7", "3*n"). The verifier grades a submitted expression by
    # EQUIVALENCE against this (sympify both, equal iff simplify(a - b) == 0), so a reordered form
    # is still correct. ``None`` for every numeric/yes-no item; ``correct_value`` carries a
    # ``Rational(0)`` placeholder for an expression item (never read on the EXPRESSION path).
    correct_expression: str | None = None
    # For an "equivalent expression" item (KC_equivalent_expressions): the GIVEN (un-rewritten)
    # expression the learner must produce an equivalent of, as a SymPy-parseable string
    # ("3*(x + 2)"). The verifier replays the distributive-error misconception from THIS source
    # (it cannot be derived from the answer alone, unlike reversed-operands). ``None`` for every
    # other item; symmetric to ``correct_expression`` (a domain-only carrier, never on the wire).
    source_expression: str | None = None
    # For an INEQUALITY item (answer_kind=INEQUALITY): the canonical correct answer as a
    # SymPy-parseable relational string ("x>=5", "x<13"). The verifier grades a submitted inequality
    # by RELATIONAL EQUIVALENCE against this (same variable, direction, bound = same solution set),
    # so "x>=5" == "5<=x" but "x>3" != "x>=3". ``None`` for every other item; ``correct_value``
    # carries a ``Rational(0)`` placeholder for an inequality item (never read on this path).
    correct_inequality: str | None = None
    # For a COORDINATE item (answer_kind=COORDINATE): the canonical answer as a comma-separated
    # list of integer-coordinate points ("(2,-1)" or "(0,0),(3,0),(3,2)"). The verifier grades a
    # submitted answer by ORDER-INSENSITIVE SET equality against this (parse both to a set of
    # integer tuples), so the vertices may be listed in any order. ``None`` for every other item;
    # ``correct_value`` carries a ``Rational(0)`` placeholder for a coordinate item (never read on
    # the COORDINATE path).
    correct_points: str | None = None
    # For a NUMBER_SETS item (answer_kind=NUMBER_SETS): the canonical correct answer as a
    # comma-separated label list ordered small→large ("integer,rational"). The verifier grades a
    # submitted list by ORDER-INSENSITIVE SET membership against this. ``None`` for every other
    # item; ``correct_value`` carries a ``Rational(0)`` placeholder for a number-sets item (never
    # read on the NUMBER_SETS path). The classified VALUE itself rides in ``operands`` so the
    # misconception (drop ``rational``) is replayable.
    correct_sets: str | None = None


# A generator takes a seeded RNG, the seed (for the stable id), the chosen surface
# format, and a difficulty tier, and returns a Problem. Keeping the signature uniform
# lets ``GENERATORS`` be a flat KC -> generator map.
_KcGenerator = Callable[[random.Random, int, Representation, "int | None"], Problem]


# ─── Scope-safe building blocks (PROJECT.md §3.1: positive proper fractions) ──
#
# Every generated operand is a positive proper fraction (0 < n/d < 1) with a
# denominator > 1. We sample from a small curriculum-appropriate denominator set
# (2..12, the sizes the gem bank uses) and a numerator strictly between 0 and the
# denominator, so the fraction is positive and not a whole number — exactly the
# §3.1 scope. Sampling through the seeded RNG is what makes a seed reproducible.

_DENOMINATORS: tuple[int, ...] = (2, 3, 4, 5, 6, 8, 10, 12)

# Difficulty tiers (CP.B easy→hard ramp; CURRICULUM_DRAFT.md §1.1). A tier narrows the
# denominator pool a generated operand may draw from, so a lesson that walks tiers 1→4
# ramps from friendly halves/thirds/quarters to the larger denominators where
# natural-number bias bites. Every tier has ≥3 denominators, so unlike-pairs are always
# feasible. ``None`` = the full set (the pre-ramp default, kept so callers that don't ask
# for a tier are unchanged and deterministic).
_DENOM_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4),
    2: (3, 4, 5, 6),
    3: (5, 6, 8),
    4: (6, 8, 10, 12),
}


def _denoms(difficulty: int | None) -> tuple[int, ...]:
    """The denominator pool for a difficulty tier (the full set when ``difficulty`` is None
    or out of range — never empty, so sampling is always well-defined)."""
    return _DENOM_BY_DIFFICULTY.get(difficulty, _DENOMINATORS) if difficulty else _DENOMINATORS


def _proper_fraction(rng: random.Random, difficulty: int | None = None) -> Rational:
    """Sample one positive proper fraction 0 < n/d < 1 with d > 1 (in-scope); the
    denominator is drawn from ``difficulty``'s pool (the full set when None)."""
    denominator = rng.choice(_denoms(difficulty))
    numerator = rng.randint(1, denominator - 1)  # 1..d-1 keeps it strictly in (0, 1)
    return Rational(numerator, denominator)


def _unlike_pair(rng: random.Random, difficulty: int | None = None) -> tuple[Rational, Rational]:
    """Sample two positive proper fractions with UNLIKE denominators.

    The add/subtract KCs are "with unlike denominators" (PROJECT.md §3.1), so the
    two pieces must be different sizes — otherwise the common-denominator step the
    KC is named for is never exercised. We resample the second fraction until its
    denominator differs; the loop is bounded because every difficulty pool has ≥3
    denominators.
    """
    first = _proper_fraction(rng, difficulty)
    second = _proper_fraction(rng, difficulty)
    while second.q == first.q:
        second = _proper_fraction(rng, difficulty)
    return first, second


def _unlike_pair_sum_below_one(
    rng: random.Random, difficulty: int | None = None
) -> tuple[Rational, Rational]:
    """An unlike-denominator pair whose SUM is < 1, for number-line addition.

    The number-line surface spans 0–1, so an addition answered by placing the total must
    have a total in that interval. We resample until the sum fits (bounded), falling back to
    a known-good in-scope pair (1/4 + 1/3 = 7/12) so the generator is always deterministic
    and never loops forever (CLAUDE.md §8.5)."""
    for _ in range(50):
        first, second = _unlike_pair(rng, difficulty)
        if first + second < 1:
            return first, second
    return Rational(1, 4), Rational(1, 3)


def _ordered_unlike_pair(
    rng: random.Random, difficulty: int | None = None
) -> tuple[Rational, Rational]:
    """An unlike-denominator pair ordered larger-first, for well-formed subtraction.

    Subtraction stays in scope (positive result) only if the minuend exceeds the
    subtrahend, so we sample an unlike pair and return it largest-first.
    """
    first, second = _unlike_pair(rng, difficulty)
    if first > second:
        return first, second
    if second > first:
        return second, first
    # Equal magnitude with unlike denominators (e.g. 1/2 vs 2/4 cannot occur since
    # denominators differ, but guard anyway): resample to guarantee a strict order.
    return _ordered_unlike_pair(rng, difficulty)


def _require_supported_format(kc: KnowledgeComponentId, surface_format: Representation) -> None:
    """Fail loudly if a KC is asked to render in a format it does not support.

    The KC registry advertises which representations apply to each KC (PROJECT.md
    §3.3/§3.5); rendering KC_equivalence on a number line is not meaningful, so we
    raise rather than silently substitute a different format (CLAUDE.md §8.5).
    """
    supported = get_kc(kc).representations
    if surface_format not in supported:
        raise ValueError(
            f"{kc.value} cannot be rendered as {surface_format.value}; "
            f"supported formats: {[r.value for r in supported]}"
        )


def _default_format(kc: KnowledgeComponentId) -> Representation:
    """The format a KC defaults to when the caller does not specify one.

    The registry lists each KC's representations in priority order, so the first is
    a sensible default (symbolic for the arithmetic KCs, number_line for placement).
    """
    return get_kc(kc).representations[0]


def _generated_id(kc: KnowledgeComponentId, seed: int, surface_format: Representation) -> str:
    """A stable, human-readable id for a generated problem.

    Includes the seed and format so two distinct generated problems get distinct
    ids (the harness dedupes by id), and so a generated id never collides with a
    bank id (which use the ``EQ-001`` / ``ADD-001`` style).
    """
    return f"{kc.value}-gen-{seed}-{surface_format.value}"


# ─── Per-KC procedural generators ────────────────────────────────────────────
#
# Each generator computes its correct answer with SymPy from the sampled operands;
# the answer is never asserted by hand. The kid-friendly statement mirrors the gem
# bank's phrasing style (PROJECT.md learner-facing-language rule via the bank).


def _generate_equivalence(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_equivalence in two REAL representations (so mastery rule 2 is reachable live):

    - **SYMBOLIC** (default): "fill in the missing top number so both names show the same
      amount: a/b is the same as ?/N" (the bank's EQ-003/EQ-004 fill-the-blank shape). The
      denominator N is given; the learner supplies the numerator. correct_value = the base.
    - **WORD_PROBLEM**: a yes/no JUDGMENT in a story — "{Name} cut a {thing} into N pieces and
      took k; is that the same amount as a/b?" Half the time (deterministic per seed) the story
      amount is a genuine rename of a/b (equal → YES); otherwise a different amount (NO). The
      truth is SymPy equality over the two operands. Translating a story to a fraction comparison
      is a genuinely different skill from the symbolic form — a real second representation for
      mastery rule 2, answered with the same yes/no control.
    """
    if surface_format is Representation.WORD_PROBLEM:
        base = _proper_fraction(rng, difficulty)  # the a/b the story is compared against
        if rng.random() < 0.5:  # the story amount is an equal rename (answer YES)
            scale = rng.randint(2, 4)
            taken, pieces, other = base.p * scale, base.q * scale, base
        else:  # a genuinely different amount (answer NO)
            other = _proper_fraction(rng, difficulty)
            while other == base:
                other = _proper_fraction(rng, difficulty)
            taken, pieces = other.p, other.q
        name = rng.choice(("Maria", "Sam", "Leo", "Ava", "Theo"))
        thing = rng.choice(("pizza", "cake", "ribbon", "chocolate bar"))
        statement = (
            f"{name} cut a {thing} into {pieces} equal pieces and took {taken}. "
            f"Is that the same amount as {base.p}/{base.q} of the {thing}?"
        )
        return Problem(
            problem_id=_generated_id(KnowledgeComponentId.EQUIVALENCE, seed, surface_format),
            kc=KnowledgeComponentId.EQUIVALENCE,
            surface_format=surface_format,
            statement=statement,
            correct_value=base,  # magnitude anchor; the yes/no truth is operands[0] == operands[1]
            representations_available=get_kc(KnowledgeComponentId.EQUIVALENCE).representations,
            operands=(base, other),
            answer_kind=AnswerKind.YES_NO,
        )

    base = _proper_fraction(rng, difficulty)
    scale = rng.randint(2, 4)  # bigger-bottom rename; keeps numbers curriculum-sized
    new_denominator = base.q * scale
    statement = (
        "Fill in the missing top number so both names show the same amount: "
        f"{base.p}/{base.q} is the same as ?/{new_denominator}"
    )
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.EQUIVALENCE, seed, surface_format),
        kc=KnowledgeComponentId.EQUIVALENCE,
        surface_format=surface_format,
        statement=statement,
        correct_value=base,  # the equivalent form names the same amount as `base`
        representations_available=get_kc(KnowledgeComponentId.EQUIVALENCE).representations,
        operands=(base,),
        given_denominator=new_denominator,  # surface pre-fills/locks the "?/{new_denominator}"
    )


def _generate_common_denominator(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_common_denominator: a shared piece-size for two fractions (§3.4.1).

    The answer is ANY positive common multiple of the two denominators — the verifier accepts
    any (e.g. 12 OR 24 for 3/4 and 1/6), not only the least (§3.4.1: "find A common
    denominator", not "find the LEAST"). ``correct_value`` carries the LCD (the canonical least
    anchor the worked example / hints teach), computed by SymPy; verification does the
    accept-any divisibility check. Two construction representations so the skill is masterable
    across representations (PROJECT.md §3.4 rule 2):

      - SYMBOLIC   — "what piece-size works for both?" (a whole-number answer);
      - AREA_MODEL — repartition two bars until their pieces align; the shared partition count
        IS the common denominator (the visual, magnitude-grounded form).

    Both are answered with the SAME whole-number value (NUMERIC), so the simulator/verifier are
    representation-agnostic; only the framing and the surface widget differ.
    """
    first, second = _unlike_pair(rng, difficulty)
    shared = ilcm(first.q, second.q)
    if surface_format is Representation.AREA_MODEL:
        statement = (
            f"Cut both bars into the same size pieces so {first.p}/{first.q} and "
            f"{second.p}/{second.q} line up. How many equal pieces should each bar have?"
        )
    else:
        statement = (
            "What size of piece (bottom number) works for BOTH "
            f"{first.p}/{first.q} and {second.p}/{second.q}?"
        )
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.COMMON_DENOMINATOR, seed, surface_format),
        kc=KnowledgeComponentId.COMMON_DENOMINATOR,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(shared),
        representations_available=get_kc(KnowledgeComponentId.COMMON_DENOMINATOR).representations,
        operands=(first, second),
    )


def _generate_addition(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_addition_unlike: add two positive proper fractions with unlike bottoms.

    The correct value is the SymPy sum (ADD items, e.g. 1/2 + 1/4 = 3/4). A sum of
    two positive fractions is strictly larger than either addend — the property the
    area model / number line use to expose the add-across error.

    Two REAL representations (so the mastery model's rule 2 can be met live): the default
    SYMBOLIC "a/b + c/d = ?" answered in the fraction editor, and a NUMBER_LINE form where
    the learner places the TOTAL on the 0–1 line (operands sampled so the sum fits 0–1).
    """
    if surface_format is Representation.NUMBER_LINE:
        first, second = _unlike_pair_sum_below_one(rng, difficulty)
        total = first + second
        statement = (
            f"Add {first.p}/{first.q} + {second.p}/{second.q}, then drag the marker to where "
            f"the total sits on the line from 0 to 1."
        )
    else:
        first, second = _unlike_pair(rng, difficulty)
        total = first + second
        statement = f"{first.p}/{first.q} + {second.p}/{second.q} = ?"
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.ADDITION_UNLIKE, seed, surface_format),
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        surface_format=surface_format,
        statement=statement,
        correct_value=total,
        representations_available=get_kc(KnowledgeComponentId.ADDITION_UNLIKE).representations,
        operands=(first, second),
    )


def _generate_subtraction(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_subtraction_unlike: subtract, larger minus smaller, unlike bottoms.

    Ordered larger-first so the difference is positive (in-scope). The correct value
    is the SymPy difference (SUB items, e.g. 1/2 - 1/4 = 1/4).

    Two REAL representations (rule 2): SYMBOLIC "a/b - c/d = ?" in the fraction editor, and a
    NUMBER_LINE form placing the result on 0–1 (a proper-fraction difference is always in
    that interval).
    """
    minuend, subtrahend = _ordered_unlike_pair(rng, difficulty)
    difference = minuend - subtrahend
    if surface_format is Representation.NUMBER_LINE:
        statement = (
            f"Subtract {minuend.p}/{minuend.q} - {subtrahend.p}/{subtrahend.q}, then drag the "
            f"marker to where the answer sits on the line from 0 to 1."
        )
    else:
        statement = f"{minuend.p}/{minuend.q} - {subtrahend.p}/{subtrahend.q} = ?"
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.SUBTRACTION_UNLIKE, seed, surface_format),
        kc=KnowledgeComponentId.SUBTRACTION_UNLIKE,
        surface_format=surface_format,
        statement=statement,
        correct_value=difference,
        representations_available=get_kc(KnowledgeComponentId.SUBTRACTION_UNLIKE).representations,
        operands=(minuend, subtrahend),
    )


def _number_line_target(rng: random.Random, difficulty: int | None) -> Rational:
    """A number-line placement target whose sign/magnitude matches the difficulty tier
    (CP.B ramp + the authorized improper/negative scope expansion, PROJECT.md §3.1):

      - tiers 1–2 (or None) → a positive PROPER fraction in (0,1);
      - tier 3              → a positive IMPROPER fraction in (1,2) — placed PAST the '1'
        landmark, the most concrete refutation of "n<d so it fits in the box";
      - tier 4              → a NEGATIVE fraction (proper or improper) in (−2,0) — left of 0
        (CCSS 6.NS.6), where magnitude is distance from 0, not the digits.

    Whole-number values are excluded (numerator never a multiple of the denominator) so the
    target is always a real fraction to place, never a trivial landmark.
    """
    if difficulty == 3:
        denominator = rng.choice(_denoms(2))
        numerator = rng.randint(denominator + 1, 2 * denominator - 1)  # (1,2), never the whole 2
        return Rational(numerator, denominator)
    if difficulty is not None and difficulty >= 4:
        denominator = rng.choice(_denoms(2))
        numerator = rng.randint(1, 2 * denominator - 1)
        while numerator == denominator:  # avoid −1 (a whole number)
            numerator = rng.randint(1, 2 * denominator - 1)
        return Rational(-numerator, denominator)
    return _proper_fraction(rng, difficulty)


def _generate_number_line(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_number_line_placement in two REAL representations (so mastery rule 2 is reachable):

    - **NUMBER_LINE** (default): place one fraction on the line — proper on 0–1, then (as the
      ramp climbs) IMPROPER on 0–2 and NEGATIVE on −2…0 (CP.B; PROJECT.md §3.1 magnitude scope).
      correct_value = the fraction; the surface reads the axis bounds off its magnitude.
    - **SYMBOLIC**: a magnitude COMPARISON — "is a/b greater than c/d?" — the same
      reason-about-magnitude-not-digits skill, without the line. At the hardest tier both
      fractions are NEGATIVE ("is −1/4 greater than −3/4?"), baiting negative-magnitude bias —
      the negative twin of natural-number bias. Answered yes/no; truth is SymPy a > b.
    """
    if surface_format is Representation.SYMBOLIC:
        first, second = _unlike_pair(rng, difficulty)
        if difficulty is not None and difficulty >= 4:
            first, second = -first, -second  # negative-magnitude-bias comparison (6.NS.7)
        return Problem(
            problem_id=_generated_id(
                KnowledgeComponentId.NUMBER_LINE_PLACEMENT, seed, surface_format
            ),
            kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
            surface_format=surface_format,
            statement=f"Is {first.p}/{first.q} greater than {second.p}/{second.q}?",
            correct_value=first,  # magnitude anchor; the yes/no truth is operands[0] > operands[1]
            representations_available=get_kc(
                KnowledgeComponentId.NUMBER_LINE_PLACEMENT
            ).representations,
            operands=(first, second),
            answer_kind=AnswerKind.YES_NO,
            yes_no_relation="greater",
        )

    target = _number_line_target(rng, difficulty)
    # The axis just contains the target: [0,1] for a proper fraction, [0,2] for improper,
    # [floor,1] for a negative — always anchored on 0 and ≥1 so the learner has a reference.
    # floor/ceil via integer arithmetic on the Rational (Python // floors toward −∞).
    floor_target = target.p // target.q
    ceil_target = -((-target.p) // target.q)
    axis_lo = min(0, floor_target)
    axis_hi = max(1, ceil_target)
    span = f"the line from {axis_lo} to {axis_hi}"
    statement = f"Drag the marker to where {target.p}/{target.q} belongs on {span}."
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.NUMBER_LINE_PLACEMENT, seed, surface_format),
        kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        surface_format=surface_format,
        statement=statement,
        correct_value=target,
        representations_available=get_kc(
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT
        ).representations,
        operands=(target,),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 1: Ratios & Rates ───

# Two-colour counter contexts for ratio-language items: (this-colour, other-colour). The asked
# colour is the FIRST entry; the question wants its part-OF-the-whole fraction. Seeded RNG so the
# same seed yields the same scenario (PROJECT.md §4.1 reproducibility).
_RATIO_COLOURS: tuple[tuple[str, str], ...] = (
    ("red", "blue"),
    ("green", "yellow"),
    ("black", "white"),
    ("orange", "purple"),
)

# The two part-counts by difficulty tier (the easy→hard ramp; CP.B): higher tiers use larger
# counts so the part-whole fraction is less obvious. Whole-number counts (the answer is the
# part-WHOLE fraction); the ramp is by count size, not denominator size.
_RATIO_COUNTS_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3),
    2: (2, 3, 4),
    3: (3, 4, 5, 6),
    4: (4, 5, 6, 7),
}
_RATIO_COUNT_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7)


def _generate_ratio_language(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_ratio_language: tell a part-to-whole ratio from a part-to-part ratio (6.RP.1).

    Builds a two-colour collection (``part`` of one colour, ``other`` of a second) and asks for
    the asked colour's fraction OF the whole — ``part / (part + other)``, strictly between 0 and 1.
    ``operands = (part, other)`` so the verifier can replay the part-part-whole confusion (the
    part-TO-part ratio ``part / other``, which is always a DIFFERENT value since ``part >= 1`` ⇒
    ``other != part + other``). Rendered symbolically; ``difficulty`` widens the count pool.
    """
    pool = (
        _RATIO_COUNTS_BY_DIFFICULTY.get(difficulty, _RATIO_COUNT_POOL)
        if difficulty
        else _RATIO_COUNT_POOL
    )
    part = rng.choice(pool)
    other = rng.choice(pool)
    this_colour, other_colour = rng.choice(_RATIO_COLOURS)
    total = part + other
    statement = (
        f"A jar has {part} {this_colour} and {other} {other_colour} counters. "
        f"What fraction of the counters are {this_colour}? "
        f"(Compare the {this_colour} counters to ALL the counters, not to the {other_colour}.)"
    )
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.RATIO_LANGUAGE, seed, surface_format),
        kc=KnowledgeComponentId.RATIO_LANGUAGE,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(part, total),
        representations_available=get_kc(KnowledgeComponentId.RATIO_LANGUAGE).representations,
        operands=(Rational(part), Rational(other)),
    )


# Word-problem contexts for unit-rate items: (quantity-noun, single-unit) pairs. Chosen through
# the seeded RNG so the same seed yields the same scenario (PROJECT.md §4.1 reproducibility).
_RATE_CONTEXTS: tuple[tuple[str, str], ...] = (
    ("dollars", "pound"),
    ("dollars", "ticket"),
    ("miles", "hour"),
    ("pages", "minute"),
    ("liters", "tank"),
)

# The per-ONE rate pool by difficulty tier (the easy→hard ramp; CP.B). Higher tiers use larger
# rates. ``None`` / out-of-range keeps the full pool (the pre-ramp default, unchanged for callers
# that don't ask for a tier).
_RATE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4),
    2: (3, 4, 5, 6),
    3: (4, 6, 7, 8),
    4: (6, 7, 8, 9),
}
_RATE_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9)


def _generate_unit_rate(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_unit_rate: find the per-ONE rate from a total given for several units.

    Builds a clean whole-number unit rate ``r`` (so the answer is friendly): a total of
    ``r * count`` over ``count`` units, asking how much for ONE unit. The correct value is the
    SymPy quotient ``total / count`` (which equals ``r``); ``operands = (total, count)`` so the
    verifier can replay the rate-inversion misconception (``count / total``). Rendered
    symbolically — a numeric-answer word problem; ``difficulty`` widens the rate pool.
    """
    rate_pool = _RATE_BY_DIFFICULTY.get(difficulty, _RATE_POOL) if difficulty else _RATE_POOL
    rate = rng.choice(rate_pool)
    count = rng.choice((2, 3, 4, 5, 6))
    total = rate * count
    noun, unit = rng.choice(_RATE_CONTEXTS)
    statement = (
        f"{total} {noun} for {count} {unit}s. How many {noun} per {unit}? "
        f"(Find the unit rate — the amount for ONE {unit}.)"
    )
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.UNIT_RATE, seed, surface_format),
        kc=KnowledgeComponentId.UNIT_RATE,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(total, count),
        representations_available=get_kc(KnowledgeComponentId.UNIT_RATE).representations,
        operands=(Rational(total), Rational(count)),
    )


def _generate_equivalent_ratios(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_equivalent_ratios: find the missing term of an equivalent ratio (multiplicative).

    Builds ``a:b = ?:(b*k)`` and asks for the missing term ``a*k``. The scale factor ``k`` is
    ≥3 so the additive answer (``a + (b*k - b)``) is always DISTINCT from the correct ``a*k``
    (they coincide only at k=2), keeping the misconception diagnostic. ``operands = (a, b,
    b*k)`` so the verifier can replay the additive-ratio error. Numeric, rendered symbolically.
    """
    scale_pool = {1: (3, 4), 2: (3, 4, 5), 3: (4, 5, 6), 4: (5, 6, 7)}.get(
        difficulty or 0, (3, 4, 5)
    )
    a = rng.randint(1, 6)
    b = rng.randint(1, 6)
    # a != b keeps the additive misconception (a + (b*k - b)) DISTINCT from the multiplicative
    # answer (a*k): the two coincide exactly when a == b (then both equal k), which would make the
    # error non-diagnostic. With a != b and k >= 3 they always differ.
    while b == a:
        b = rng.randint(1, 6)
    k = rng.choice(scale_pool)
    target_den = b * k
    statement = f"{a} : {b} = ? : {target_den}. Find the missing number that keeps the ratio equal."
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.EQUIVALENT_RATIOS, seed, surface_format),
        kc=KnowledgeComponentId.EQUIVALENT_RATIOS,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(a * k),
        representations_available=get_kc(KnowledgeComponentId.EQUIVALENT_RATIOS).representations,
        operands=(Rational(a), Rational(b), Rational(target_den)),
    )


_PERCENT_POOL: tuple[int, ...] = (10, 20, 25, 30, 40, 50, 60, 75)
_PERCENT_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (10, 50),
    2: (20, 25, 50),
    3: (30, 40, 60),
    4: (25, 60, 75),
}
# Wholes exclude 100 so the percent NUMBER itself (the percent-as-amount misconception) is always
# distinct from the correct value (p% of 100 == p only at whole == 100).
_PERCENT_WHOLES: tuple[int, ...] = (20, 30, 40, 50, 60, 80)


def _generate_percent(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_percent: find a percent OF a quantity (a rate per 100).

    Asks "what is p% of whole?"; the answer is the SymPy ``Rational(p*whole, 100)`` (may reduce
    to a fraction, which the editor accepts). ``operands = (p, whole)`` so the verifier can replay
    the percent-as-amount misconception (answering the percent ``p`` itself). Numeric, symbolic.
    """
    pool = _PERCENT_BY_DIFFICULTY.get(difficulty, _PERCENT_POOL) if difficulty else _PERCENT_POOL
    percent = rng.choice(pool)
    whole = rng.choice(_PERCENT_WHOLES)
    statement = f"What is {percent}% of {whole}?"
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.PERCENT, seed, surface_format),
        kc=KnowledgeComponentId.PERCENT,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(percent * whole, 100),
        representations_available=get_kc(KnowledgeComponentId.PERCENT).representations,
        operands=(Rational(percent), Rational(whole)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 2: Fractions & Decimals (T2) ───


def _generate_multiply_fractions(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_multiply_fractions: multiply two proper fractions; the product is the answer.

    Two unlike-denominator proper fractions (the existing ``_unlike_pair`` pool, so difficulty
    ramps the same way the other fraction KCs do). The correct value is the SymPy product
    ``first * second`` (e.g. 2/3 x 3/4 = 1/2). ``operands = (first, second)`` so the verifier can
    replay the multiply-as-add misconception (``first + second`` — treating x as +). Rendered
    symbolically; a product of two proper fractions is strictly smaller than either factor, the
    property the area model uses and that defeats the "added, so it got bigger" error.
    """
    first, second = _unlike_pair(rng, difficulty)
    product = first * second
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.MULTIPLY_FRACTIONS, seed, surface_format),
        kc=KnowledgeComponentId.MULTIPLY_FRACTIONS,
        surface_format=surface_format,
        statement=f"{first.p}/{first.q} x {second.p}/{second.q} = ?",
        correct_value=product,
        representations_available=get_kc(KnowledgeComponentId.MULTIPLY_FRACTIONS).representations,
        operands=(first, second),
    )


def _generate_divide_fractions(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_divide_fractions: divide a fraction by a fraction; the quotient is the answer.

    Two unlike-denominator proper fractions (the existing ``_unlike_pair`` pool, so difficulty
    ramps the same way the other fraction KCs do). The correct value is the SymPy quotient
    ``first / second`` (invert and multiply, e.g. 1/2 div 3/4 = 2/3). ``operands = (first, second)``
    so the verifier can replay the multiply-without-inverting misconception (``first * second`` —
    skipping the flip). The divisor is a PROPER fraction (numerator < denominator), so its
    reciprocal differs from itself and the no-invert error is always a distinct value. Symbolic.
    """
    first, second = _unlike_pair(rng, difficulty)
    quotient = first / second
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.DIVIDE_FRACTIONS, seed, surface_format),
        kc=KnowledgeComponentId.DIVIDE_FRACTIONS,
        surface_format=surface_format,
        statement=f"{first.p}/{first.q} div {second.p}/{second.q} = ?",
        correct_value=quotient,
        representations_available=get_kc(KnowledgeComponentId.DIVIDE_FRACTIONS).representations,
        operands=(first, second),
    )


# Conversion contexts: (larger-unit, smaller-unit, factor) — small units per ONE large unit.
# Chosen through the seeded RNG so the same seed yields the same scenario (PROJECT.md §4.1).
# Every factor is > 1 (a genuine convert-down), so the inversion error (quantity/factor) is
# always a distinct, smaller value.
_CONVERSION_CONTEXTS: tuple[tuple[str, str, int], ...] = (
    ("foot", "inches", 12),
    ("yard", "feet", 3),
    ("hour", "minutes", 60),
    ("minute", "seconds", 60),
    ("meter", "centimeters", 100),
    ("dozen", "items", 12),
    ("week", "days", 7),
)

# The quantity pool by difficulty tier (the easy→hard ramp; CP.B): higher tiers use larger
# quantities. ``None`` / out-of-range keeps the full pool (the pre-ramp default).
_CONVERSION_QTY_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4),
    2: (3, 4, 5, 6),
    3: (5, 6, 7, 8),
    4: (7, 8, 9, 10),
}
_CONVERSION_QTY_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9, 10)


def _generate_unit_conversion(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_unit_conversion: convert a quantity to the smaller unit via its conversion factor.

    Builds a clean whole-number conversion: ``quantity`` larger units at ``factor`` smaller units
    each, asking how many smaller units. The correct value is the SymPy product ``quantity *
    factor``; ``operands = (quantity, factor)`` so the verifier can replay the conversion-inversion
    misconception (``quantity / factor``). Rendered symbolically — a numeric-answer conversion
    word problem; ``difficulty`` widens the quantity pool.
    """
    qty_pool = (
        _CONVERSION_QTY_BY_DIFFICULTY.get(difficulty, _CONVERSION_QTY_POOL)
        if difficulty
        else _CONVERSION_QTY_POOL
    )
    quantity = rng.choice(qty_pool)
    larger, smaller, factor = rng.choice(_CONVERSION_CONTEXTS)
    statement = (
        f"{factor} {smaller} = 1 {larger}. How many {smaller} are in {quantity} {larger}s? "
        f"(Convert by multiplying by the factor.)"
    )
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.UNIT_CONVERSION, seed, surface_format),
        kc=KnowledgeComponentId.UNIT_CONVERSION,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(quantity * factor),
        representations_available=get_kc(KnowledgeComponentId.UNIT_CONVERSION).representations,
        operands=(Rational(quantity), Rational(factor)),
    )


# GCF/LCM number pairs by difficulty tier (the easy→hard ramp; CP.B). Every pair has a != b (so
# gcd != lcm — the GCF↔LCM confusion is always a genuinely wrong answer) and a non-trivial shared
# factor on the harder tiers (so the GCF isn't a giveaway 1). ``None`` / out-of-range keeps the
# full pool (the pre-ramp default, unchanged for callers that don't ask for a tier).
_GCF_LCM_PAIRS_BY_DIFFICULTY: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((4, 6), (6, 8), (4, 10)),
    2: ((6, 9), (8, 12), (9, 12)),
    3: ((12, 18), (10, 15), (8, 20)),
    4: ((12, 30), (18, 24), (16, 20)),
}
_GCF_LCM_PAIR_POOL: tuple[tuple[int, int], ...] = tuple(
    pair for pairs in _GCF_LCM_PAIRS_BY_DIFFICULTY.values() for pair in pairs
)
# operands carry a mode flag the verifier reads (it never sees the statement): 0 = GCF asked,
# 1 = LCM asked. Defined here as the single source of truth for the encoding.
_GCF_MODE = 0
_LCM_MODE = 1


def _generate_gcf_lcm(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_gcf_lcm: find the GCF or the LCM of two whole numbers; a single integer is the answer.

    Picks a pair ``(a, b)`` with ``a != b`` and then, by the same seeded RNG, whether to ask for
    the GREATEST COMMON FACTOR or the LEAST COMMON MULTIPLE. The correct value is the SymPy
    ``igcd``/``ilcm`` of the pair. ``operands = (a, b, mode)`` — ``mode`` (0 = GCF, 1 = LCM) lets
    the verifier replay the GCF↔LCM-confusion misconception (return the OTHER aggregate) without
    seeing the statement. Rendered symbolically; ``difficulty`` widens the pair pool.
    """
    pool = (
        _GCF_LCM_PAIRS_BY_DIFFICULTY.get(difficulty, _GCF_LCM_PAIR_POOL)
        if difficulty
        else _GCF_LCM_PAIR_POOL
    )
    a, b = rng.choice(pool)
    ask_lcm = rng.random() < 0.5
    mode = _LCM_MODE if ask_lcm else _GCF_MODE
    answer = ilcm(a, b) if ask_lcm else igcd(a, b)
    if ask_lcm:
        statement = f"What is the least common multiple (LCM) of {a} and {b}?"
    else:
        statement = f"What is the greatest common factor (GCF) of {a} and {b}?"
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.GCF_LCM, seed, surface_format),
        kc=KnowledgeComponentId.GCF_LCM,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(int(answer)),
        representations_available=get_kc(KnowledgeComponentId.GCF_LCM).representations,
        operands=(Rational(a), Rational(b), Rational(mode)),
    )


# Multi-digit-division divisor and quotient pools by difficulty tier (the easy→hard ramp; CP.B).
# The dividend is divisor * quotient, so division is always EXACT (a clean integer quotient) and
# the dividend is multi-digit; higher tiers use larger quotients (so larger dividends). ``None`` /
# out-of-range keeps the full pool (the pre-ramp default, unchanged for callers without a tier).
_DIVISION_DIVISORS: tuple[int, ...] = (3, 4, 6, 7, 8, 9, 12)
_DIVISION_QUOTIENT_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (12, 15, 18, 24),
    2: (23, 34, 41, 52),
    3: (68, 75, 84, 96),
    4: (123, 156, 204, 312),
}
_DIVISION_QUOTIENT_POOL: tuple[int, ...] = (12, 15, 23, 34, 52, 68, 84, 96, 123, 204)


def _generate_multi_digit_division(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_multi_digit_division: divide a multi-digit whole number exactly; quotient is the answer.

    Builds the dividend as ``divisor * quotient`` so the division is always exact (a clean integer
    quotient, no remainder) and the dividend is multi-digit. The correct value is the SymPy
    quotient ``dividend / divisor`` (which equals ``quotient``). ``operands = (dividend, divisor)``
    so the verifier can replay the place-value-slip misconception (``quotient * 10`` — the right
    digits off by a factor of 10). Rendered symbolically; ``difficulty`` widens the quotient pool.
    """
    quotient_pool = (
        _DIVISION_QUOTIENT_BY_DIFFICULTY.get(difficulty, _DIVISION_QUOTIENT_POOL)
        if difficulty
        else _DIVISION_QUOTIENT_POOL
    )
    divisor = rng.choice(_DIVISION_DIVISORS)
    quotient = rng.choice(quotient_pool)
    dividend = divisor * quotient
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.MULTI_DIGIT_DIVISION, seed, surface_format),
        kc=KnowledgeComponentId.MULTI_DIGIT_DIVISION,
        surface_format=surface_format,
        statement=f"{dividend} divided by {divisor} = ?",
        correct_value=Rational(dividend, divisor),
        representations_available=get_kc(KnowledgeComponentId.MULTI_DIGIT_DIVISION).representations,
        operands=(Rational(dividend), Rational(divisor)),
    )


# Decimal factors for the product, as (numerator, denominator) with a power-of-ten denominator —
# tenths and hundredths, the place values 6.NS.3 works in. Kept as integer pairs so the operand is
# an EXACT Rational (5/10, 25/100), never a float. Difficulty climbs from tenths to hundredths and
# from small to larger digit strings.
_DECIMAL_FACTORS_BY_DIFFICULTY: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((2, 10), (3, 10), (5, 10), (4, 10)),  # 0.2 … 0.5, one place
    2: ((6, 10), (8, 10), (15, 10), (12, 10)),  # 0.6 … 1.5, one place
    3: ((25, 100), (15, 100), (35, 100), (8, 10)),  # mix tenths/hundredths
    4: ((125, 100), (45, 100), (75, 100), (24, 10)),  # larger, two places
}
_DECIMAL_FACTOR_POOL: tuple[tuple[int, int], ...] = (
    (2, 10),
    (5, 10),
    (3, 10),
    (25, 100),
    (15, 100),
    (8, 10),
)


def _decimal_literal(numerator: int, power_of_ten_denominator: int) -> str:
    """Render ``numerator / power_of_ten_denominator`` as a finite decimal string (e.g. 25/100 →
    "0.25"). Pure integer arithmetic — no float — so the statement text introduces no fuzz."""
    places = len(str(power_of_ten_denominator)) - 1  # 10 → 1, 100 → 2
    if places == 0:
        return str(numerator)
    sign = "-" if numerator < 0 else ""
    digits = str(abs(numerator)).zfill(places + 1)
    return f"{sign}{digits[:-places]}.{digits[-places:]}"


def _generate_decimal_operations(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_decimal_operations: multiply two decimals; the product (a decimal) is the answer.

    Both factors are exact decimals with power-of-ten denominators (tenths/hundredths), so the
    product is a finite decimal the symbolic editor accepts as a decimal string. The correct value
    is the SymPy product ``first * second``; ``operands = (first, second)`` so the verifier can
    replay the decimal-point-misplacement misconception (the product off by a power of ten).
    Rendered symbolically; ``difficulty`` widens the factor pool from tenths to hundredths.
    """
    pool = (
        _DECIMAL_FACTORS_BY_DIFFICULTY.get(difficulty, _DECIMAL_FACTOR_POOL)
        if difficulty
        else _DECIMAL_FACTOR_POOL
    )
    (n1, d1), (n2, d2) = rng.choice(pool), rng.choice(pool)
    first, second = Rational(n1, d1), Rational(n2, d2)
    # Render each factor as its decimal literal so the statement reads like a decimal problem.
    a_text, b_text = _decimal_literal(n1, d1), _decimal_literal(n2, d2)
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.DECIMAL_OPERATIONS, seed, surface_format),
        kc=KnowledgeComponentId.DECIMAL_OPERATIONS,
        surface_format=surface_format,
        statement=f"{a_text} x {b_text} = ?",
        correct_value=first * second,
        representations_available=get_kc(KnowledgeComponentId.DECIMAL_OPERATIONS).representations,
        operands=(first, second),
    )


# Absolute-value input magnitudes by difficulty tier (the easy→hard ramp; CP.B): higher tiers use
# larger distances from 0. The generated input is the NEGATIVE of the chosen magnitude (so |x|
# always differs from x and the signed-not-magnitude error is genuinely wrong). ``None`` /
# out-of-range keeps the full pool (the pre-ramp default, unchanged for callers without a tier).
_ABS_MAGNITUDE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4, 5),
    2: (6, 7, 8, 9),
    3: (11, 13, 15, 18),
    4: (21, 27, 34, 42),
}
_ABS_MAGNITUDE_POOL: tuple[int, ...] = (2, 3, 5, 7, 9, 11, 15, 21, 34)


def _generate_absolute_value(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_absolute_value: find |x| as the distance of an integer from 0; the answer is non-negative.

    Samples a positive magnitude and negates it, so the input is a NEGATIVE integer and the answer
    ``abs(value)`` always differs from the signed value (the signed-not-magnitude misconception is
    then always wrong). The correct value is the SymPy ``Rational(abs(value))``. ``operands =
    (value,)`` (the signed input) so the verifier can replay signed-not-magnitude (return ``value``
    unchanged). Rendered symbolically; ``difficulty`` widens the magnitude pool.
    """
    pool = (
        _ABS_MAGNITUDE_BY_DIFFICULTY.get(difficulty, _ABS_MAGNITUDE_POOL)
        if difficulty
        else _ABS_MAGNITUDE_POOL
    )
    value = -rng.choice(pool)
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.ABSOLUTE_VALUE, seed, surface_format),
        kc=KnowledgeComponentId.ABSOLUTE_VALUE,
        surface_format=surface_format,
        statement=f"What is the absolute value of {value}?",
        correct_value=Rational(abs(value)),
        representations_available=get_kc(KnowledgeComponentId.ABSOLUTE_VALUE).representations,
        operands=(Rational(value),),
    )


# ─── Grade-6 content build (2026-05-30) — Unit-INT: Integer Arithmetic (TEKS 6.3C/D) ───

# The integer-magnitude pool for "a + b" items by difficulty tier (the easy→hard ramp; CP.B):
# higher tiers use larger magnitudes. The two operands always take OPPOSITE signs (the diagnostic
# hard case), so the magnitude is drawn per operand and the signs are assigned + then -.
_INTEGER_MAGNITUDE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (1, 2, 3, 4, 5),
    2: (3, 5, 6, 7, 8),
    3: (6, 8, 9, 11, 13),
    4: (10, 12, 15, 18, 20),
}
_INTEGER_MAGNITUDE_POOL: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15)


def _generate_integer_add_subtract(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_integer_add_subtract: add two opposite-sign integers; the signed sum is the answer.

    Builds ``a + b`` with ``a`` and ``b`` of OPPOSITE signs (the diagnostic hard case where the
    add-the-magnitudes error bites). The correct value is the SymPy sum ``a + b``.
    ``operands = (a, b)`` so the verifier can replay the sign-handling misconception
    (``|a| + |b|`` — combine as whole numbers). Rendered symbolically (a negative second operand is
    parenthesised, e.g. ``5 + (-3)``); ``difficulty`` widens the magnitude pool. With opposite signs
    and both nonzero, ``|a| + |b| > |a + b|`` always, so the misconception is always diagnostic.
    """
    pool = (
        _INTEGER_MAGNITUDE_BY_DIFFICULTY.get(difficulty, _INTEGER_MAGNITUDE_POOL)
        if difficulty
        else _INTEGER_MAGNITUDE_POOL
    )
    mag_a = rng.choice(pool)
    mag_b = rng.choice(pool)
    # Opposite signs: the seeded RNG decides which operand is the positive one.
    if rng.random() < 0.5:
        a, b = mag_a, -mag_b
    else:
        a, b = -mag_a, mag_b
    b_text = f"({b})" if b < 0 else str(b)
    statement = f"{a} + {b_text} = ?"
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.INTEGER_ADD_SUBTRACT, seed, surface_format),
        kc=KnowledgeComponentId.INTEGER_ADD_SUBTRACT,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(a + b),
        representations_available=get_kc(KnowledgeComponentId.INTEGER_ADD_SUBTRACT).representations,
        operands=(Rational(a), Rational(b)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 3: Rational Numbers ───

# The magnitude pool for "opposite of N" items by difficulty tier (the easy→hard ramp; CP.B):
# higher tiers use larger magnitudes. The SIGN is chosen separately so both "opposite of a
# positive" and "opposite of a negative" appear.
_SIGNED_MAGNITUDE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (1, 2, 3, 4, 5),
    2: (3, 5, 6, 7, 8),
    3: (7, 9, 10, 12, 15),
    4: (12, 15, 18, 20, 25),
}
_SIGNED_MAGNITUDE_POOL: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15)


def _generate_signed_numbers(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_signed_numbers: find the opposite of a signed integer; a single signed integer answer.

    Picks a nonzero magnitude and a sign (both via the seeded RNG, so both "opposite of a
    positive" and "opposite of a negative" occur). The number is ``n``; the answer is its opposite
    ``-n`` (reflection across zero). ``operands = (n,)`` so the verifier can replay the sign-error
    misconception (return ``n`` unchanged). Rendered symbolically; ``difficulty`` widens the
    magnitude pool. ``n`` is never zero, so ``-n != n`` and the misconception is always diagnostic.
    """
    pool = (
        _SIGNED_MAGNITUDE_BY_DIFFICULTY.get(difficulty, _SIGNED_MAGNITUDE_POOL)
        if difficulty
        else _SIGNED_MAGNITUDE_POOL
    )
    magnitude = rng.choice(pool)
    n = magnitude if rng.random() < 0.5 else -magnitude
    statement = f"What is the opposite of {n}?"
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.SIGNED_NUMBERS, seed, surface_format),
        kc=KnowledgeComponentId.SIGNED_NUMBERS,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(-n),
        representations_available=get_kc(KnowledgeComponentId.SIGNED_NUMBERS).representations,
        operands=(Rational(n),),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics (CCSS 6.SP.3) ───

# Value pool the data set is drawn from, by difficulty tier (CP.B easy→hard): higher tiers use
# larger values (slightly harder arithmetic). The statistic computed (mean/median/mode/range) is
# chosen separately so all four appear across seeds.
_STAT_VALUE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (1, 2, 3, 4, 5, 6),
    2: (2, 4, 6, 8, 10, 12),
    3: (5, 8, 10, 12, 15, 18),
    4: (10, 14, 18, 20, 24, 30),
}
_STAT_VALUE_POOL: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14)
_STAT_MODE_NAMES: tuple[str, ...] = ("mean", "median", "mode", "range")


def _summary_statistic(mode: str, data: list[int]) -> Rational:
    """The SymPy-exact summary statistic of ``data`` for ``mode`` (mean/median/mode/range).

    Mean divides by the count, so it can be fractional — kept exact as a ``Rational`` (never a
    float). Median is the center of the SORTED data (this generator emits odd-length median sets,
    so the median is a single middle element). Mode is the most-frequent value (the generator
    guarantees a unique mode). Range is max - min. Domain-only (SymPy decides the value; CLAUDE.md
    §8.2).
    """
    if mode == "mean":
        return sum((Rational(v) for v in data), Rational(0)) / len(data)
    if mode == "median":
        ordered = sorted(data)
        return Rational(ordered[len(ordered) // 2])
    if mode == "mode":
        return Rational(max(set(data), key=data.count))
    return Rational(max(data) - min(data))  # range


def _generate_summary_statistics(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_summary_statistics: compute one statistic of a small data set; a single numeric answer.

    Variable-length data set encoding (the 6.SP.3 wrinkle): unlike the fixed-arity numeric KCs,
    the item carries a VARIABLE-LENGTH data set PLUS which statistic to compute. We encode both in
    the existing ``operands: tuple[Rational, ...]`` with a LEADING stat-mode sentinel —
    ``operands = (mode_code, *data)`` (codes in ``_SUMMARY_STAT_MODE_CODE``). The verifier's
    median-without-sorting model decodes ``operands[0]`` to know when it applies, and matches via
    the variable-length ``operand_count=None`` row, so no fixed arity is assumed.

    The statistic (mean/median/mode/range) is chosen via the seeded RNG so all four appear. Means
    can be fractional and are kept exact as ``Rational`` (SymPy decides — §8.2). MEDIAN items are
    emitted at ODD length AND with the unsorted-middle DISTINCT from the sorted median, so the
    median-without-sorting misconception is always diagnostic. MODE items have a unique mode. The
    answer is entered in the existing symbolic editor (NO new widget). ``difficulty`` widens the
    value pool.
    """
    pool = (
        _STAT_VALUE_BY_DIFFICULTY.get(difficulty, _STAT_VALUE_POOL)
        if difficulty
        else _STAT_VALUE_POOL
    )
    mode = rng.choice(_STAT_MODE_NAMES)
    data = _sample_stat_data(rng, mode, pool)
    statement = f"Find the {mode} of {', '.join(str(v) for v in data)}."
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.SUMMARY_STATISTICS, seed, surface_format),
        kc=KnowledgeComponentId.SUMMARY_STATISTICS,
        surface_format=surface_format,
        statement=statement,
        correct_value=_summary_statistic(mode, data),
        representations_available=get_kc(KnowledgeComponentId.SUMMARY_STATISTICS).representations,
        operands=(Rational(_SUMMARY_STAT_MODE_CODE[mode]), *(Rational(v) for v in data)),
    )


def _sample_stat_data(rng: random.Random, mode: str, pool: tuple[int, ...]) -> list[int]:
    """Sample a small data set well-formed for ``mode`` (the statistic to be computed).

    - mean/range: 3-6 values drawn with replacement (any small set is valid).
    - median: an ODD-length set (3 or 5) whose UNSORTED middle differs from the sorted median, so
      the median-without-sorting misconception is genuinely wrong (re-samples until it is).
    - mode: a set with a UNIQUE most-frequent value (re-samples until the top value is unique),
      so "the mode" is well-defined.
    """
    for _ in range(200):  # bounded re-sampling; the conditions are easy to satisfy in this pool
        if mode == "median":
            size = rng.choice((3, 5))
        else:
            size = rng.randint(3, 6)
        data = [rng.choice(pool) for _ in range(size)]
        if mode == "median":
            if data[len(data) // 2] != sorted(data)[len(data) // 2]:
                return data
            continue
        if mode == "mode":
            counts = sorted((data.count(v) for v in set(data)), reverse=True)
            if len(counts) >= 2 and counts[0] > counts[1]:
                return data
            continue
        return data  # mean / range: any set works
    # Fallback (the loop above effectively always returns): a hand-built valid set per mode.
    if mode == "median":
        return [pool[2], pool[0], pool[1]]  # unsorted middle pool[0] != sorted middle pool[1]
    if mode == "mode":
        return [pool[0], pool[0], pool[1]]  # pool[0] is the unique mode
    return [pool[0], pool[1], pool[2]]


# ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics (CCSS 6.SP.4) ───

# Value pool the displayed data set is drawn from, by difficulty tier (CP.B easy→hard): higher
# tiers use a wider value range (the display spans more of the line / more bins). The question
# type (count-above / most-frequent / bin-frequency) is chosen separately so all three appear.
_DISPLAY_VALUE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (1, 2, 3, 4, 5, 6),
    2: (2, 4, 6, 8, 10, 12),
    3: (3, 6, 9, 12, 15, 18, 21),
    4: (5, 10, 15, 20, 25, 30, 35),
}
_DISPLAY_VALUE_POOL: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14)
_DISPLAY_QUESTION_NAMES: tuple[str, ...] = ("count_above", "most_frequent", "bin_freq")
_DISPLAY_BIN_WIDTH = 10  # histogram bins are width-10 (0-9, 10-19, 20-29, ...)


def _display_answer(question: str, param: int, data: list[int]) -> Rational:
    """The SymPy-exact answer for one data-display question over ``data``.

    - count_above: how many DATA POINTS are strictly greater than the threshold ``param``.
    - most_frequent: the value that appears most often (the generator guarantees a unique mode);
      ``param`` is unused.
    - bin_freq: how many data points fall in the width-10 bin whose lower bound is ``param``
      (i.e. in ``[param, param + 9]``).

    Domain-only — SymPy/the generator decides the value, never an LLM (CLAUDE.md §8.2).
    """
    if question == "count_above":
        return Rational(sum(1 for v in data if v > param))
    if question == "most_frequent":
        return Rational(max(set(data), key=data.count))
    hi = param + _DISPLAY_BIN_WIDTH - 1
    return Rational(sum(1 for v in data if param <= v <= hi))


def _display_statement(question: str, param: int, data: list[int]) -> str:
    """The textual description of the display plus the question (NO new widget; text + numeric)."""
    listing = ", ".join(str(v) for v in data)
    if question == "count_above":
        return (
            f"A dot plot stacks one dot above each value in this data set: {listing}. "
            f"How many data points are greater than {param}?"
        )
    if question == "most_frequent":
        return (
            f"A dot plot stacks one dot above each value in this data set: {listing}. "
            "Which value appears most often (the tallest stack of dots)?"
        )
    hi = param + _DISPLAY_BIN_WIDTH - 1
    return (
        f"A histogram groups this data set into bins of width {_DISPLAY_BIN_WIDTH}: {listing}. "
        f"How many data points fall in the {param}-{hi} bin?"
    )


def _sample_display_data(
    rng: random.Random, question: str, pool: tuple[int, ...]
) -> tuple[list[int], int]:
    """Sample a data set + question parameter well-formed for ``question``.

    Returns ``(data, param)``. The conditions below make each question type diagnostic and
    well-defined; the loop is bounded re-sampling (the conditions are easy to satisfy in this pool).

    - count_above: a threshold strictly inside the value range, with at least one DUPLICATED value
      strictly above it — so the distinct-value count (the modeled misconception) differs from the
      true data-point count.
    - most_frequent: a UNIQUE most-frequent value, so "the most frequent value" is well-defined.
    - bin_freq: a bin (lower bound a multiple of the width) containing at least one data point, so
      the frequency is a positive, meaningful read.
    """
    for _ in range(300):
        size = rng.randint(4, 9)
        data = [rng.choice(pool) for _ in range(size)]
        if question == "count_above":
            low, high = min(data), max(data)
            if high <= low:
                continue
            threshold = rng.randint(low, high - 1)
            above = [v for v in data if v > threshold]
            # Need a duplicate above the threshold so distinct-count != data-point-count.
            if above and len(set(above)) < len(above):
                return data, threshold
            continue
        if question == "most_frequent":
            counts = sorted((data.count(v) for v in set(data)), reverse=True)
            if len(counts) >= 2 and counts[0] > counts[1]:
                return data, 0  # param unused for most_frequent
            continue
        # bin_freq: pick a width-10 bin (lower bound a multiple of the width) that holds a point.
        bins = sorted({(v // _DISPLAY_BIN_WIDTH) * _DISPLAY_BIN_WIDTH for v in data})
        bin_lo = rng.choice(bins)
        return data, bin_lo
    # Fallback (the loop above effectively always returns): a hand-built valid item per question.
    if question == "count_above":
        return [pool[2], pool[2], pool[0]], pool[1]  # two dots > threshold, one distinct value
    if question == "most_frequent":
        return [pool[0], pool[0], pool[1]], 0  # pool[0] is the unique mode
    return [pool[0], pool[1]], (pool[0] // _DISPLAY_BIN_WIDTH) * _DISPLAY_BIN_WIDTH


def _generate_data_displays(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_data_displays: read a textually-described data display; a single numeric answer.

    Variable-length data set encoding (the 6.SP.4 wrinkle): the item carries a VARIABLE-LENGTH data
    set described in the PROMPT TEXT (a future stats-display renderer will visualize it — NO new
    widget today) PLUS which question to ask. Both are encoded in the existing
    ``operands: tuple[Rational, ...]`` with a LEADING question-type sentinel —
    ``operands = (question_code, param, *data)`` (codes in ``_DATA_DISPLAY_QUESTION_CODE``). The
    verifier's distinct-value-count model decodes ``operands[0]`` / ``operands[1]`` to know when it
    applies, and matches via the variable-length ``operand_count=None`` row, so no fixed arity is
    assumed.

    The question type (count-above / most-frequent / bin-frequency) is chosen via the seeded RNG so
    all three appear. The answer is a whole-number count or value, entered in the existing symbolic
    editor. COUNT-ABOVE items always carry a duplicated value above the threshold, so the
    distinct-value-count misconception is always diagnostic. MOST-FREQUENT items have a unique mode;
    BIN-FREQUENCY items have a non-empty bin. ``difficulty`` widens the value pool.
    """
    pool = (
        _DISPLAY_VALUE_BY_DIFFICULTY.get(difficulty, _DISPLAY_VALUE_POOL)
        if difficulty
        else _DISPLAY_VALUE_POOL
    )
    question = rng.choice(_DISPLAY_QUESTION_NAMES)
    data, param = _sample_display_data(rng, question, pool)
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.DATA_DISPLAYS, seed, surface_format),
        kc=KnowledgeComponentId.DATA_DISPLAYS,
        surface_format=surface_format,
        statement=_display_statement(question, param, data),
        correct_value=_display_answer(question, param, data),
        representations_available=get_kc(KnowledgeComponentId.DATA_DISPLAYS).representations,
        operands=(
            Rational(_DATA_DISPLAY_QUESTION_CODE[question]),
            Rational(param),
            *(Rational(v) for v in data),
        ),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 7: Categorical data (TEKS 6.12D) ───

# Per-category count pool by difficulty tier (CP.B easy->hard): higher tiers use larger counts
# (slightly harder arithmetic). The summary computed (difference / total / relative frequency) is
# chosen separately so all three appear across seeds.
_CATEGORICAL_COUNT_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4, 5, 6),
    2: (4, 6, 8, 10, 12),
    3: (8, 10, 12, 15, 18),
    4: (12, 15, 18, 20, 25),
}
_CATEGORICAL_COUNT_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12)
# Category labels for the prompt (the "what was surveyed" framing). Three categories keep the
# breakdown rich and the relative-frequency denominator (the total) distinct from any single
# category's count, so the wrong-denominator misconception is always diagnostic.
_CATEGORICAL_LABELS: tuple[str, ...] = ("red", "blue", "green")
_CATEGORICAL_MODE_NAMES: tuple[str, ...] = ("count_difference", "total", "relative_frequency")


def _categorical_summary(mode: str, counts: list[int]) -> Rational:
    """The SymPy-exact summary of a category breakdown for ``mode`` (TEKS 6.12D).

    - count_difference: how many more chose category 0 than category 1 — ``counts[0] - counts[1]``
      (the generator orders counts so this is positive).
    - total: how many were surveyed in all — ``sum(counts)``.
    - relative_frequency: the fraction of the total that chose category 0 — ``counts[0] / total``,
      kept EXACT as a ``Rational`` (never a float). Domain-only (SymPy decides; CLAUDE.md §8.2).
    """
    if mode == "count_difference":
        return Rational(counts[0] - counts[1])
    if mode == "total":
        return Rational(sum(counts))
    return Rational(counts[0], sum(counts))  # relative_frequency


def _generate_categorical_data(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_categorical_data: summarize a category breakdown; a single numeric answer (TEKS 6.12D).

    Variable-length encoding: a category breakdown has several categories, so the item carries a
    VARIABLE-LENGTH list of per-category counts PLUS which summary to compute. Both ride in the
    existing ``operands: tuple[Rational, ...]`` behind a LEADING mode sentinel —
    ``operands = (mode_code, *counts)`` (codes in ``_CATEGORICAL_MODE_CODE``). The verifier's
    wrong-denominator model decodes ``operands[0]`` to know when it applies and matches via the
    variable-length ``operand_count=None`` row, so no fixed arity is assumed.

    The summary (difference / total / relative frequency) is chosen via the seeded RNG so all three
    appear. Counts are ordered DESCENDING, so the count-difference (category 0 - category 1) is
    positive and the relative frequency of category 0 is the largest share; the relative frequency
    is exact (``Rational`` — SymPy decides, §8.2). With three categories the total always differs
    from any single count, so the wrong-denominator misconception (``count0 / count1``) is always
    diagnostic. The answer is entered in the existing symbolic editor (NO new widget).
    ``difficulty`` widens the count pool.
    """
    pool = (
        _CATEGORICAL_COUNT_BY_DIFFICULTY.get(difficulty, _CATEGORICAL_COUNT_POOL)
        if difficulty
        else _CATEGORICAL_COUNT_POOL
    )
    counts = sorted((rng.choice(pool) for _ in _CATEGORICAL_LABELS), reverse=True)
    mode = rng.choice(_CATEGORICAL_MODE_NAMES)
    breakdown = ", ".join(
        f"{c} chose {label}" for c, label in zip(counts, _CATEGORICAL_LABELS, strict=True)
    )
    if mode == "count_difference":
        question = f"how many more chose {_CATEGORICAL_LABELS[0]} than {_CATEGORICAL_LABELS[1]}?"
    elif mode == "total":
        question = "how many were surveyed in all?"
    else:  # relative_frequency
        question = f"what fraction of those surveyed chose {_CATEGORICAL_LABELS[0]}?"
    statement = f"In a survey, {breakdown}. So {question}"
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.CATEGORICAL_DATA, seed, surface_format),
        kc=KnowledgeComponentId.CATEGORICAL_DATA,
        surface_format=surface_format,
        statement=statement,
        correct_value=_categorical_summary(mode, counts),
        representations_available=get_kc(KnowledgeComponentId.CATEGORICAL_DATA).representations,
        operands=(Rational(_CATEGORICAL_MODE_CODE[mode]), *(Rational(c) for c in counts)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit-INT: Integer multiply & divide (TEKS 6.3C/D) ───

# Operand-magnitude pool for "a × b" / "a ÷ b" items by difficulty tier (the easy→hard ramp; CP.B):
# higher tiers use larger magnitudes. Both operands are nonzero (so the result is nonzero and the
# sign-rule flip is always diagnostic); the sign of each is chosen separately so like- AND
# unlike-sign pairs both appear. Divide items reuse the same pool for the QUOTIENT and the divisor,
# then form the dividend as their product, guaranteeing an even (integer) division.
_INT_MUL_DIV_MAGNITUDE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (1, 2, 3, 4, 5),
    2: (3, 4, 5, 6, 7),
    3: (6, 7, 8, 9, 10),
    4: (8, 9, 10, 11, 12),
}
_INT_MUL_DIV_MAGNITUDE_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12)


def _generate_integer_multiply_divide(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_integer_multiply_divide: multiply OR divide two signed integers; the signed result.

    An operation-mode flag (the seeded RNG picks multiply vs divide) decides the item. MULTIPLY:
    pick two signed nonzero magnitudes ``a, b``; the answer is ``a * b``. DIVIDE: pick a signed
    nonzero quotient ``q`` and divisor ``b``, form the dividend ``a = q * b``; the answer is
    ``a / b == q`` — so the division ALWAYS divides evenly (an integer quotient). Each operand's
    sign is chosen independently, so like-sign and unlike-sign pairs both occur (the sign rule is
    exercised in every case). ``operands = (a, b, mode)`` with ``mode = 1`` (multiply) / ``0``
    (divide) so the verifier can replay the sign-rule error (``-(a*b)`` / ``-(a/b)``);
    ``difficulty`` widens the magnitude pool. The result is never zero (both operands nonzero), so
    ``-result != result`` and the misconception is always diagnostic.
    """
    pool = (
        _INT_MUL_DIV_MAGNITUDE_BY_DIFFICULTY.get(difficulty, _INT_MUL_DIV_MAGNITUDE_POOL)
        if difficulty
        else _INT_MUL_DIV_MAGNITUDE_POOL
    )
    multiply = rng.random() < 0.5
    sign_first = 1 if rng.random() < 0.5 else -1
    sign_second = 1 if rng.random() < 0.5 else -1
    if multiply:
        a = sign_first * rng.choice(pool)
        b = sign_second * rng.choice(pool)
        correct = a * b
        b_text = f"({b})" if b < 0 else str(b)
        statement = f"{a} × {b_text} = ?"
        mode = 1
    else:
        # Build an even division: dividend = quotient × divisor, so a ÷ b is an exact integer.
        quotient = sign_first * rng.choice(pool)
        b = sign_second * rng.choice(pool)
        a = quotient * b
        correct = quotient
        b_text = f"({b})" if b < 0 else str(b)
        statement = f"{a} ÷ {b_text} = ?"
        mode = 0
    return Problem(
        problem_id=_generated_id(
            KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE, seed, surface_format
        ),
        kc=KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(correct),
        representations_available=get_kc(
            KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE
        ).representations,
        operands=(Rational(a), Rational(b), Rational(mode)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 6: Geometry (TEKS 6.8A) ───

# The two known angles a, b for a missing-angle item (their sum stays < 180 so the third angle is
# positive) and the base/height for an area item, by difficulty tier (the easy→hard ramp; CP.B):
# higher tiers use larger measures. Angle pairs are listed explicitly so a + b < 180 always holds.
_TRIANGLE_ANGLE_PAIRS_BY_DIFFICULTY: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((30, 60), (45, 45), (60, 60), (40, 50)),
    2: ((35, 70), (55, 65), (50, 80), (25, 75)),
    3: ((48, 73), (62, 84), (37, 96), (53, 88)),
    4: ((71, 94), (66, 107), (83, 89), (58, 119)),
}
_TRIANGLE_ANGLE_PAIRS_POOL: tuple[tuple[int, int], ...] = (
    (30, 60),
    (45, 45),
    (40, 50),
    (35, 70),
    (55, 65),
    (50, 80),
    (48, 73),
    (62, 84),
    (37, 96),
)
# Base/height pairs whose PRODUCT is even, so the area ½·b·h is always a whole number.
_TRIANGLE_BASE_HEIGHT_BY_DIFFICULTY: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((4, 3), (2, 5), (6, 2), (4, 4)),
    2: ((6, 5), (8, 3), (4, 7), (10, 2)),
    3: ((9, 8), (12, 5), (7, 6), (14, 4)),
    4: ((16, 9), (15, 8), (18, 7), (20, 6)),
}
_TRIANGLE_BASE_HEIGHT_POOL: tuple[tuple[int, int], ...] = (
    (4, 3),
    (2, 5),
    (6, 2),
    (6, 5),
    (8, 3),
    (4, 7),
    (9, 8),
    (12, 5),
    (7, 6),
)


def _generate_triangle_properties(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_triangle_properties: find a missing angle OR a triangle's area; a single numeric answer.

    An item-mode flag (the seeded RNG picks angle vs area) decides the item. MISSING ANGLE (mode 0):
    pick two angles ``a, b`` whose sum is < 180; the answer is the third angle ``180 - a - b``. AREA
    (mode 1): pick a base ``a`` and height ``b`` whose product is even; the answer is the area
    ``a*b/2`` (a whole number). ``operands = (a, b, mode)`` so the verifier can replay the
    triangle-formula error (subtract from 90 / drop the ½); ``difficulty`` widens the measure pools.
    The figure is described in the statement (the display-only stimulus convention) but the answer
    stays NUMERIC, entered in the existing editor. The wrong value the misconception predicts is
    always distinct from the correct one (an angle off by 90; an area off by a factor of 2), so the
    diagnosis is reliable.
    """
    angle_mode = rng.random() < 0.5
    if angle_mode:
        pairs = (
            _TRIANGLE_ANGLE_PAIRS_BY_DIFFICULTY.get(difficulty, _TRIANGLE_ANGLE_PAIRS_POOL)
            if difficulty
            else _TRIANGLE_ANGLE_PAIRS_POOL
        )
        a, b = rng.choice(pairs)
        correct = Rational(180 - a - b)
        statement = (
            f"A triangle has two angles measuring {a}° and {b}°. "
            "What is the measure of the third angle, in degrees?"
        )
        mode = 0
    else:
        pairs = (
            _TRIANGLE_BASE_HEIGHT_BY_DIFFICULTY.get(difficulty, _TRIANGLE_BASE_HEIGHT_POOL)
            if difficulty
            else _TRIANGLE_BASE_HEIGHT_POOL
        )
        a, b = rng.choice(pairs)
        correct = Rational(a * b, 2)
        statement = (
            f"A triangle has a base of {a} units and a height of {b} units. "
            "What is its area, in square units?"
        )
        mode = 1
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.TRIANGLE_PROPERTIES, seed, surface_format),
        kc=KnowledgeComponentId.TRIANGLE_PROPERTIES,
        surface_format=surface_format,
        statement=statement,
        correct_value=correct,
        representations_available=get_kc(KnowledgeComponentId.TRIANGLE_PROPERTIES).representations,
        operands=(Rational(a), Rational(b), Rational(mode)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───

# Write-expression phrase templates: (phrase with {v}/{c} slots, builder of the canonical SymPy
# expression). Each builder takes the variable Symbol and the integer constant and returns the
# correct expression; ``sstr`` renders it to the canonical answer string. Mixes commutative
# (addition, multiplication — reversing is still equivalent, no wrong order) and non-commutative
# (subtraction, division — where the reversed-operands misconception produces a genuinely wrong
# form). 6th-grade single-variable phrases (6.EE.2a).
_EXPRESSION_TEMPLATES: tuple[tuple[str, Callable[[Symbol, int], object]], ...] = (
    ("{c} more than {v}", lambda v, c: v + c),  # commutative
    ("{c} added to {v}", lambda v, c: v + c),  # commutative
    ("{v} increased by {c}", lambda v, c: v + c),  # commutative
    ("{c} times {v}", lambda v, c: c * v),  # commutative
    ("{c} less than {v}", lambda v, c: v - c),  # non-commutative: v - c, NOT c - v
    ("{v} decreased by {c}", lambda v, c: v - c),  # non-commutative
    ("{v} divided by {c}", lambda v, c: v / c),  # non-commutative: v / c, NOT c / v
)
_EXPRESSION_VARIABLES: tuple[str, ...] = ("p", "n", "x", "y", "t")
# Constants by difficulty tier (the easy→hard ramp; CP.B): higher tiers use larger numbers.
_EXPRESSION_CONST_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4, 5),
    2: (6, 7, 8, 9),
    3: (11, 12, 15, 20),
    4: (25, 30, 40, 50),
}
_EXPRESSION_CONST_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 8, 10, 12)


def _generate_write_expressions(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_write_expressions: write an algebraic expression from a word phrase.

    Picks a phrase template, a variable, and a constant (seeded), builds the CANONICAL SymPy
    expression, and renders it to the answer string in ``correct_expression`` (e.g. "p - 7"). The
    answer is an EXPRESSION graded by SymPy equivalence; ``correct_value`` is a ``Rational(0)``
    placeholder (never read on the EXPRESSION path). ``operands`` is empty; the misconception
    (reversed-operands) is replayed from ``correct_expression`` by the verifier, not from operands.
    """
    const_pool = (
        _EXPRESSION_CONST_BY_DIFFICULTY.get(difficulty, _EXPRESSION_CONST_POOL)
        if difficulty
        else _EXPRESSION_CONST_POOL
    )
    phrase_template, build = rng.choice(_EXPRESSION_TEMPLATES)
    variable = Symbol(rng.choice(_EXPRESSION_VARIABLES))
    constant = rng.choice(const_pool)
    canonical = build(variable, constant)
    phrase = phrase_template.format(v=variable.name, c=constant)
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.WRITE_EXPRESSIONS, seed, surface_format),
        kc=KnowledgeComponentId.WRITE_EXPRESSIONS,
        surface_format=surface_format,
        statement=f'Write an expression for "{phrase}".',
        correct_value=Rational(0),  # placeholder; the EXPRESSION path grades correct_expression
        representations_available=get_kc(KnowledgeComponentId.WRITE_EXPRESSIONS).representations,
        answer_kind=AnswerKind.EXPRESSION,
        correct_expression=sstr(canonical),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───

# Operand pools for "evaluate a*x + b at x" by difficulty tier (the easy→hard ramp; CP.B). Higher
# tiers use larger coefficients/values. a >= 2 and b >= 1 in every tier, so the multiply-first
# answer a*x + b is always DISTINCT from the left-to-right slip a*(x + b) — the misconception
# stays diagnostic. (a, x, b) are drawn independently from these pools.
_EVAL_COEFF_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4),
    2: (3, 4, 5),
    3: (4, 6, 7),
    4: (6, 8, 9),
}
_EVAL_VALUE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4),
    2: (4, 5, 6),
    3: (6, 7, 8),
    4: (8, 9, 10),
}
_EVAL_CONST_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (1, 2, 3),
    2: (2, 4, 5),
    3: (5, 6, 7),
    4: (7, 9, 11),
}
_EVAL_COEFF_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7)
_EVAL_VALUE_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8)
_EVAL_CONST_POOL: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)


def _generate_evaluate_expressions(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_evaluate_expressions: substitute a value and evaluate a*x + b; a single numeric answer.

    Picks a coefficient ``a`` (>= 2), a value ``x``, and a constant ``b`` (>= 1) via the seeded
    RNG; the answer is ``a*x + b`` (multiply before add). ``operands = (a, x, b)`` so the verifier
    can replay the order-of-operations slip (``a*(x + b)``). Two REAL surfaces share this answer
    (so the KC is masterable across representations, PROJECT.md §3.4 rule 2):

      - **SYMBOLIC** (default) — "Evaluate {a}x + {b} when x = {x}." (the symbolic form);
      - **AREA_MODEL** — an array/area picture: ``a`` rows of ``x`` squares, plus ``b`` extra; the
        total count IS ``a*x + b`` (the visual, magnitude-grounded form).

    The math is sampled before the format is applied, so the same seed yields identical operands
    in either surface. ``a >= 2`` and ``b >= 1`` keep the slip ``a*(x + b)`` distinct from the
    correct ``a*x + b`` (they differ by ``(a - 1)*b > 0``), so the misconception is diagnostic.
    """
    coeff_pool = (
        _EVAL_COEFF_BY_DIFFICULTY.get(difficulty, _EVAL_COEFF_POOL)
        if difficulty
        else _EVAL_COEFF_POOL
    )
    value_pool = (
        _EVAL_VALUE_BY_DIFFICULTY.get(difficulty, _EVAL_VALUE_POOL)
        if difficulty
        else _EVAL_VALUE_POOL
    )
    const_pool = (
        _EVAL_CONST_BY_DIFFICULTY.get(difficulty, _EVAL_CONST_POOL)
        if difficulty
        else _EVAL_CONST_POOL
    )
    a = rng.choice(coeff_pool)
    x = rng.choice(value_pool)
    b = rng.choice(const_pool)
    if surface_format is Representation.AREA_MODEL:
        statement = (
            f"A picture shows {a} rows of {x} squares, plus {b} more squares. "
            f"How many squares is that in all?"
        )
    else:
        statement = f"Evaluate {a}x + {b} when x = {x}."
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.EVALUATE_EXPRESSIONS, seed, surface_format),
        kc=KnowledgeComponentId.EVALUATE_EXPRESSIONS,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(a * x + b),
        representations_available=get_kc(KnowledgeComponentId.EVALUATE_EXPRESSIONS).representations,
        operands=(Rational(a), Rational(x), Rational(b)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───

# The base/exponent pools for "evaluate base^exp" items by difficulty tier (the easy→hard ramp;
# CP.B): higher tiers use larger bases and exponents. base >= 2 and exp >= 2 throughout, with the
# single (base == 2, exp == 2) case excluded at generation, so the correct power base**exp is
# always DISTINCT from the multiply slip base*exp (the misconception stays diagnostic). The
# exponent stays modest (<= 5) so the answer is a friendly 6th-grade whole number, not astronomical.
_EXPONENT_BASE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3),
    2: (3, 4, 5),
    3: (4, 5, 6),
    4: (5, 6, 7, 8),
}
_EXPONENT_POWER_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3),
    2: (2, 3),
    3: (3, 4),
    4: (3, 4, 5),
}
_EXPONENT_BASE_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8)
_EXPONENT_POWER_POOL: tuple[int, ...] = (2, 3, 4, 5)


def _generate_exponents(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_exponents: evaluate a whole-number power base^exp; a single numeric answer.

    Picks a base (>= 2) and an exponent (>= 2) via the seeded RNG; the answer is ``base ** exp``
    (repeated multiplication). ``operands = (base, exp)`` so the verifier can replay the
    multiply-base-by-exponent slip (``base * exp``). Two REAL surfaces share this answer (so the KC
    is masterable across representations, PROJECT.md §3.4 rule 2):

      - **SYMBOLIC** (default) — "What is 3^4?" (the symbolic power);
      - **AREA_MODEL** — the geometric picture: base^2 as the area of a square of side base,
        base^3 as the volume of a cube of edge base (the visual, magnitude-grounded form).

    The single ``(base, exp) == (2, 2)`` case is excluded because there ``base ** exp == base *
    exp`` (4 == 4), which would make the misconception indistinguishable from the correct; every
    other in-scope pair has ``base ** exp != base * exp``, so the slip is always diagnostic. The
    math is sampled before the format is applied, so the same seed yields identical operands in
    either surface. ``difficulty`` widens the base/exponent pools.
    """
    base_pool = (
        _EXPONENT_BASE_BY_DIFFICULTY.get(difficulty, _EXPONENT_BASE_POOL)
        if difficulty
        else _EXPONENT_BASE_POOL
    )
    power_pool = (
        _EXPONENT_POWER_BY_DIFFICULTY.get(difficulty, _EXPONENT_POWER_POOL)
        if difficulty
        else _EXPONENT_POWER_POOL
    )
    base = rng.choice(base_pool)
    exponent = rng.choice(power_pool)
    # Resample the one collision case (2^2 == 2*2) so the multiply slip stays distinct (AREA_MODEL
    # for exp 2 is a square's area; exp 3 a cube's volume; higher exponents stay symbolic).
    while base == 2 and exponent == 2:
        base = rng.choice(base_pool)
        exponent = rng.choice(power_pool)
    if surface_format is Representation.AREA_MODEL:
        if exponent == 2:
            statement = (
                f"A square has sides of length {base}. How many unit squares cover its area?"
            )
        elif exponent == 3:
            statement = f"A cube has edges of length {base}. How many unit cubes fill its volume?"
        else:
            statement = (
                f"Start with 1 and multiply by {base} a total of {exponent} times "
                f"(growing {exponent} steps). What number do you reach?"
            )
    else:
        statement = f"What is {base}^{exponent}?"
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.EXPONENTS, seed, surface_format),
        kc=KnowledgeComponentId.EXPONENTS,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(base**exponent),
        representations_available=get_kc(KnowledgeComponentId.EXPONENTS).representations,
        operands=(Rational(base), Rational(exponent)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 5: Equations & Inequalities ───

# The (b/a) coefficient pool by difficulty tier (the easy→hard ramp; CP.B): higher tiers use
# larger numbers. Used as the additive constant ``b`` (x + b = c) and the multiplicative
# coefficient ``a`` (a*x = c).
_ONE_STEP_COEFF_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (1, 2, 3, 4, 5),
    2: (4, 5, 6, 7, 8),
    3: (7, 9, 10, 11, 12),
    4: (12, 15, 18, 20, 25),
}
_ONE_STEP_COEFF_POOL: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12)
# The solution (value of x) pool — kept whole-number and 6th-grade-sized so a*x = c divides
# evenly and x + b = c stays in scope (CURRICULUM_STANDARD.md §6 — one-step over the rationals,
# whole-number answers at this grade).
_ONE_STEP_SOLUTION_POOL: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
# Story templates for the WORD_PROBLEM surface, one per mode. ``{x}`` is never shown (it is the
# unknown); the slots are the coefficient and the result. additive: "had x, got b more, now c".
# multiplicative: "a equal groups hold c in all, how many per group".
_ONE_STEP_ADD_STORY = (
    "{name} had some {item}, then got {b} more, and now has {c}. "
    "How many {item} did {name} start with?"
)
_ONE_STEP_MUL_STORY = (
    "{name} packs {item} into {a} equal boxes and uses {c} {item} in all. "
    "How many {item} go in each box?"
)
_ONE_STEP_NAMES: tuple[str, ...] = ("Maria", "Sam", "Leo", "Ava", "Theo")
_ONE_STEP_ITEMS: tuple[str, ...] = ("stickers", "marbles", "cards", "apples", "coins")


def _generate_one_step_equations(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_one_step_equations: solve a one-step equation for x; the answer is the value of x.

    ONE KC, TWO modes behind an operand flag (decided design, 6.EE.7): mode 0 is the additive
    equation ``x + b = c`` (solve ``x = c - b``); mode 1 is the multiplicative equation ``a*x = c``
    (solve ``x = c / a``). The math (operands, correct value) is sampled FIRST and identically for
    every surface, so the same seed yields the same equation whether shown symbolically or as a
    story (mastery rule 2 — two surfaces of one skill). ``operands = (mode, p, q)`` lets the
    verifier replay the inverse-operation misconception uniformly.

    The whole-number solution ``x`` and coefficient are drawn from seeded pools so ``a*x = c``
    divides evenly. The mode flag is sampled so BOTH equation types appear across seeds. The wrong
    inverse value is guaranteed DISTINCT from the correct one: for the additive case ``p != 0``
    forces ``c + b != c - b``; for the rare multiplicative coincidence (``c - a == c / a``) the
    coefficient is resampled.
    """
    pool = (
        _ONE_STEP_COEFF_BY_DIFFICULTY.get(difficulty, _ONE_STEP_COEFF_POOL)
        if difficulty
        else _ONE_STEP_COEFF_POOL
    )
    additive = rng.random() < 0.5
    x_value = rng.choice(_ONE_STEP_SOLUTION_POOL)
    coeff = rng.choice(pool)
    if additive:
        mode, b, c = 0, coeff, coeff + x_value  # x + b = c, x = c - b = x_value
        correct = Rational(x_value)
        operands = (Rational(mode), Rational(b), Rational(c))
        symbolic_statement = f"Solve for x: x + {b} = {c}"
        story = _ONE_STEP_ADD_STORY.format(
            name=rng.choice(_ONE_STEP_NAMES), item=rng.choice(_ONE_STEP_ITEMS), b=b, c=c
        )
    else:
        # a*x = c with c = a*x_value, so x = c / a = x_value divides evenly. Resample the
        # coefficient on the rare coincidence where the wrong inverse (c - a) equals x_value
        # (otherwise the misconception value would equal the correct answer and not be diagnostic).
        a = coeff
        while a * x_value - a == x_value:
            a = rng.choice(pool)
        c = a * x_value
        mode = 1
        correct = Rational(x_value)
        operands = (Rational(mode), Rational(a), Rational(c))
        symbolic_statement = f"Solve for x: {a}x = {c}"
        story = _ONE_STEP_MUL_STORY.format(
            name=rng.choice(_ONE_STEP_NAMES), item=rng.choice(_ONE_STEP_ITEMS), a=a, c=c
        )
    statement = story if surface_format is Representation.WORD_PROBLEM else symbolic_statement
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.ONE_STEP_EQUATIONS, seed, surface_format),
        kc=KnowledgeComponentId.ONE_STEP_EQUATIONS,
        surface_format=surface_format,
        statement=statement,
        correct_value=correct,
        representations_available=get_kc(KnowledgeComponentId.ONE_STEP_EQUATIONS).representations,
        operands=operands,
    )


# Equivalent-expression templates (6.EE.3 / 6.EE.4): the learner is shown a GIVEN expression and
# must type an EQUIVALENT one. Each template builds, from the variable and two integers, a tuple of
# (the GIVEN expression as a folded SymPy object, its CANONICAL equivalent, a human-readable display
# string with implicit multiplication). DISTRIBUTE: the given is a product ``c*(v + b)`` (kept
# folded, so the distributive-error misconception can mis-distribute it onto only the first term),
# canonical is its expansion ``c*v + c*b``. COMBINE: the given is a like-terms sum (rendered
# ``a*v + b*v`` but SymPy auto-combines it on construction), canonical is the combined ``(a+b)*v``;
# it carries no distributive structure (distributive_error returns None for it). 6th-grade single-
# variable, integer-coefficient expressions.
def _distribute_given(v: Symbol, c: int, b: int) -> tuple[Expr, Expr, str]:
    # Build the product UNEVALUATED so SymPy keeps it folded as c*(v + b) (a plain ``c * (v + b)``
    # auto-distributes to c*v + c*b on construction). ``sstr`` then renders "c*(v + b)", the form
    # the distributive-error misconception mis-distributes; the canonical is the expansion.
    folded: Expr = Mul(c, Add(v, b, evaluate=False), evaluate=False)
    return folded, folded.expand(), f"{c}({v.name} + {b})"


def _combine_given(v: Symbol, a: int, b: int) -> tuple[Expr, Expr, str]:
    combined: Expr = a * v + b * v  # SymPy auto-combines like terms to (a + b)*v
    return combined, combined, f"{a}{v.name} + {b}{v.name}"


_EQUIVALENT_TEMPLATES: tuple[Callable[[Symbol, int, int], tuple[Expr, Expr, str]], ...] = (
    _distribute_given,
    _combine_given,
)
_EQUIVALENT_VARIABLES: tuple[str, ...] = ("x", "y", "n", "p", "t")
# Coefficient/constant pools by difficulty tier (the easy→hard ramp; CP.B): higher tiers use
# larger numbers. Both integer slots draw from the same tier pool (two independent draws).
_EQUIVALENT_NUM_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4, 5),
    2: (3, 4, 6, 7),
    3: (5, 6, 8, 9),
    4: (7, 9, 11, 12),
}
_EQUIVALENT_NUM_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9)


def _generate_equivalent_expressions(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_equivalent_expressions: produce an expression equivalent to a GIVEN one (6.EE.3/4).

    Picks a template (distribute a product, or combine like terms), a variable, and two integers
    (seeded), builds the GIVEN expression and its CANONICAL equivalent. The given (un-rewritten)
    form goes in ``source_expression`` (e.g. "3*(x + 2)"); the canonical equivalent goes in
    ``correct_expression`` (e.g. "3*x + 6"). The answer is an EXPRESSION graded by SymPy
    equivalence; ``correct_value`` is a ``Rational(0)`` placeholder (never read on the EXPRESSION
    path). The distributive-error misconception is replayed from ``source_expression`` by the
    verifier, not from operands (``operands`` is empty).
    """
    num_pool = (
        _EQUIVALENT_NUM_BY_DIFFICULTY.get(difficulty, _EQUIVALENT_NUM_POOL)
        if difficulty
        else _EQUIVALENT_NUM_POOL
    )
    build = rng.choice(_EQUIVALENT_TEMPLATES)
    variable = Symbol(rng.choice(_EQUIVALENT_VARIABLES))
    first = rng.choice(num_pool)
    second = rng.choice(num_pool)
    given, canonical, given_text = build(variable, first, second)
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.EQUIVALENT_EXPRESSIONS, seed, surface_format),
        kc=KnowledgeComponentId.EQUIVALENT_EXPRESSIONS,
        surface_format=surface_format,
        statement=f'Write an equivalent expression for "{given_text}".',
        correct_value=Rational(0),  # placeholder; the EXPRESSION path grades correct_expression
        representations_available=get_kc(
            KnowledgeComponentId.EQUIVALENT_EXPRESSIONS
        ).representations,
        answer_kind=AnswerKind.EXPRESSION,
        correct_expression=sstr(canonical),
        source_expression=sstr(given),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 5: Inequalities (6.EE.8) ───

# Inequality-phrase templates: (constraint phrase with a {c} slot, the ASCII relational operator
# the phrase names). The learner writes ``x OP c``. Each phrase maps to EXACTLY one direction +
# strictness so the canonical answer is unambiguous (the flipped-direction misconception is the
# wrong direction, not a different reading): "at least"/"no less than" = >= ; "more than"/"over" =
# strict > ; "at most"/"no more than" = <= ; "less than"/"under"/"below" = strict <. Single-variable
# ``x``, matching the frozen widget contract answer string ("x>=5").
_INEQUALITY_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("A number x is at least {c}", ">="),
    ("A number x is no less than {c}", ">="),
    ("A number x is more than {c}", ">"),
    ("A number x is greater than {c}", ">"),
    ("A number x is at most {c}", "<="),
    ("A number x is no more than {c}", "<="),
    ("A number x is less than {c}", "<"),
    ("A number x is under {c}", "<"),
)
# Bounds by difficulty tier (the easy->hard ramp; CP.B): higher tiers use larger numbers.
_INEQUALITY_BOUND_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4, 5),
    2: (6, 7, 8, 10),
    3: (12, 13, 15, 18),
    4: (20, 25, 30, 50),
}
_INEQUALITY_BOUND_POOL: tuple[int, ...] = (3, 5, 7, 10, 12, 13, 18, 21)


def _generate_inequalities(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_inequalities: write a one-variable inequality from a constraint phrase (6.EE.8).

    Picks a constraint phrase + its single unambiguous operator and a bound (seeded), and renders
    the canonical answer string ``x OP c`` (e.g. "x >= 5") into ``correct_inequality``. The answer
    is an INEQUALITY graded by SymPy RELATIONAL equivalence; ``correct_value`` is a ``Rational(0)``
    placeholder (never read on the INEQUALITY path). ``operands`` is empty; the flipped-direction
    misconception is replayed from ``correct_inequality`` by the verifier, not from operands.
    """
    bound_pool = (
        _INEQUALITY_BOUND_BY_DIFFICULTY.get(difficulty, _INEQUALITY_BOUND_POOL)
        if difficulty
        else _INEQUALITY_BOUND_POOL
    )
    phrase_template, operator = rng.choice(_INEQUALITY_TEMPLATES)
    bound = rng.choice(bound_pool)
    phrase = phrase_template.format(c=bound)
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.INEQUALITIES, seed, surface_format),
        kc=KnowledgeComponentId.INEQUALITIES,
        surface_format=surface_format,
        statement=f"Write an inequality for: {phrase}.",
        correct_value=Rational(0),  # placeholder; the INEQUALITY path grades correct_inequality
        representations_available=get_kc(KnowledgeComponentId.INEQUALITIES).representations,
        answer_kind=AnswerKind.INEQUALITY,
        correct_inequality=f"x {operator} {bound}",
    )


# ─── Grade-6 content build (2026-05-30) — Unit 3: The coordinate plane (6.NS.8) ───

# Coordinate magnitudes by difficulty tier (the easy→hard ramp; CP.B): higher tiers reach farther
# from the origin and across more quadrants. Tier 1 stays small and near the axes; tier 4 spans the
# full four-quadrant range a 6th-grader works in.
_COORDINATE_RANGE_BY_DIFFICULTY: dict[int, int] = {1: 3, 2: 5, 3: 8, 4: 10}
_COORDINATE_RANGE_DEFAULT = 6


def _format_point(x: int, y: int) -> str:
    """Render one integer point in the frozen ``(x,y)`` answer shape (no spaces)."""
    return f"({x},{y})"


def _format_points(points: tuple[tuple[int, int], ...]) -> str:
    """Render an ordered list of points as the frozen ``(x,y),(x,y),...`` answer string."""
    return ",".join(_format_point(x, y) for x, y in points)


def _nonzero(rng: random.Random, bound: int) -> int:
    """A nonzero integer in ``[-bound, bound]`` — keeps a 'plot the point' item off the axes so the
    quadrant (and thus the sign pattern the misconception perturbs) is unambiguous."""
    value = 0
    while value == 0:
        value = rng.randint(-bound, bound)
    return value


def _generate_coordinate_plane(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_coordinate_plane: identify/plot points in the four-quadrant plane (6.NS.8 / TEKS 6.11A).

    Picks one of three item kinds (seeded): plot a single point, reflect a point across an axis, or
    plot the vertices of an axis-aligned rectangle (a polygon). The answer is the resulting SET of
    integer points, rendered to the canonical ``correct_points`` string ("(2,-1)" or
    "(0,0),(3,0),(0,2),(3,2)"). The answer kind is COORDINATE — graded by the verifier as an
    ORDER-INSENSITIVE set, never a magnitude; ``correct_value`` is a ``Rational(0)`` placeholder
    (never read on the COORDINATE path). ``operands`` is empty; the coordinate-swap misconception is
    replayed from ``correct_points`` by the verifier, not from operands.
    """
    bound = (
        _COORDINATE_RANGE_BY_DIFFICULTY.get(difficulty, _COORDINATE_RANGE_DEFAULT)
        if difficulty
        else _COORDINATE_RANGE_DEFAULT
    )
    kind = rng.choice(("plot", "reflect", "rectangle"))
    if kind == "plot":
        x, y = _nonzero(rng, bound), _nonzero(rng, bound)
        statement = f"Plot the point ({x}, {y})."
        points: tuple[tuple[int, int], ...] = ((x, y),)
    elif kind == "reflect":
        x, y = _nonzero(rng, bound), _nonzero(rng, bound)
        axis = rng.choice(("x", "y"))
        # Reflecting across the x-axis negates y; across the y-axis negates x.
        reflected = (x, -y) if axis == "x" else (-x, y)
        statement = f"Reflect the point ({x}, {y}) across the {axis}-axis and plot the image."
        points = (reflected,)
    else:  # rectangle: four axis-aligned corners spanning two distinct x's and two distinct y's
        x1 = rng.randint(-bound, bound)
        x2 = x1 + rng.randint(1, max(1, bound))  # strictly to the right — a real, positive width
        y1 = rng.randint(-bound, bound)
        y2 = y1 + rng.randint(1, max(1, bound))  # strictly above — a real, positive height
        statement = (
            f"Plot the four corners of the rectangle with width from x = {x1} to x = {x2} and "
            f"height from y = {y1} to y = {y2}."
        )
        points = ((x1, y1), (x2, y1), (x1, y2), (x2, y2))
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.COORDINATE_PLANE, seed, surface_format),
        kc=KnowledgeComponentId.COORDINATE_PLANE,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(0),  # placeholder; the COORDINATE path grades correct_points
        representations_available=get_kc(KnowledgeComponentId.COORDINATE_PLANE).representations,
        answer_kind=AnswerKind.COORDINATE,
        correct_points=_format_points(points),
    )


# ─── Grade-6 content build (2026-05-31) — Unit 4/5: Dependent variables (CCSS 6.EE.9) ───

# The rate ``a`` (the multiplicative relationship y = a*x) and the independent value ``x`` by
# difficulty tier (the easy→hard ramp; CP.B): higher tiers use larger rates/values. ``a >= 2`` and
# ``x >= 2`` throughout, with the single ``(a == 2, x == 2)`` case excluded at generation, so the
# correct dependent value ``a*x`` is always DISTINCT from the additive-confusion slip ``a + x``
# (they are equal only at a = x = 2), keeping the misconception diagnostic.
_DEPENDENT_RATE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4),
    2: (3, 4, 5),
    3: (4, 6, 7),
    4: (6, 8, 9),
}
_DEPENDENT_VALUE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4),
    2: (4, 5, 6),
    3: (5, 7, 8),
    4: (8, 9, 10),
}
_DEPENDENT_RATE_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7)
_DEPENDENT_VALUE_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8)


def _generate_dependent_vars(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_dependent_vars: relate a dependent variable to an independent one (CCSS 6.EE.9).

    The relationship is ``y = a*x``; given the INDEPENDENT value ``x``, the DEPENDENT value is
    ``y = a*x``. The math (rate ``a``, value ``x``) is sampled FIRST and identically for every
    surface, so the same seed yields the same relationship whether shown symbolically or on the
    coordinate plane (mastery rule 2 — two surfaces of one skill). ``operands = (a, x)`` lets the
    verifier replay the dependent-independent-swap misconception (additive ``a + x``).

    Two REAL surfaces share this relationship (so the KC is masterable, PROJECT.md §3.4 rule 2):

      - **SYMBOLIC** (default) — "y = {a}x. What is y when x = {x}?" — a single NUMERIC dependent
        value entered in the NUMBER_ENTRY editor (graded by SymPy substitute-and-evaluate);
      - **COORDINATE_PLANE** — "y = {a}x. Plot the point (x, y) when x = {x}." — the COORDINATE
        answer "(x, a*x)" graded ORDER-INSENSITIVELY by the existing coordinate verifier, rendered
        by the live coordinate-plane widget (REUSES that contract, no new widget).

    ``a >= 2`` and ``x >= 2`` keep the additive slip ``a + x`` distinct from the correct ``a*x``;
    the single ``(2, 2)`` collision (where ``2 + 2 == 2 * 2``) is resampled, so the misconception is
    always diagnostic. ``difficulty`` widens the rate/value pools.
    """
    rate_pool = (
        _DEPENDENT_RATE_BY_DIFFICULTY.get(difficulty, _DEPENDENT_RATE_POOL)
        if difficulty
        else _DEPENDENT_RATE_POOL
    )
    value_pool = (
        _DEPENDENT_VALUE_BY_DIFFICULTY.get(difficulty, _DEPENDENT_VALUE_POOL)
        if difficulty
        else _DEPENDENT_VALUE_POOL
    )
    a = rng.choice(rate_pool)
    x = rng.choice(value_pool)
    # Resample the one collision (2 + 2 == 2 * 2) so the additive slip stays distinct from a*x.
    while a == 2 and x == 2:
        a = rng.choice(rate_pool)
        x = rng.choice(value_pool)
    dependent = a * x
    if surface_format is Representation.COORDINATE_PLANE:
        statement = f"The rule is y = {a}x. Plot the point (x, y) on the line when x = {x}."
        return Problem(
            problem_id=_generated_id(KnowledgeComponentId.DEPENDENT_VARS, seed, surface_format),
            kc=KnowledgeComponentId.DEPENDENT_VARS,
            surface_format=surface_format,
            statement=statement,
            correct_value=Rational(0),  # placeholder; the COORDINATE path grades correct_points
            representations_available=get_kc(KnowledgeComponentId.DEPENDENT_VARS).representations,
            operands=(Rational(a), Rational(x)),
            answer_kind=AnswerKind.COORDINATE,
            correct_points=_format_point(x, dependent),
        )
    statement = f"The rule is y = {a}x. What is y when x = {x}?"
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.DEPENDENT_VARS, seed, surface_format),
        kc=KnowledgeComponentId.DEPENDENT_VARS,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(dependent),
        representations_available=get_kc(KnowledgeComponentId.DEPENDENT_VARS).representations,
        operands=(Rational(a), Rational(x)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 3: classify number sets (TEKS 6.2A) ───

# The values to classify, as (numerator, denominator) pairs spanning every membership case so the
# lesson exercises the full nested-subset structure: positive integers (natural ⊂ whole ⊂ integer
# ⊂ rational), zero (whole ⊂ integer ⊂ rational), negative integers (integer ⊂ rational), and
# non-integer fractions positive and negative (rational only). Difficulty widens the range and
# leans toward the trickier non-positive / non-integer cases at higher tiers (CP.B easy→hard).
_CLASSIFY_VALUES_BY_DIFFICULTY: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((1, 1), (2, 1), (5, 1), (8, 1)),  # friendly positive integers (all four sets)
    2: ((0, 1), (3, 1), (10, 1), (1, 2)),  # zero + a first non-integer fraction
    3: ((-2, 1), (-7, 1), (3, 4), (7, 2)),  # negatives + proper/improper fractions
    4: ((-12, 1), (-1, 5), (9, 4), (-11, 3)),  # larger negatives + negative fractions
}
_CLASSIFY_VALUE_POOL: tuple[tuple[int, int], ...] = (
    (1, 1),
    (4, 1),
    (12, 1),
    (0, 1),
    (-3, 1),
    (-9, 1),
    (1, 2),
    (3, 4),
    (7, 2),
    (-2, 3),
    (-5, 4),
)


def _generate_classify_number_sets(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_classify_number_sets: classify which number sets a value belongs to (TEKS 6.2A).

    Picks a value (seeded) spanning the membership cases, computes its canonical set membership via
    the domain ``classify_sets_for_value`` (the single source of truth, no LLM), and renders the
    canonical comma-separated answer (small→large) into ``correct_sets``. The answer is a SET of
    labels graded by order-insensitive membership; ``correct_value`` is a ``Rational(0)``
    placeholder (never read on the NUMBER_SETS path). The classified value rides in ``operands`` so
    the integer-not-rational misconception (drop ``rational``) is replayable by the verifier.
    """
    pool = (
        _CLASSIFY_VALUES_BY_DIFFICULTY.get(difficulty, _CLASSIFY_VALUE_POOL)
        if difficulty
        else _CLASSIFY_VALUE_POOL
    )
    numerator, denominator = rng.choice(pool)
    value = Rational(numerator, denominator)
    membership = classify_sets_for_value(value)
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.CLASSIFY_NUMBER_SETS, seed, surface_format),
        kc=KnowledgeComponentId.CLASSIFY_NUMBER_SETS,
        surface_format=surface_format,
        statement=f"Which number sets does {value} belong to?",
        correct_value=Rational(0),  # placeholder; the NUMBER_SETS path grades correct_sets
        representations_available=get_kc(KnowledgeComponentId.CLASSIFY_NUMBER_SETS).representations,
        answer_kind=AnswerKind.NUMBER_SETS,
        correct_sets=",".join(membership),
        operands=(value,),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───

# Expression-parts item modes (the operand flag the verifier reads; it never sees the statement):
# 0 = name the COEFFICIENT, 1 = name the CONSTANT, 2 = count the TERMS. Single source of truth.
_MODE_COEFFICIENT = 0
_MODE_CONSTANT = 1
_MODE_TERM_COUNT = 2

# Coefficient / constant pools for "parts of an expression" items by difficulty tier (the easy→hard
# ramp; CP.B). Higher tiers use larger numbers. The two are drawn so coefficient != constant (the
# generator resamples), keeping the coefficient↔constant swap always diagnostic.
_PARTS_NUMBER_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4, 5),
    2: (4, 5, 6, 7, 8),
    3: (6, 7, 8, 9, 10, 12),
    4: (9, 11, 12, 15, 18, 20),
}
_PARTS_NUMBER_POOL: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12)


def _generate_expression_parts(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_expression_parts: name a part of an algebraic expression; a single number is the answer.

    An item-mode flag (sampled by the seeded RNG) varies which part is asked: the COEFFICIENT of
    the variable, the CONSTANT term, or the number of TERMS. The expression is built as
    ``{coefficient}x + {constant}`` (two terms); a term-count item may add a second variable term
    ``+ {k}y`` so the count is 2 or 3. The coefficient and constant are drawn distinct (resampled),
    so the coefficient↔constant swap is always diagnostic. ``operands = (mode, coefficient,
    constant)`` so the verifier can replay the part-confusion misconception without seeing the
    statement. The answer is a single whole number (the part's value), entered in the NUMERIC
    editor; ``difficulty`` widens the coefficient/constant pool.
    """
    pool = (
        _PARTS_NUMBER_BY_DIFFICULTY.get(difficulty, _PARTS_NUMBER_POOL)
        if difficulty
        else _PARTS_NUMBER_POOL
    )
    coefficient = rng.choice(pool)
    constant = rng.choice(pool)
    while constant == coefficient:  # keep the two parts distinct so the swap is diagnostic
        constant = rng.choice(pool)
    mode = rng.choice((_MODE_COEFFICIENT, _MODE_CONSTANT, _MODE_TERM_COUNT))

    if mode == _MODE_TERM_COUNT:
        # Two or three terms: optionally a second variable term so the count varies.
        add_second_variable = rng.random() < 0.5
        second_coefficient = rng.choice(pool)
        if add_second_variable:
            expression = f"{coefficient}x + {constant} + {second_coefficient}y"
            term_count = 3
        else:
            expression = f"{coefficient}x + {constant}"
            term_count = 2
        statement = f"How many terms are in the expression {expression}?"
        answer = term_count
    elif mode == _MODE_COEFFICIENT:
        statement = f"What is the coefficient of x in {coefficient}x + {constant}?"
        answer = coefficient
    else:  # _MODE_CONSTANT
        statement = f"What is the constant term in {coefficient}x + {constant}?"
        answer = constant

    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.EXPRESSION_PARTS, seed, surface_format),
        kc=KnowledgeComponentId.EXPRESSION_PARTS,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(answer),
        representations_available=get_kc(KnowledgeComponentId.EXPRESSION_PARTS).representations,
        operands=(Rational(mode), Rational(coefficient), Rational(constant)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 6: Geometry ───

# Side-length pools for "find the area" items by difficulty tier (the easy→hard ramp; CP.B):
# higher tiers use larger sides. Whole-number sides throughout (a clean grade-6 area), so the
# difficulty ramps the side magnitudes, not a fraction denominator. The TRIANGLE mode halves the
# product, so to keep the area a whole number the generator forces the HEIGHT even on triangles.
_AREA_SIDE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (2, 3, 4, 5),
    2: (5, 6, 7, 8),
    3: (8, 9, 10, 11),
    4: (11, 12, 13, 14, 15),
}
_AREA_SIDE_POOL: tuple[int, ...] = (3, 4, 5, 6, 7, 8, 9, 10, 12, 14)
# Triangle mode = 0 (area 1/2·b·h); parallelogram/rectangle mode = 1 (area b·h).
_AREA_TRIANGLE_MODE = 0
_AREA_PARALLELOGRAM_MODE = 1


def _generate_area_polygons(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_area_polygons: find a polygon's area; a single numeric area answer (6.G.1).

    A shape-mode flag (the seeded RNG picks triangle vs parallelogram/rectangle) decides the item.
    TRIANGLE (mode 0): area is ``1/2 · base · height`` — the HEIGHT is drawn even so the area is a
    whole number. PARALLELOGRAM/RECTANGLE (mode 1): area is ``base · height``. ``operands =
    (base, height, mode)`` so the verifier can replay the forgot-the-half misconception (answer
    ``base · height`` on a triangle). ``difficulty`` widens the side pool.

    Two REAL surfaces share this answer (so the KC is masterable across representations,
    PROJECT.md §3.4 rule 2), mirroring KC_evaluate_expressions / KC_exponents:

      - **SYMBOLIC** (default) — "Find the area of a triangle with base {b} and height {h}." (the
        formula form);
      - **AREA_MODEL** — the same figure read off a unit-square grid: "On a unit grid, a triangle
        has base {b} and height {h}. What is its area in square units?" (the visual form).

    The math is sampled before the format is applied, so the same seed yields identical operands in
    either surface. Base and height are positive, so ``base · height > base · height / 2`` and the
    forgot-the-half misconception is always diagnostic on a triangle.
    """
    pool = (
        _AREA_SIDE_BY_DIFFICULTY.get(difficulty, _AREA_SIDE_POOL) if difficulty else _AREA_SIDE_POOL
    )
    triangle = rng.random() < 0.5
    base = rng.choice(pool)
    height = rng.choice(pool)
    if triangle:
        # Force an even height so 1/2·base·height is a whole-number area (a clean grade-6 answer).
        if height % 2 == 1:
            height += 1
        mode = _AREA_TRIANGLE_MODE
        correct = Rational(base * height, 2)
        shape = "triangle"
    else:
        mode = _AREA_PARALLELOGRAM_MODE
        correct = Rational(base * height)
        shape = "parallelogram"
    if surface_format is Representation.AREA_MODEL:
        statement = (
            f"On a unit grid, a {shape} has base {base} and height {height}. "
            f"What is its area in square units?"
        )
    else:
        statement = f"Find the area of a {shape} with base {base} and height {height}."
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.AREA_POLYGONS, seed, surface_format),
        kc=KnowledgeComponentId.AREA_POLYGONS,
        surface_format=surface_format,
        statement=statement,
        correct_value=correct,
        representations_available=get_kc(KnowledgeComponentId.AREA_POLYGONS).representations,
        operands=(Rational(base), Rational(height), Rational(mode)),
    )


# Edge-length pool for "volume of a prism with fractional edges" items (CCSS 6.G.2). Every entry
# is an exact SymPy Rational (no float); the pool mixes proper/improper fractions with small whole
# numbers so a generated prism has FRACTIONAL edges while staying 6th-grade-sized. Difficulty
# tiers widen toward larger numerators/denominators (the easy->hard ramp; CP.B).
_VOLUME_EDGE_BY_DIFFICULTY: dict[int, tuple[Rational, ...]] = {
    1: (Rational(1, 2), Rational(3, 2), Rational(2), Rational(5, 2), Rational(3)),
    2: (Rational(1, 2), Rational(2, 3), Rational(3, 2), Rational(5, 2), Rational(3), Rational(4)),
    3: (Rational(2, 3), Rational(3, 4), Rational(5, 2), Rational(7, 2), Rational(4), Rational(5)),
    4: (
        Rational(3, 4),
        Rational(5, 4),
        Rational(7, 3),
        Rational(7, 2),
        Rational(9, 2),
        Rational(5),
    ),
}
_VOLUME_EDGE_POOL: tuple[Rational, ...] = (
    Rational(1, 2),
    Rational(2, 3),
    Rational(3, 4),
    Rational(3, 2),
    Rational(5, 2),
    Rational(2),
    Rational(3),
    Rational(4),
)


def _format_edge(edge: Rational) -> str:
    """Render an edge length as a kid-facing string — a whole number, else 'p/q' (no decimals)."""
    return str(edge.p) if edge.q == 1 else f"{edge.p}/{edge.q}"


def _generate_volume_fractional_edges(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_volume_fractional_edges: volume of a right rectangular prism; a single numeric answer.

    Picks three edge lengths (length, width, height) from a fraction-bearing pool via the seeded
    RNG; the answer is the exact product ``l * w * h`` as a SymPy ``Rational`` (V = l*w*h, no
    float). ``operands = (l, w, h)`` so the verifier can replay the add-edges misconception
    (``l + w + h``). At least one edge is resampled until it is genuinely fractional (q != 1), so
    every item exercises the 6.G.2 fractional-edge skill. The sum-equals-product case is resampled,
    the add-edges value is always DISTINCT from the correct volume (the match stays diagnostic).
    Two surfaces share the same numeric answer (the LessonSpec >=2-rep contract):

      - **SYMBOLIC** (default) — "What is the volume of a right rectangular prism with edges …?";
      - **AREA_MODEL** — the same prism described as a stack of unit-cube layers (the concrete
        3D picture of V = l*w*h). PRACTICE-ONLY today: only SYMBOLIC is live.

    ``difficulty`` widens the edge pool. The math is sampled before the surface is applied, so the
    same seed yields identical operands in either surface.
    """
    pool = (
        _VOLUME_EDGE_BY_DIFFICULTY.get(difficulty, _VOLUME_EDGE_POOL)
        if difficulty
        else _VOLUME_EDGE_POOL
    )
    length = rng.choice(pool)
    width = rng.choice(pool)
    height = rng.choice(pool)
    # Require at least one genuinely fractional edge (the 6.G.2 point), and exclude the degenerate
    # case where l + w + h == l * w * h (there the add-edges misconception would be
    # indistinguishable from the correct volume).
    while all(edge.q == 1 for edge in (length, width, height)) or (
        length + width + height == length * width * height
    ):
        length = rng.choice(pool)
        width = rng.choice(pool)
        height = rng.choice(pool)

    volume = length * width * height
    edge_l, edge_w, edge_h = _format_edge(length), _format_edge(width), _format_edge(height)
    if surface_format is Representation.AREA_MODEL:
        statement = (
            f"A right rectangular prism is built from unit-cube layers: it is {edge_l} long, "
            f"{edge_w} wide, and {edge_h} tall. What is its volume?"
        )
    else:
        statement = (
            f"What is the volume of a right rectangular prism with edge lengths {edge_l}, "
            f"{edge_w}, and {edge_h}?"
        )
    return Problem(
        problem_id=_generated_id(
            KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES, seed, surface_format
        ),
        kc=KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES,
        surface_format=surface_format,
        statement=statement,
        correct_value=volume,
        representations_available=get_kc(
            KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES
        ).representations,
        operands=(length, width, height),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 6: Polygons in the coordinate plane (6.G.3) ───


def _generate_polygons_coordinate_plane(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_polygons_coordinate_plane: draw polygons / use coordinates in the plane (CCSS 6.G.3).

    Picks one of two item kinds (seeded), both about an axis-aligned rectangle whose four corners
    are ``(x1,y1),(x2,y1),(x1,y2),(x2,y2)``:

    * ``missing_vertex`` — show three corners, ask for the fourth. The answer is the SINGLE missing
      corner (a one-element point set).
    * ``name_vertices`` — describe the rectangle by its x- and y-extents, ask for all four corners.
      The answer is the four-vertex polygon.

    The answer kind is COORDINATE — graded by the SAME verifier path as KC_coordinate_plane
    (ORDER-INSENSITIVE set equality on ``correct_points``), never a magnitude; ``correct_value`` is
    a ``Rational(0)`` placeholder (never read on the COORDINATE path). ``operands`` is empty; the
    coordinate-swap misconception is replayed from ``correct_points`` by the verifier, not operands.
    """
    bound = (
        _COORDINATE_RANGE_BY_DIFFICULTY.get(difficulty, _COORDINATE_RANGE_DEFAULT)
        if difficulty
        else _COORDINATE_RANGE_DEFAULT
    )
    # An axis-aligned rectangle: two distinct x's and two distinct y's, with a real positive width
    # and height so the four corners are always four distinct points.
    x1 = rng.randint(-bound, bound)
    x2 = x1 + rng.randint(1, max(1, bound))  # strictly to the right
    y1 = rng.randint(-bound, bound)
    y2 = y1 + rng.randint(1, max(1, bound))  # strictly above
    corners = ((x1, y1), (x2, y1), (x1, y2), (x2, y2))

    if rng.choice(("missing_vertex", "name_vertices")) == "missing_vertex":
        missing_index = rng.randrange(len(corners))
        missing = corners[missing_index]
        shown = tuple(c for i, c in enumerate(corners) if i != missing_index)
        shown_text = "; ".join(f"({cx}, {cy})" for cx, cy in shown)
        statement = (
            f"Three corners of a rectangle are {shown_text}. Give the fourth corner so the four "
            "points form a rectangle with sides parallel to the axes."
        )
        points: tuple[tuple[int, int], ...] = (missing,)
    else:
        statement = (
            f"Plot the four corners of the rectangle whose left and right sides are at x = {x1} "
            f"and x = {x2}, and whose bottom and top sides are at y = {y1} and y = {y2}."
        )
        points = corners

    return Problem(
        problem_id=_generated_id(
            KnowledgeComponentId.POLYGONS_COORDINATE_PLANE, seed, surface_format
        ),
        kc=KnowledgeComponentId.POLYGONS_COORDINATE_PLANE,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(0),  # placeholder; the COORDINATE path grades correct_points
        representations_available=get_kc(
            KnowledgeComponentId.POLYGONS_COORDINATE_PLANE
        ).representations,
        answer_kind=AnswerKind.COORDINATE,
        correct_points=_format_points(points),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 6: Surface area of a prism from its net (6.G.4) ───

# Edge-length pool for "surface area of a prism from its net" items (CCSS 6.G.4). Whole-number
# edges keep every face area a whole number (the 6.G.4 net scope); the pool stays 6th-grade-sized.
# Difficulty tiers widen toward larger edges (the easy->hard ramp; CP.B). A cube (all edges equal)
# occurs naturally when the three independent draws coincide.
_SURFACE_AREA_EDGE_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (1, 2, 3, 4),
    2: (2, 3, 4, 5),
    3: (3, 4, 5, 6, 7),
    4: (5, 6, 7, 8, 9, 10),
}
_SURFACE_AREA_EDGE_POOL: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8)


def _generate_surface_area_nets(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_surface_area_nets: surface area of a right rectangular prism (or cube); numeric answer.

    Picks three whole-number edge lengths (length, width, height) via the seeded RNG; the answer is
    the sum of the six face areas, ``SA = 2*(l*w + l*h + w*h)`` (a 2x3x4 prism -> 52). Whole-number
    edges keep every face area a whole number (the 6.G.4 net scope). ``operands = (l, w, h)`` so the
    verifier can replay the count-three-faces misconception (``l*w + l*h + w*h`` — half the answer).
    A cube (all edges equal) arises naturally when the draws coincide. Two surfaces share the same
    numeric answer (the LessonSpec >=2-rep contract):

      - **SYMBOLIC** (default) — "What is the surface area of a right rectangular prism with edge
        lengths …?";
      - **AREA_MODEL** — the same prism described as a net of six rectangular faces (the concrete
        unfolded picture). PRACTICE-ONLY today: only SYMBOLIC is live.

    ``difficulty`` widens the edge pool. The math is sampled before the surface is applied, so the
    same seed yields identical operands in either surface.
    """
    pool = (
        _SURFACE_AREA_EDGE_BY_DIFFICULTY.get(difficulty, _SURFACE_AREA_EDGE_POOL)
        if difficulty
        else _SURFACE_AREA_EDGE_POOL
    )
    length = rng.choice(pool)
    width = rng.choice(pool)
    height = rng.choice(pool)
    surface_area = 2 * (length * width + length * height + width * height)
    if surface_format is Representation.AREA_MODEL:
        statement = (
            f"A right rectangular prism unfolds into a net of six rectangles; it is {length} long, "
            f"{width} wide, and {height} tall. What is its total surface area?"
        )
    else:
        statement = (
            f"What is the surface area of a right rectangular prism with edge lengths {length}, "
            f"{width}, and {height}?"
        )
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.SURFACE_AREA_NETS, seed, surface_format),
        kc=KnowledgeComponentId.SURFACE_AREA_NETS,
        surface_format=surface_format,
        statement=statement,
        correct_value=Rational(surface_area),
        representations_available=get_kc(KnowledgeComponentId.SURFACE_AREA_NETS).representations,
        operands=(Rational(length), Rational(width), Rational(height)),
    )


# ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics (MAD, 6.SP.5c) ───

# Curated DEVIATION patterns for a MAD item, keyed by data-set length (4–6). Each tuple is the set
# of (integer) deviations from the data's mean: it SUMS TO ZERO — so the mean of (mean + d_i) is
# exactly the chosen base mean, an integer — and its ABSOLUTE values sum to a multiple of the
# length, so MAD = (sum of |d_i|) / n is a clean whole number. Spread is always positive (no all-
# zero pattern), so the true MAD > 0 and the forgot-absolute-value error (signed mean = 0) is
# always distinct from it. The data values themselves are (mean + d_i), kept positive by the mean
# base below. Difficulty widens the pattern pool (larger spreads ⇒ larger MAD) within each length.
_MAD_DEVIATION_PATTERNS: dict[int, tuple[tuple[int, ...], ...]] = {
    4: (
        (-1, -1, 1, 1),  # |.|sum 4, MAD 1
        (-3, -1, 1, 3),  # |.|sum 8, MAD 2
        (-2, -2, 2, 2),  # |.|sum 8, MAD 2
        (-4, 0, 0, 4),  # |.|sum 8, MAD 2
        (-5, -3, 3, 5),  # |.|sum 16, MAD 4
    ),
    5: (
        (-2, -2, -1, 2, 3),  # |.|sum 10, MAD 2
        (-4, -1, 0, 2, 3),  # |.|sum 10, MAD 2
        (-3, -1, -1, 2, 3),  # |.|sum 10, MAD 2
        (-5, -5, 0, 5, 5),  # |.|sum 20, MAD 4
    ),
    6: (
        (-1, -1, -1, 1, 1, 1),  # |.|sum 6, MAD 1
        (-3, -2, -1, 1, 2, 3),  # |.|sum 12, MAD 2
        (-2, -2, -2, 2, 2, 2),  # |.|sum 12, MAD 2
        (-5, -4, -3, 3, 4, 5),  # |.|sum 24, MAD 4
    ),
}
# The mean (an integer) the deviations are centered on, by difficulty tier. Chosen large enough
# that mean + min(deviation) stays positive for every pattern above (min deviation is -5), so the
# data set reads as plausible whole-number measurements.
_MAD_MEAN_BY_DIFFICULTY: dict[int, tuple[int, ...]] = {
    1: (8, 10, 12),
    2: (10, 12, 15),
    3: (12, 15, 18, 20),
    4: (15, 18, 20, 25),
}
_MAD_MEAN_POOL: tuple[int, ...] = (8, 10, 12, 15, 18, 20)


def _generate_mean_absolute_deviation(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_mean_absolute_deviation: the MAD of a small data set; a single Rational answer (6.SP.5c).

    Builds a VARIABLE-LENGTH data set (4–6 whole numbers) by centering a curated, zero-sum deviation
    pattern on an integer mean (so the mean is exactly that integer and the MAD is a clean whole
    number). The answer is the MAD — the mean of the absolute deviations from the data's mean
    (``{2,4,6,8}`` -> mean 5, ``|deviations|`` 3,1,1,3, MAD 2). ``operands`` is the data set itself
    (the full variable-length tuple), so the verifier can replay the forgot-absolute-value
    misconception (averaging the SIGNED deviations -> always 0). The data values are listed in the
    prompt text and entered as a single number in the existing editor (NO new widget).
    ``difficulty`` widens the mean and the spread of the chosen pattern; spread is always positive,
    so MAD > 0.
    """
    length = rng.choice((4, 5, 6))
    patterns = _MAD_DEVIATION_PATTERNS[length]
    pattern = rng.choice(patterns)
    mean_pool = (
        _MAD_MEAN_BY_DIFFICULTY.get(difficulty, _MAD_MEAN_POOL) if difficulty else _MAD_MEAN_POOL
    )
    mean = rng.choice(mean_pool)
    values = [mean + d for d in pattern]
    rng.shuffle(values)
    data = tuple(Rational(v) for v in values)
    mad = sum((abs(Rational(d)) for d in pattern), Rational(0)) / length
    listed = ", ".join(str(v) for v in values)
    statement = f"What is the mean absolute deviation (MAD) of the data set {listed}?"
    return Problem(
        problem_id=_generated_id(
            KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION, seed, surface_format
        ),
        kc=KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION,
        surface_format=surface_format,
        statement=statement,
        correct_value=mad,
        representations_available=get_kc(
            KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION
        ).representations,
        operands=data,
    )


# ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics (6.SP) ───

# The data-set size by difficulty tier for center/spread items. Larger sets at higher tiers make
# the median/IQR split less obvious; always >= 4 so the lower/upper halves are each non-empty for
# the IQR. The data VALUES are drawn from a small whole-number pool that widens with difficulty.
_CENTER_SPREAD_SIZE_BY_DIFFICULTY: dict[int, int] = {1: 4, 2: 5, 3: 6, 4: 7}
_CENTER_SPREAD_VALUE_BY_DIFFICULTY: dict[int, int] = {1: 9, 2: 12, 3: 15, 4: 20}
_CENTER_SPREAD_DEFAULT_SIZE = 5
_CENTER_SPREAD_DEFAULT_MAX_VALUE = 12
# The three measure modes, cycled by the seed so a lesson covers center AND both spread measures.
_CENTER_SPREAD_MODES: tuple[int, ...] = (CENTER_MEDIAN, SPREAD_RANGE, SPREAD_IQR)


def _generate_center_spread(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_center_spread_shape: a measure of center or spread for a small data set; numeric answer.

    Picks a measure MODE (median-center, range, or IQR) and a sorted whole-number data set via the
    seeded RNG, then computes the exact measure with SymPy (see ``app.domain.center_spread``). The
    data is sampled WITHOUT a zero so the range's max + min misconception (max + min vs max − min)
    always differs from the correct value, and the extremes are kept distinct (max > min) for the
    same reason.

    Variable-length operand encoding (the data-set wrinkle): ``operands`` is
    ``(mode_flag, *sorted_data)`` — a leading ``Rational`` sentinel (0=median, 1=range, 2=IQR)
    followed by the sorted data values. This keeps both the mode AND the data inside the single
    ``operands`` field the verifier's wrong-answer predictor receives, so the range-as-sum model can
    recompute from it without any new Problem field. The verifier matches this KC's model with
    ``operand_count=None`` (any length).

    ``difficulty`` widens the data-set size and value pool. SYMBOLIC-only is live (PRACTICE-ONLY);
    the math is sampled before the surface is applied, so the same seed is identical across formats.
    """
    size = (
        _CENTER_SPREAD_SIZE_BY_DIFFICULTY.get(difficulty, _CENTER_SPREAD_DEFAULT_SIZE)
        if difficulty
        else _CENTER_SPREAD_DEFAULT_SIZE
    )
    max_value = (
        _CENTER_SPREAD_VALUE_BY_DIFFICULTY.get(difficulty, _CENTER_SPREAD_DEFAULT_MAX_VALUE)
        if difficulty
        else _CENTER_SPREAD_DEFAULT_MAX_VALUE
    )
    mode = _CENTER_SPREAD_MODES[seed % len(_CENTER_SPREAD_MODES)]
    # Sample distinct nonzero values (1..max_value) so the extremes differ and no zero hides the
    # max + min vs max − min distinction; then sort (the median/IQR rules assume sorted data).
    raw = rng.sample(range(1, max_value + 1), size)
    data = tuple(Rational(v) for v in sorted(raw))
    if mode == CENTER_MEDIAN:
        correct = median(data)
        statement = f"What is the median of the data set {', '.join(str(v) for v in raw)}?"
    elif mode == SPREAD_RANGE:
        correct = range_spread(data)
        statement = f"What is the range of the data set {', '.join(str(v) for v in raw)}?"
    else:
        correct = iqr(data)
        statement = (
            f"What is the interquartile range (IQR) of the data set "
            f"{', '.join(str(v) for v in raw)}?"
        )
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.CENTER_SPREAD_SHAPE, seed, surface_format),
        kc=KnowledgeComponentId.CENTER_SPREAD_SHAPE,
        surface_format=surface_format,
        statement=statement,
        correct_value=correct,
        representations_available=get_kc(KnowledgeComponentId.CENTER_SPREAD_SHAPE).representations,
        operands=(Rational(mode), *data),
    )


# Curated question banks for KC_statistical_questions (CCSS 6.SP.1). A STATISTICAL question
# anticipates VARIABILITY — its answer varies across the population/repeated measures (→ YES). A
# NON-statistical question has a single fixed answer (→ NO). Hand-authored so the truth is curated,
# not computed (there is no math to derive "is this statistical?" from — the variability lives in
# the question's MEANING). Kept kid-friendly per the bank language rule (CLAUDE.md §8.5).
_STATISTICAL_QUESTION_TEMPLATES: tuple[str, ...] = (
    "How tall are the students in my class?",
    "How many pets do the families on my street have?",
    "What are the ages of the people at the park today?",
    "How long do sixth graders spend on homework each night?",
    "How many books did each student in the class read this month?",
    "What are the shoe sizes of the players on the team?",
    "How far do students travel to get to school?",
    "How many minutes do people wait in the lunch line?",
)
_NON_STATISTICAL_QUESTION_TEMPLATES: tuple[str, ...] = (
    "How tall is our teacher?",
    "How many days are in this month?",
    "What is my age today?",
    "How many wheels does my bike have?",
    "What is the height of the flagpole at school?",
    "How many students are in the class right now?",
    "What time does school start today?",
    "How many legs does a spider have?",
)


def _generate_statistical_questions(
    rng: random.Random, seed: int, surface_format: Representation, difficulty: int | None = None
) -> Problem:
    """KC_statistical_questions (CCSS 6.SP.1): is this a STATISTICAL question? — a YES/NO judgment.

    REUSES the existing YES_NO answer kind (NO new widget). The generator alternates by seed
    parity between the curated statistical bank (anticipates variability → answer YES) and the
    non-statistical bank (a single fixed value → answer NO), so both verdicts are produced across
    seeds. The truth is encoded in ``operands`` as the SAME equality the EQUIVALENCE YES_NO items
    use: ``(1, 1)`` (equal → YES) for a statistical question, ``(1, 0)`` (not equal → NO) for a
    non-statistical one — so ``_verify_yes_no`` grades it by SymPy equality with NO new verifier
    path (SymPy decides the math; CLAUDE.md §8.2). ``correct_value`` is the operand anchor (1),
    matching how the EQUIVALENCE YES_NO generator anchors its yes/no items.

    The question text IS a word problem, so the SYMBOLIC and WORD_PROBLEM surfaces render the same
    judgment; ``difficulty`` does not vary the item (there is no magnitude to ramp). Deterministic
    per seed (PROJECT.md §4.1): the bank choice is seeded by ``rng``.
    """
    statistical = seed % 2 == 0
    if statistical:
        statement = rng.choice(_STATISTICAL_QUESTION_TEMPLATES)
        operands = (Rational(1), Rational(1))  # equal ⇒ YES (a statistical question)
    else:
        statement = rng.choice(_NON_STATISTICAL_QUESTION_TEMPLATES)
        operands = (Rational(1), Rational(0))  # not equal ⇒ NO (not a statistical question)
    return Problem(
        problem_id=_generated_id(KnowledgeComponentId.STATISTICAL_QUESTIONS, seed, surface_format),
        kc=KnowledgeComponentId.STATISTICAL_QUESTIONS,
        surface_format=surface_format,
        statement=statement,
        correct_value=operands[0],  # anchor; the yes/no truth is operands[0] == operands[1]
        representations_available=get_kc(
            KnowledgeComponentId.STATISTICAL_QUESTIONS
        ).representations,
        operands=operands,
        answer_kind=AnswerKind.YES_NO,
    )


# The flat KC -> generator registry. A KC without a generator would fail the "a generator exists
# for every live KC" contract (test_generators), so this grows with LIVE_KCS.
GENERATORS: dict[KnowledgeComponentId, _KcGenerator] = {
    KnowledgeComponentId.EQUIVALENCE: _generate_equivalence,
    KnowledgeComponentId.COMMON_DENOMINATOR: _generate_common_denominator,
    KnowledgeComponentId.ADDITION_UNLIKE: _generate_addition,
    KnowledgeComponentId.SUBTRACTION_UNLIKE: _generate_subtraction,
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT: _generate_number_line,
    KnowledgeComponentId.RATIO_LANGUAGE: _generate_ratio_language,
    KnowledgeComponentId.UNIT_RATE: _generate_unit_rate,
    KnowledgeComponentId.EQUIVALENT_RATIOS: _generate_equivalent_ratios,
    KnowledgeComponentId.PERCENT: _generate_percent,
    KnowledgeComponentId.MULTIPLY_FRACTIONS: _generate_multiply_fractions,
    KnowledgeComponentId.DIVIDE_FRACTIONS: _generate_divide_fractions,
    KnowledgeComponentId.UNIT_CONVERSION: _generate_unit_conversion,
    KnowledgeComponentId.GCF_LCM: _generate_gcf_lcm,
    KnowledgeComponentId.MULTI_DIGIT_DIVISION: _generate_multi_digit_division,
    KnowledgeComponentId.DECIMAL_OPERATIONS: _generate_decimal_operations,
    KnowledgeComponentId.ABSOLUTE_VALUE: _generate_absolute_value,
    KnowledgeComponentId.INTEGER_ADD_SUBTRACT: _generate_integer_add_subtract,
    KnowledgeComponentId.SIGNED_NUMBERS: _generate_signed_numbers,
    KnowledgeComponentId.WRITE_EXPRESSIONS: _generate_write_expressions,
    KnowledgeComponentId.EVALUATE_EXPRESSIONS: _generate_evaluate_expressions,
    KnowledgeComponentId.EXPONENTS: _generate_exponents,
    KnowledgeComponentId.ONE_STEP_EQUATIONS: _generate_one_step_equations,
    KnowledgeComponentId.EQUIVALENT_EXPRESSIONS: _generate_equivalent_expressions,
    KnowledgeComponentId.INEQUALITIES: _generate_inequalities,
    KnowledgeComponentId.COORDINATE_PLANE: _generate_coordinate_plane,
    KnowledgeComponentId.CLASSIFY_NUMBER_SETS: _generate_classify_number_sets,
    KnowledgeComponentId.EXPRESSION_PARTS: _generate_expression_parts,
    KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE: _generate_integer_multiply_divide,
    KnowledgeComponentId.TRIANGLE_PROPERTIES: _generate_triangle_properties,
    KnowledgeComponentId.AREA_POLYGONS: _generate_area_polygons,
    KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES: _generate_volume_fractional_edges,
    KnowledgeComponentId.POLYGONS_COORDINATE_PLANE: _generate_polygons_coordinate_plane,
    KnowledgeComponentId.SURFACE_AREA_NETS: _generate_surface_area_nets,
    KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION: _generate_mean_absolute_deviation,
    KnowledgeComponentId.CENTER_SPREAD_SHAPE: _generate_center_spread,
    KnowledgeComponentId.SUMMARY_STATISTICS: _generate_summary_statistics,
    KnowledgeComponentId.DATA_DISPLAYS: _generate_data_displays,
    KnowledgeComponentId.CATEGORICAL_DATA: _generate_categorical_data,
    KnowledgeComponentId.STATISTICAL_QUESTIONS: _generate_statistical_questions,
    KnowledgeComponentId.DEPENDENT_VARS: _generate_dependent_vars,
}


def generate_problem(
    kc: KnowledgeComponentId,
    seed: int,
    surface_format: Representation | None = None,
    difficulty: int | None = None,
) -> Problem:
    """Generate one in-scope ``Problem`` for ``kc``, deterministically from ``seed``.

    Surface format is a PARAMETER (decision 0.D.1): if given, the problem is rendered
    in that representation (so the harness can interleave the same KC across formats
    to test multi-representation mastery and defeat Surface Sam); if omitted, the
    KC's default (first registered) representation is used. Requesting a format the
    KC does not support raises ``ValueError`` (CLAUDE.md §8.5 — fail loudly).

    ``difficulty`` is the CP.B easy→hard ramp tier (1=friendliest … 4=hardest; see
    ``_DENOM_BY_DIFFICULTY``). It narrows the denominator pool so a lesson that walks the
    tiers ramps from small to large bottoms. ``None`` keeps the full-set default — so the
    persona harness, the transfer probe, and any caller that doesn't ramp are byte-for-byte
    unchanged (PROJECT.md §4.1 reproducibility).

    Determinism: the seed alone (with the difficulty tier) fixes the operands and the correct
    answer, so the SAME (seed, difficulty) yields an identical ``Problem`` every call. The
    format does not perturb the RNG draw (the math is sampled before the format is applied),
    so the same seed in two different formats yields the same underlying operands.
    """
    chosen_format = surface_format if surface_format is not None else _default_format(kc)
    _require_supported_format(kc, chosen_format)

    # A fresh, seed-only RNG per call: no shared/global state, so two calls with the
    # same seed are independent yet identical (CLAUDE.md §8.1 — pure & deterministic).
    rng = random.Random(seed)

    generator = GENERATORS[kc]
    return generator(rng, seed, chosen_format, difficulty)


# ─── The diagnostic-gem bank adapter (decision 0.D.1: one shared type) ───────


def _parse_fractions(text: str) -> tuple[Rational, ...]:
    """Pull every ``a/b`` fraction out of a bank statement, in order, as Rationals.

    Bank statements are kid-friendly prose with embedded slash-fractions (e.g.
    "1/2 + 1/4 = ?"). We extract them left-to-right so the operands tuple matches
    the order the learner reads — the same order the misconception generators in
    ``misconceptions.py`` expect.
    """
    return tuple(Rational(int(n), int(d)) for n, d in re.findall(r"(\d+)\s*/\s*(\d+)", text))


def _parse_sympy_check_fractions(check: str) -> tuple[Rational, ...]:
    """Pull ``Rational(n, d)`` fractions out of a bank item's ``sympy_check`` string.

    Used only as a fallback for the rare item whose statement phrases quantities in
    words (e.g. EQ-005). The ``sympy_check`` expression always names the fractions
    explicitly, so it is a reliable last-resort anchor for ``correct_value``.
    """
    return tuple(
        Rational(int(n), int(d))
        for n, d in re.findall(r"Rational\(\s*(\d+)\s*,\s*(\d+)\s*\)", check)
    )


def _bank_correct_value(item: dict[str, Any]) -> Rational:
    """Derive a single ``Rational`` correct value from a bank item's answer.

    The bank stores SymPy-verified answers in several shapes (RESEARCH.md §6); we
    map each onto one canonical magnitude so a downstream verifier compares against
    the same oracle whether the problem is generated or handpicked:

      - ``fraction`` / ``point_on_unit_interval``: the value is an ``a/b`` string.
      - ``integer``: a whole-number answer (e.g. a common-denominator piece-size, or
        an equivalence fill-the-blank top) — wrapped as a ``Rational``.
      - ``yes_no`` / ``choice`` / ``structured`` / ``ordered_points``: there is no
        single magnitude answer (it is a judgment, a chosen option, or several
        points), so we recover the problem's *primary* fraction from the statement —
        the magnitude the item is fundamentally about — keeping ``correct_value``
        typed and non-null for every item without overstating what the item asks.

    This deliberately does NOT try to encode the full structured answer; that richer
    shape belongs to the verifier (Slice 1.4). Here we only need the one shared
    ``Problem`` field populated with a SymPy-typed value.
    """
    answer = item["correct_answer"]
    answer_type = answer["type"]

    if answer_type in ("fraction", "point_on_unit_interval"):
        numerator, denominator = str(answer["value"]).split("/")
        return Rational(int(numerator), int(denominator))
    if answer_type == "integer":
        return Rational(int(answer["value"]))
    if answer_type == "choice":
        # The chosen key is itself a fraction string (e.g. "2/6").
        numerator, denominator = str(answer["value"]).split("/")
        return Rational(int(numerator), int(denominator))

    # yes_no / structured / ordered_points: fall back to the first fraction the
    # item is about. Prefer the learner-facing statement; a few items phrase the
    # quantities entirely in words (e.g. EQ-005 "8 equal pieces ... half"), so we
    # then read the SymPy-verified ``sympy_check`` oracle, which always names the
    # fractions explicitly (e.g. "Rational(4,8) == Rational(1,2)").
    fractions = _parse_fractions(item["problem_statement"]["symbolic"])
    if not fractions:
        fractions = _parse_sympy_check_fractions(str(item["correct_answer"]["sympy_check"]))
    if not fractions:
        raise ValueError(f"bank item {item['id']} has no fraction to anchor correct_value")
    return fractions[0]


def problem_from_bank_item(item: dict[str, Any]) -> Problem:
    """Adapt one ``diagnostic_gems.json`` item into the shared ``Problem`` type.

    This is the second half of the hybrid strategy (decision 0.D.1): a handpicked,
    research-cited bank item becomes the SAME ``Problem`` a procedural generator
    emits, so the mastery model and persona harness are source-agnostic. Operands
    are parsed from the statement when a clean pair is present (arithmetic items);
    items without two operand fractions (e.g. a single placement, a multi-point
    ordering, or a relational judgment) carry ``None`` operands.
    """
    statement = item["problem_statement"]["symbolic"]
    operands = _parse_fractions(statement)
    return Problem(
        problem_id=item["id"],
        kc=KnowledgeComponentId(item["kc_primary"]),
        surface_format=Representation(item["format"]),
        statement=statement,
        correct_value=_bank_correct_value(item),
        representations_available=tuple(
            Representation(r) for r in item["problem_statement"]["representations_available"]
        ),
        # Only expose operands for the canonical two-fraction arithmetic shape; a
        # single fraction or 3+ fractions does not form an operand PAIR the
        # misconception generators expect, so we leave it None there.
        operands=operands if len(operands) == 2 else None,
    )
