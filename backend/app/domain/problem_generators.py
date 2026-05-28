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

from sympy import Rational, ilcm

from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc

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


# A generator takes a seeded RNG, the seed (for the stable id), and the chosen
# surface format, and returns a Problem. Keeping the signature uniform lets
# ``GENERATORS`` be a flat KC -> generator map.
_KcGenerator = Callable[[random.Random, int, Representation], Problem]


# ─── Scope-safe building blocks (PROJECT.md §3.1: positive proper fractions) ──
#
# Every generated operand is a positive proper fraction (0 < n/d < 1) with a
# denominator > 1. We sample from a small curriculum-appropriate denominator set
# (2..12, the sizes the gem bank uses) and a numerator strictly between 0 and the
# denominator, so the fraction is positive and not a whole number — exactly the
# §3.1 scope. Sampling through the seeded RNG is what makes a seed reproducible.

_DENOMINATORS: tuple[int, ...] = (2, 3, 4, 5, 6, 8, 10, 12)


def _proper_fraction(rng: random.Random) -> Rational:
    """Sample one positive proper fraction 0 < n/d < 1 with d > 1 (in-scope)."""
    denominator = rng.choice(_DENOMINATORS)
    numerator = rng.randint(1, denominator - 1)  # 1..d-1 keeps it strictly in (0, 1)
    return Rational(numerator, denominator)


def _unlike_pair(rng: random.Random) -> tuple[Rational, Rational]:
    """Sample two positive proper fractions with UNLIKE denominators.

    The add/subtract KCs are "with unlike denominators" (PROJECT.md §3.1), so the
    two pieces must be different sizes — otherwise the common-denominator step the
    KC is named for is never exercised. We resample the second fraction until its
    denominator differs; the loop is bounded in practice because the denominator
    set has eight members.
    """
    first = _proper_fraction(rng)
    second = _proper_fraction(rng)
    while second.q == first.q:
        second = _proper_fraction(rng)
    return first, second


def _unlike_pair_sum_below_one(rng: random.Random) -> tuple[Rational, Rational]:
    """An unlike-denominator pair whose SUM is < 1, for number-line addition.

    The number-line surface spans 0–1, so an addition answered by placing the total must
    have a total in that interval. We resample until the sum fits (bounded), falling back to
    a known-good in-scope pair (1/4 + 1/3 = 7/12) so the generator is always deterministic
    and never loops forever (CLAUDE.md §8.5)."""
    for _ in range(50):
        first, second = _unlike_pair(rng)
        if first + second < 1:
            return first, second
    return Rational(1, 4), Rational(1, 3)


def _ordered_unlike_pair(rng: random.Random) -> tuple[Rational, Rational]:
    """An unlike-denominator pair ordered larger-first, for well-formed subtraction.

    Subtraction stays in scope (positive result) only if the minuend exceeds the
    subtrahend, so we sample an unlike pair and return it largest-first.
    """
    first, second = _unlike_pair(rng)
    if first > second:
        return first, second
    if second > first:
        return second, first
    # Equal magnitude with unlike denominators (e.g. 1/2 vs 2/4 cannot occur since
    # denominators differ, but guard anyway): resample to guarantee a strict order.
    return _ordered_unlike_pair(rng)


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


def _generate_equivalence(rng: random.Random, seed: int, surface_format: Representation) -> Problem:
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
        base = _proper_fraction(rng)  # the a/b the story is compared against
        if rng.random() < 0.5:  # the story amount is an equal rename (answer YES)
            scale = rng.randint(2, 4)
            taken, pieces, other = base.p * scale, base.q * scale, base
        else:  # a genuinely different amount (answer NO)
            other = _proper_fraction(rng)
            while other == base:
                other = _proper_fraction(rng)
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

    base = _proper_fraction(rng)
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
    rng: random.Random, seed: int, surface_format: Representation
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
    first, second = _unlike_pair(rng)
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


