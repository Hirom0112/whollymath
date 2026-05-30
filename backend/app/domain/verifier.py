"""Layer-1 SymPy answer verifier (Slice 1.4).

This is Slice 1.4 of the domain model (ARCHITECTURE.md §5 Layer 1; PROJECT.md
§3.10). It is the ONE thing in the system that decides "is this answer correct?"
— and it decides it with SymPy, never with an LLM and never with a heuristic
(CLAUDE.md §8.2, ARCHITECTURE.md §9, §14 invariant 2: "The LLM never decides math
correctness. SymPy does. Always."). SymPy lives only in ``domain/`` (CLAUDE.md §7,
ARCHITECTURE.md §14 invariant 5), which is exactly where this verifier sits.

It builds directly on the earlier Layer-1 slices: it judges a ``Problem`` (Slice
1.3) against its SymPy-computed ``correct_value``, and when an answer is wrong it
CLASSIFIES the error by replaying the misconception generators (Slice 1.2) on the
problem's operands. The classification feeds the §3.6 adaptation policy, which
routes on the *kind* of error:

  - a MAGNITUDE error (the learner misjudged how big the fraction is) -> S2, the
    number line, the representation that exposes magnitude;
  - an OPERATION/FORMAT error (the learner ran the wrong procedure) -> S3, the
    fraction bars, where part-manipulation makes the operation visible.

(PROJECT.md §3.6 transition table; ARCHITECTURE.md §7.)

The error categories are a canonical domain enum, ``ErrorCategory``, whose string
VALUES are deliberately identical to the api ``ErrorType`` placeholder
(``app/api/schemas.py``: none/magnitude/operation/format/other). This module is the
source of truth; the API imports the domain enum later without a value change, so
the policy that routes on the error string stays aligned across the boundary
(ARCHITECTURE.md §4 — one registry).

Scope (Slice 1.4): NUMERIC (``Rational``) answers — what all five procedural
generators produce. yes/no judgments and multi-point ordering (the adapted bank
items whose ``correct_value`` is only a magnitude anchor) are a DEFERRED extension:
the committed ``Problem`` type carries no structured answer to verify them against,
and this slice does NOT modify that type. See ``verify`` for the documented
deferral. There is NO LLM and NO DB here (CLAUDE.md §8.1/§8.2).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.misconceptions import (
    MisconceptionId,
    WrongFraction,
    add_across,
    add_magnitudes_ignoring_sign,
    additive_ratio,
    decimal_point_misplacement,
    gcf_lcm_confusion,
    invert_conversion,
    invert_rate,
    keep_original_sign,
    multiply_without_inverting,
    natural_number_bias_number_line,
    part_part_ratio,
    place_value_slip,
    signed_not_magnitude,
    subtract_across,
)
from app.domain.problem_generators import AnswerKind, Problem


class ErrorCategory(StrEnum):
    """Coarse, labeled classification of a verified answer — the §3.6 routing key.

    The string VALUES match the api ``ErrorType`` placeholder verbatim
    (none/magnitude/operation/format/other). This domain enum is the source of
    truth the API imports later (ARCHITECTURE.md §4); changing a VALUE is a
    breaking change to the policy that routes on it (PROJECT.md §3.6).

    ``FORMAT`` is in the closed set because the §3.6 table groups "operation/format
    error -> S3"; Slice 1.4's numeric verifier produces ``operation`` for the
    modeled wrong-procedure errors and does not yet emit ``format`` (a format error
    is a representation-entry problem the numeric verifier cannot observe), but the
    value exists so the enum is the complete routing alphabet from the start.
    """

    NONE = "none"
    MAGNITUDE = "magnitude"
    OPERATION = "operation"
    FORMAT = "format"
    OTHER = "other"


@dataclass(frozen=True)
class VerificationResult:
    """The verifier's verdict on one submitted answer.

    Frozen because a verdict is a fact about a turn, not mutable state — nothing
    downstream may rewrite what the verifier decided (ARCHITECTURE.md §14,
    CLAUDE.md §8.4). The three fields are exactly what the turn loop needs:

    - ``is_correct``           the SymPy correctness verdict (§9: SymPy decides).
    - ``error_category``       the §3.6 routing key; ``NONE`` when correct.
    - ``matched_misconception`` which named misconception the wrong answer matched
      (Slice 1.2 id), or ``None`` when correct or unrecognized. This lets the
      tutor's diagnostic log and the persona evaluation see *which* error fired,
      not merely its coarse category.
    """

    is_correct: bool
    error_category: ErrorCategory
    matched_misconception: MisconceptionId | None


# A submitted answer may arrive as a raw "a/b" string from the API boundary, as a
# plain int, or as an already-typed SymPy Rational/Integer from in-process callers
# (e.g. the persona simulator). We accept all three and normalize to one Rational.
Submitted: TypeAlias = str | int | Rational

# A decimal LITERAL: optional sign, then either ``digits[.digits]`` (incl. a trailing point,
# "10.") or ``.digits`` (a leading point, ".5"). This is intentionally narrow — it matches a single
# plain decimal number, NOT an expression — so the parse never evaluates arbitrary input. A
# match is fed to ``Rational(<the original string>)``, which parses the decimal EXACTLY (e.g.
# "0.1" → 1/10), unlike ``Rational(float("0.1"))`` which carries binary-fraction fuzz.
_DECIMAL_LITERAL = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)$")


def _parse_to_rational(submitted: Submitted) -> Rational | None:
    """Parse a submitted answer to a SymPy ``Rational``, or ``None`` if impossible.

    Why this exists: correctness must be decided by SymPy on a single normalized
    magnitude (ARCHITECTURE.md §9). We accept the shapes a numeric answer arrives in
    — a ``Rational``/``int``, an ``"a/b"`` fraction string, a bare integer string, or
    a DECIMAL literal ("3.5", "0.75") — and reduce them to one ``Rational`` so SymPy
    equality is the only decision rule. We deliberately do NOT use ``sympify``/``eval``
    on the string: evaluating arbitrary expressions would both widen the input surface
    and risk treating a learner's typo as an expression, so each accepted shape is matched
    explicitly. Anything that is not a clean ``a/b``, integer, or decimal literal returns
    ``None`` — the caller then reports the answer as wrong rather than raising on learner
    input (the verifier must never crash on what a kid types).

    A decimal is parsed by ``Rational(<string>)`` (NOT ``Rational(float(...))``): the string
    constructor reads the decimal literal exactly, so "0.1" is 1/10, keeping the oracle
    SymPy-exact (CLAUDE.md §8.2) — a binary ``float`` never enters the correctness decision.

    A zero denominator (``n/0``) is an undefined magnitude, not a value the learner
    can be "correct" with, so it also returns ``None`` rather than letting SymPy
    raise.
    """
    # A SymPy Rational (which includes Integer — Integer is a Rational subclass) is
    # already the normalized form; pass it straight through.
    if isinstance(submitted, Rational):
        return submitted
    if isinstance(submitted, bool):
        # bool is an int subclass in Python; a True/False is never a fraction answer.
        return None
    if isinstance(submitted, int):
        return Rational(submitted)

    text = submitted.strip()
    if not text:
        return None
    if "/" in text:
        numerator_text, _, denominator_text = text.partition("/")
        try:
            numerator = int(numerator_text.strip())
            denominator = int(denominator_text.strip())
        except ValueError:
            return None
        if denominator == 0:
            return None  # undefined magnitude — not a value to be correct with
        return Rational(numerator, denominator)
    if _DECIMAL_LITERAL.match(text) and any(ch.isdigit() for ch in text):
        # A decimal literal ("3.5", ".5", "10."): parse the STRING exactly. (The digit check
        # rejects a lone "." or sign that the literal pattern's optional parts would otherwise
        # let through.) Rational(str) is exact — no float ever touches the correctness decision.
        return Rational(text)
    try:
        return Rational(int(text))
    except ValueError:
        return None


_YES_TOKENS = frozenset({"yes", "y", "true"})
_NO_TOKENS = frozenset({"no", "n", "false"})


def _parse_to_bool(submitted: Submitted) -> bool | None:
    """Parse a yes/no submission to a bool, or ``None`` if it is neither.

    Accepts the kid-facing 'yes'/'no' (case- and whitespace-insensitive) plus the
    in-process ``bool`` a non-UI caller might pass. Anything else (a number, blank, or
    junk) returns ``None`` — the caller reports it wrong rather than crashing, exactly
    as the numeric path treats an unparseable answer."""
    if isinstance(submitted, bool):
        return submitted
    if not isinstance(submitted, str):
        return None
    token = submitted.strip().lower()
    if token in _YES_TOKENS:
        return True
    if token in _NO_TOKENS:
        return False
    return None


def _verify_yes_no(problem: Problem, submitted: Submitted) -> VerificationResult:
    """Verify a yes/no judgment over the two operands. The truth is SymPy: equality
    ("same amount?" — 2/3 == 4/6 → YES) or, when ``yes_no_relation`` is "greater", a
    magnitude comparison ("is a greater than b?" — the symbolic form of number-line
    placement). A wrong judgment is a MAGNITUDE error (the learner misjudged the amounts —
    §3.6 routes it to S2, the number line). We do not over-claim a misconception match."""
    operands = problem.operands
    if operands is None or len(operands) != 2:
        # A yes/no item without a fraction pair is a CONSTRUCTION bug (not learner
        # input): there is nothing for SymPy to judge over. Fail loudly (CLAUDE.md §8.5)
        # rather than silently scoring a meaningless verdict.
        raise ValueError(
            f"yes/no problem {problem.problem_id!r} needs exactly two operands to verify"
        )

    answer = _parse_to_bool(submitted)
    if answer is None:
        return VerificationResult(
            is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
        )

    if problem.yes_no_relation == "greater":
        truth = bool(operands[0] > operands[1])
    else:
        truth = bool(operands[0] == operands[1])
    if answer == truth:
        return VerificationResult(
            is_correct=True, error_category=ErrorCategory.NONE, matched_misconception=None
        )
    return VerificationResult(
        is_correct=False, error_category=ErrorCategory.MAGNITUDE, matched_misconception=None
    )


def _verify_common_denominator(problem: Problem, submitted: Submitted) -> VerificationResult:
    """Verify a common-denominator answer: ANY positive common multiple is correct (§3.4.1).

    The skill is "find A common denominator", which is satisfied by any positive integer that
    both denominators divide — 12 AND 24 are both correct common denominators for 3/4 and 1/6.
    Accepting only the LEAST would measure LCM/efficiency, a different construct (a validity
    error per the §3.4.1 learning-science decision). SymPy still decides: we parse the
    submission to a Rational and check it is a positive integer that is a multiple of BOTH
    operand denominators. ``correct_value`` (the LCD) stays as the canonical least anchor the
    worked example / hints teach, but it is NOT the only accepted answer.

    A wrong answer is an OPERATION error (the procedure for matching piece-sizes broke — §3.6
    routes OPERATION to S3, the area model, which is exactly the right remediation: show the
    pieces). A non-numeric / non-integer / non-positive submission is OTHER (no procedure to
    route on). We do not claim a specific misconception match here.
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        # A construction bug, not learner input: no denominator pair to judge against.
        raise ValueError(
            f"common-denominator problem {problem.problem_id!r} needs exactly two operands"
        )

    value = _parse_to_rational(submitted)
    # Must be a positive WHOLE number (a denominator/piece-count). A fraction or n/0 is not.
    if value is None or value <= 0 or value.q != 1:
        return VerificationResult(
            is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
        )

    candidate = int(value)
    d1, d2 = int(operands[0].q), int(operands[1].q)
    if candidate % d1 == 0 and candidate % d2 == 0:
        return VerificationResult(
            is_correct=True, error_category=ErrorCategory.NONE, matched_misconception=None
        )
    return VerificationResult(
        is_correct=False, error_category=ErrorCategory.OPERATION, matched_misconception=None
    )


