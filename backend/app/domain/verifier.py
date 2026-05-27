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

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.misconceptions import (
    MisconceptionId,
    add_across,
    natural_number_bias_number_line,
    subtract_across,
)
from app.domain.problem_generators import Problem


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


def _parse_to_rational(submitted: Submitted) -> Rational | None:
    """Parse a submitted answer to a SymPy ``Rational``, or ``None`` if impossible.

    Why this exists: correctness must be decided by SymPy on a single normalized
    magnitude (ARCHITECTURE.md §9). We accept the three shapes a numeric answer
    arrives in and reduce them to one ``Rational`` so SymPy equality is the only
    decision rule. We deliberately do NOT use ``sympify``/``eval`` on the string:
    a fraction answer is an ``"a/b"`` (or bare integer) form, and evaluating
    arbitrary expressions would both widen the input surface and risk treating a
    learner's typo as an expression. Anything that is not a clean ``a/b`` or
    integer returns ``None`` — the caller then reports the answer as wrong rather
    than raising on learner input (the verifier must never crash on what a kid
    types).

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
    try:
        return Rational(int(text))
    except ValueError:
        return None


def _classify_wrong_answer(
    problem: Problem, submitted_value: Rational
) -> tuple[ErrorCategory, MisconceptionId | None]:
    """Classify a wrong numeric answer by matching it against the §3.6 misconceptions.

    We replay the Slice-1.2 misconception generators on ``problem.operands`` and
    compare the submitted VALUE (SymPy equality) to each modeled wrong answer. The
    category mapping is grounded in the PROJECT.md §3.6 transition table:

      - add-across on an addition problem -> the learner ran the wrong PROCEDURE
        (added tops and bottoms). §3.6: "operation/format error -> S3". So
        category=OPERATION, misconception=add-across-error.
      - subtract-across on a subtraction problem -> the same wrong-procedure family
        (operate on the parts separately); misconceptions.py labels it
        natural-number-bias (a citation-honesty relabel, RESEARCH.md §6.4). Still an
        operation error -> S3. category=OPERATION, misconception=natural-number-bias.
      - number-line bias position on a placement problem -> the learner misjudged the
        MAGNITUDE (read the denominator as a position). §3.6: "magnitude error -> S2".
        category=MAGNITUDE, misconception=natural-number-bias.

    Anything else (a wrong answer matching no modeled misconception, or a wrong
    answer on equivalence/common-denominator — KCs the task does not map to a §3.6
    category) is OTHER with no matched misconception. We do NOT invent a routing for
    an unrecognized error (CLAUDE.md §12): "other" is the honest label, and the
    policy can fall back to a default move rather than a misattributed one.
    """
    operands = problem.operands
    if operands is None:
        return ErrorCategory.OTHER, None

    if problem.kc is KnowledgeComponentId.ADDITION_UNLIKE and len(operands) == 2:
        first, second = operands
        across = add_across(first.p, first.q, second.p, second.q)
        if _matches(submitted_value, across.numerator, across.denominator):
            return ErrorCategory.OPERATION, MisconceptionId.ADD_ACROSS_ERROR

    elif problem.kc is KnowledgeComponentId.SUBTRACTION_UNLIKE and len(operands) == 2:
        minuend, subtrahend = operands
        across = subtract_across(minuend.p, minuend.q, subtrahend.p, subtrahend.q)
        if _matches(submitted_value, across.numerator, across.denominator):
            return ErrorCategory.OPERATION, MisconceptionId.NATURAL_NUMBER_BIAS

    elif problem.kc is KnowledgeComponentId.NUMBER_LINE_PLACEMENT and len(operands) == 1:
        (target,) = operands
        misplacement = natural_number_bias_number_line(target.p, target.q)
        if submitted_value == misplacement.biased_position:
            return ErrorCategory.MAGNITUDE, MisconceptionId.NATURAL_NUMBER_BIAS

    return ErrorCategory.OTHER, None


def _matches(submitted_value: Rational, raw_numerator: int, raw_denominator: int) -> bool:
    """Whether a submitted value equals a misconception's raw wrong fraction by VALUE.

    The across-error generators return a RAW (unreduced, possibly sign-flipped or
    zero-denominator) fraction, because that impossibility is the diagnostic signal
    (misconceptions.py keeps it raw). We compare on the reduced VALUE — a learner
    who writes 2/6 for the add-across of 1/2+1/4 is exhibiting the misconception
    whether they leave it 2/6 or reduce it to 1/3. A zero denominator is an
    undefined magnitude that no submitted value can equal, so it never matches
    (and we avoid asking SymPy to build n/0).
    """
    if raw_denominator == 0:
        return False
    # SymPy equality returns a SymPy truth object; coerce to a plain bool so the
    # signature's `-> bool` is honored (mypy --strict).
    return bool(submitted_value == Rational(raw_numerator, raw_denominator))


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

    DEFERRED (out of Slice 1.4 scope): yes/no relational judgments and multi-point
    ordering. Those bank items carry only a magnitude *anchor* in ``correct_value``
    (the committed ``Problem`` type has no structured-answer field), so verifying the
    learner's actual yes/no or ordering against the true judgment is not possible
    without extending the ``Problem`` type — which this slice must NOT do. A later
    slice adds a structured-answer carrier and the matching verifier path; until then
    this function treats only the numeric magnitude, which is correct for all five
    procedural KCs and for the fraction/point bank items.
    """
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