def _generate_addition(rng: random.Random, seed: int, surface_format: Representation) -> Problem:
    """KC_addition_unlike: add two positive proper fractions with unlike bottoms.

    The correct value is the SymPy sum (ADD items, e.g. 1/2 + 1/4 = 3/4). A sum of
    two positive fractions is strictly larger than either addend — the property the
    area model / number line use to expose the add-across error.

    Two REAL representations (so the mastery model's rule 2 can be met live): the default
    SYMBOLIC "a/b + c/d = ?" answered in the fraction editor, and a NUMBER_LINE form where
    the learner places the TOTAL on the 0–1 line (operands sampled so the sum fits 0–1).
    """
    if surface_format is Representation.NUMBER_LINE:
        first, second = _unlike_pair_sum_below_one(rng)
        total = first + second
        statement = (
            f"Add {first.p}/{first.q} + {second.p}/{second.q}, then drag the marker to where "
            f"the total sits on the line from 0 to 1."
        )
    else:
        first, second = _unlike_pair(rng)
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


def _generate_subtraction(rng: random.Random, seed: int, surface_format: Representation) -> Problem:
    """KC_subtraction_unlike: subtract, larger minus smaller, unlike bottoms.

    Ordered larger-first so the difference is positive (in-scope). The correct value
    is the SymPy difference (SUB items, e.g. 1/2 - 1/4 = 1/4).

    Two REAL representations (rule 2): SYMBOLIC "a/b - c/d = ?" in the fraction editor, and a
    NUMBER_LINE form placing the result on 0–1 (a proper-fraction difference is always in
    that interval).
    """
    minuend, subtrahend = _ordered_unlike_pair(rng)
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


def _generate_number_line(rng: random.Random, seed: int, surface_format: Representation) -> Problem:
    """KC_number_line_placement in two REAL representations (so mastery rule 2 is reachable):

    - **NUMBER_LINE** (default): place one proper fraction on the 0–1 line — "drag the marker
      to where 3/4 belongs" (the bank's NL placement shape). correct_value = the fraction.
    - **SYMBOLIC**: a magnitude COMPARISON — "is a/b greater than c/d?" — the same
      reason-about-magnitude-not-digits skill, without the line. Answered yes/no; truth is
      SymPy a > b. A genuinely different surface from the drag, so a learner correct in both
      has shown the magnitude skill two ways (rule 2).
    """
    if surface_format is Representation.SYMBOLIC:
        first, second = _unlike_pair(rng)
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

    target = _proper_fraction(rng)
    statement = f"Drag the marker to where {target.p}/{target.q} belongs on the line from 0 to 1."
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


# The flat KC -> generator registry. Exactly the five KCs (PROJECT.md §3.1); a KC
# without a generator would fail the "a generator exists for every KC" contract.
GENERATORS: dict[KnowledgeComponentId, _KcGenerator] = {
    KnowledgeComponentId.EQUIVALENCE: _generate_equivalence,
    KnowledgeComponentId.COMMON_DENOMINATOR: _generate_common_denominator,
    KnowledgeComponentId.ADDITION_UNLIKE: _generate_addition,
    KnowledgeComponentId.SUBTRACTION_UNLIKE: _generate_subtraction,
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT: _generate_number_line,
}


def generate_problem(
    kc: KnowledgeComponentId,
    seed: int,
    surface_format: Representation | None = None,
) -> Problem:
    """Generate one in-scope ``Problem`` for ``kc``, deterministically from ``seed``.

    Surface format is a PARAMETER (decision 0.D.1): if given, the problem is rendered
    in that representation (so the harness can interleave the same KC across formats
    to test multi-representation mastery and defeat Surface Sam); if omitted, the
    KC's default (first registered) representation is used. Requesting a format the
    KC does not support raises ``ValueError`` (CLAUDE.md §8.5 — fail loudly).

    Determinism: the seed alone fixes the operands and the correct answer, so the
    SAME seed yields an identical ``Problem`` every call (PROJECT.md §4.1
    reproducibility). The format does not perturb the RNG draw (the math is sampled
    before the format is applied), so the same seed in two different formats yields
    the same underlying operands and answer — only the presentation differs.
    """
    chosen_format = surface_format if surface_format is not None else _default_format(kc)
    _require_supported_format(kc, chosen_format)

    # A fresh, seed-only RNG per call: no shared/global state, so two calls with the
    # same seed are independent yet identical (CLAUDE.md §8.1 — pure & deterministic).
    rng = random.Random(seed)

    generator = GENERATORS[kc]
    return generator(rng, seed, chosen_format)


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