def _across_value(wrong: WrongFraction) -> Rational | None:
    """The reduced VALUE of a raw across-error fraction, or ``None`` for an undefined (n/0) one.

    The across-error generators return a RAW (unreduced, possibly sign-flipped or zero-denominator)
    fraction, because that impossibility is the diagnostic signal (misconceptions.py keeps it raw).
    We match on the reduced VALUE — a learner who writes 2/6 for the add-across of 1/2+1/4 exhibits
    the misconception whether they leave it 2/6 or reduce to 1/3. A zero denominator is an undefined
    magnitude no submitted value can equal, so it yields ``None`` (and we never ask SymPy for n/0).
    """
    if wrong.denominator == 0:
        return None
    return Rational(wrong.numerator, wrong.denominator)


@dataclass(frozen=True)
class _WrongAnswerModel:
    """A value-producing misconception the verifier matches a wrong numeric answer against (HR.A2).

    ``predict`` replays the Slice-1.2 misconception generator on the problem's operands and returns
    the wrong VALUE it models (or ``None`` when it does not apply). A match classifies the answer
    with this model's ``error_category`` + ``misconception``. New lessons add a ROW here, not a new
    ``if kc is ...`` branch — the generalization HR.A2 buys (HYPERREACTIVE.md §3)."""

    kc: KnowledgeComponentId
    operand_count: int
    error_category: ErrorCategory
    misconception: MisconceptionId
    predict: Callable[[tuple[Rational, ...]], Rational | None]


# The value-producing misconception models, grounded in the PROJECT.md §3.6 table:
#   - add-across on addition  -> wrong PROCEDURE (tops+tops/bottoms+bottoms): OPERATION (S3).
#   - subtract-across on subtraction -> same operate-on-parts family; misconceptions.py labels it
#     natural-number-bias (a citation-honesty relabel, RESEARCH.md §6.4): OPERATION (S3).
#   - number-line bias position on placement -> misjudged MAGNITUDE (read denominator as position):
#     MAGNITUDE (S2).
# A wrong answer matching none (e.g. on equivalence/common-denominator) stays OTHER — we do NOT
# invent a routing for an unrecognized error (CLAUDE.md §12).
_WRONG_ANSWER_MODELS: tuple[_WrongAnswerModel, ...] = (
    _WrongAnswerModel(
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.ADD_ACROSS_ERROR,
        predict=lambda ops: _across_value(add_across(ops[0].p, ops[0].q, ops[1].p, ops[1].q)),
    ),
    _WrongAnswerModel(
        kc=KnowledgeComponentId.SUBTRACTION_UNLIKE,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.NATURAL_NUMBER_BIAS,
        predict=lambda ops: _across_value(subtract_across(ops[0].p, ops[0].q, ops[1].p, ops[1].q)),
    ),
    _WrongAnswerModel(
        kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        operand_count=1,
        error_category=ErrorCategory.MAGNITUDE,
        misconception=MisconceptionId.NATURAL_NUMBER_BIAS,
        predict=lambda ops: natural_number_bias_number_line(ops[0].p, ops[0].q).biased_position,
    ),
    # ratio-language part-part-whole confusion: answered the part-TO-part ratio (part/other)
    # when the part-TO-whole ratio (part/(part+other)) was asked. A wrong OPERATION (compared
    # against the wrong reference — the other part, not the whole). Operands are (part, other).
    _WrongAnswerModel(
        kc=KnowledgeComponentId.RATIO_LANGUAGE,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.PART_PART_WHOLE_CONFUSION,
        predict=lambda ops: part_part_ratio(int(ops[0]), int(ops[1])),
    ),
    # unit-rate inversion: total/count formed upside-down as count/total — a wrong OPERATION
    # setup (operands are (total, count), both whole-number Rationals).
    _WrongAnswerModel(
        kc=KnowledgeComponentId.UNIT_RATE,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.RATE_INVERSION,
        predict=lambda ops: invert_rate(int(ops[0]), int(ops[1])),
    ),
    # additive ratio: scaled a:b -> ?:target_den by adding instead of multiplying (operands are
    # (a, b, target_den)). A wrong OPERATION (additive vs multiplicative reasoning).
    _WrongAnswerModel(
        kc=KnowledgeComponentId.EQUIVALENT_RATIOS,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.ADDITIVE_RATIO,
        predict=lambda ops: additive_ratio(int(ops[0]), int(ops[1]), int(ops[2])),
    ),
    # percent-as-amount: answers the percent number itself instead of that percent OF the whole
    # (operands are (percent, whole)). A wrong OPERATION (ignored the base).
    _WrongAnswerModel(
        kc=KnowledgeComponentId.PERCENT,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.PERCENT_AS_AMOUNT,
        predict=lambda ops: ops[0],
    ),
    # multiply-as-add: multiplied two fractions by ADDING them instead (operands are the two
    # fractions). A wrong OPERATION (x treated as +) — the sum is larger than the product.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.MULTIPLY_FRACTIONS,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.MULTIPLY_AS_ADD,
        predict=lambda ops: ops[0] + ops[1],
    ),
    # multiply-without-inverting: divided two fractions by multiplying straight across, skipping the
    # flip (operands are the two fractions). A wrong OPERATION (ran multiplication on a division).
    _WrongAnswerModel(
        kc=KnowledgeComponentId.DIVIDE_FRACTIONS,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.MULTIPLY_WITHOUT_INVERTING,
        predict=lambda ops: multiply_without_inverting(ops[0], ops[1]),
    ),
    # conversion-inversion: converted to the smaller unit by DIVIDING by the factor instead of
    # multiplying (operands are (quantity, factor)). A wrong OPERATION (applied the factor upside-
    # down), so the result is smaller than the quantity instead of larger.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.UNIT_CONVERSION,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.CONVERSION_INVERSION,
        predict=lambda ops: invert_conversion(int(ops[0]), int(ops[1])),
    ),
    # gcf-lcm-confusion: answered the OTHER aggregate (LCM when GCF asked, or vice versa). Operands
    # are (a, b, mode); mode 1 == LCM asked. A wrong OPERATION (took multiples not factors, or the
    # reverse) — applied the wrong aggregating operation to the right operands.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.GCF_LCM,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.GCF_LCM_CONFUSION,
        predict=lambda ops: gcf_lcm_confusion(int(ops[0]), int(ops[1]), lcm_asked=int(ops[2]) == 1),
    ),
    # place-value-slip: the right quotient digits off by a factor of 10 (a dropped/extra zero in
    # long division). Operands are (dividend, divisor). A misjudged MAGNITUDE (the procedure was
    # right; the place value slipped), so the answer is 10x the quotient.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.MULTI_DIGIT_DIVISION,
        operand_count=2,
        error_category=ErrorCategory.MAGNITUDE,
        misconception=MisconceptionId.PLACE_VALUE_SLIP,
        predict=lambda ops: place_value_slip(int(ops[0]), int(ops[1])),
    ),
    # decimal-point-misplacement: multiplied the digits right but placed the product's point by the
    # longer factor's place count, not the SUM — so the value is off by a power of ten (operands are
    # the two decimal factors). The DIGITS are right, the SIZE is wrong: a MAGNITUDE error (routes
    # to the size-exposing surface, §3.6), distinct from the OPERATION errors above.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.DECIMAL_OPERATIONS,
        operand_count=2,
        error_category=ErrorCategory.MAGNITUDE,
        misconception=MisconceptionId.DECIMAL_POINT_MISPLACEMENT,
        predict=lambda ops: decimal_point_misplacement(ops[0], ops[1]),
    ),
    # signed-not-magnitude: reported the signed value itself instead of its distance from 0
    # (|-7| -> -7). Operands are (value,), the signed input. A misjudged MAGNITUDE (a magnitude
    # can never be negative; the learner kept the sign), so the wrong answer is the input unchanged.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.ABSOLUTE_VALUE,
        operand_count=1,
        error_category=ErrorCategory.MAGNITUDE,
        misconception=MisconceptionId.SIGNED_NOT_MAGNITUDE,
        predict=lambda ops: signed_not_magnitude(int(ops[0])),
    ),
    # sign-handling-error: combined two opposite-sign integers by ADDING their magnitudes, ignoring
    # the signs (operands are (a, b)). A wrong OPERATION — applied whole-number addition instead of
    # signed combination, so the answer is |a| + |b| rather than a + b.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.INTEGER_ADD_SUBTRACT,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.SIGN_HANDLING_ERROR,
        predict=lambda ops: add_magnitudes_ignoring_sign(ops[0], ops[1]),
    ),
    # sign-error: answered the number unchanged when its OPPOSITE was asked (operand is (n,)). A
    # wrong OPERATION — the magnitude is right but the negation (flip across zero) was not applied.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.SIGNED_NUMBERS,
        operand_count=1,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.SIGN_ERROR,
        predict=lambda ops: keep_original_sign(ops[0]),
    ),
)


def _classify_wrong_answer(
    problem: Problem, submitted_value: Rational
) -> tuple[ErrorCategory, MisconceptionId | None]:
    """Classify a wrong numeric answer by looping the value-producing misconception models (HR.A2).

    Replaces the old per-KC ``if`` branches with a uniform loop over ``_WRONG_ANSWER_MODELS``: for
    each model whose KC + operand count match this problem, replay its predictor and compare the
    submitted VALUE (SymPy equality). The first match classifies; no match is the honest OTHER
    (no misconception). Behavior is identical to the prior branches for the 5 KCs — a new KC is
    added as a model row, not a code branch.
    """
    operands = problem.operands
    if operands is None:
        return ErrorCategory.OTHER, None

    for model in _WRONG_ANSWER_MODELS:
        if model.kc is problem.kc and len(operands) == model.operand_count:
            predicted = model.predict(operands)
            if predicted is not None and bool(submitted_value == predicted):
                return model.error_category, model.misconception

    return ErrorCategory.OTHER, None


def verify(problem: Problem, submitted: Submitted) -> VerificationResult:
    """Verify a NUMERIC submitted answer against ``problem.correct_value`` with SymPy.

    Correctness rule (ARCHITECTURE.md §9, §14 invariant 2): the submission is parsed
    to a single SymPy ``Rational`` and judged by exact SymPy equality against the
    problem's SymPy-computed ``correct_value``. SymPy decides — never a tolerance,
    never a string compare, never an LLM. Equality is on VALUE, so an unreduced form
    (2/4 for 1/2) is correct: the verifier judges the magnitude, and §3.1 scope does
    not require lowest-terms.

    Number-line placement: the answer is a fraction's exact position on the 0–1 line,
    and our placement problems use exact rationals, so we compare with EXACT Rational
    equality (no tolerance). A pixel/drag tolerance for a continuous drag surface is a
    UI/turn-loop concern (the surface snaps a drag to a candidate Rational before it
    reaches the domain), not a correctness concern — introducing a tolerance here
    would let "close enough" pass as mastery, which the mastery model is explicitly
    designed to prevent (ARCHITECTURE.md §2 "mastery must be earned"). Documented as a
    deliberate decision: tolerance, if ever needed, belongs at the surface, not in the
    oracle.

    On a wrong answer, ``_classify_wrong_answer`` assigns the §3.6 routing category by
    matching the submission against the misconception generators on the operands.

    Common denominator (``kc == COMMON_DENOMINATOR``) routes to
    ``_verify_common_denominator``: ANY positive common multiple of the two operand
    denominators is correct, not only the least (§3.4.1) — SymPy checks the divisibility.

    yes/no relational judgments ("Is 2/3 the same amount as 4/6?") route to
    ``_verify_yes_no``: the truth is SymPy equality over the two operands, so SymPy
    still decides — no stored answer. A problem opts in via ``answer_kind=YES_NO``
    (the default ``NUMERIC`` keeps every procedural generator and bank item on the
    magnitude path). STILL DEFERRED: multi-point ordering, which needs a structured
    ordered-answer carrier the ``Problem`` type does not yet have.
    """
    if problem.answer_kind is AnswerKind.YES_NO:
        return _verify_yes_no(problem, submitted)

    if problem.kc is KnowledgeComponentId.COMMON_DENOMINATOR:
        return _verify_common_denominator(problem, submitted)

    submitted_value = _parse_to_rational(submitted)
    if submitted_value is None:
        # Unparseable or undefined (n/0, blank, non-numeric): not correct, and there
        # is no magnitude to match against a misconception — honestly "other".
        return VerificationResult(
            is_correct=False,
            error_category=ErrorCategory.OTHER,
            matched_misconception=None,
        )

    if submitted_value == problem.correct_value:
        return VerificationResult(
            is_correct=True,
            error_category=ErrorCategory.NONE,
            matched_misconception=None,
        )

    category, matched = _classify_wrong_answer(problem, submitted_value)
    return VerificationResult(
        is_correct=False,
        error_category=category,
        matched_misconception=matched,
    )


__all__ = ["ErrorCategory", "VerificationResult", "verify"]
