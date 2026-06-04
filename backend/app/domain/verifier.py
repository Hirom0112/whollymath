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

from sympy import Rational, simplify, sympify
from sympy.core.relational import Relational
from sympy.core.sympify import SympifyError

from app.domain.center_spread import SPREAD_RANGE, range_as_sum
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.misconceptions import (
    NUMBER_SET_LABELS,
    MisconceptionId,
    WrongFraction,
    add_across,
    add_edges_instead_of_multiplying,
    add_instead_of_applying_rate,
    add_magnitudes_ignoring_sign,
    add_withdrawal_instead_of_subtracting,
    additive_ratio,
    confuse_coefficient_with_constant,
    count_three_faces_only,
    decimal_point_misplacement,
    distinct_value_count,
    distributive_error,
    evaluate_left_to_right,
    flip_result_sign,
    flipped_inequality,
    forget_trapezoid_half,
    forget_triangle_half,
    forgot_to_multiply_by_years,
    gcf_lcm_confusion,
    inverse_operation_error,
    invert_conversion,
    invert_rate,
    keep_original_sign,
    mean_signed_deviation,
    multiply_base_by_exponent,
    multiply_without_inverting,
    natural_number_bias_number_line,
    omit_rational_for_integer,
    parse_points,
    part_part_ratio,
    part_whole_ratio,
    percent_as_amount,
    place_value_slip,
    reversed_operands,
    signed_not_magnitude,
    solution_substitution_error,
    subtract_across,
    swap_coordinates,
    triangle_formula_error,
    unsorted_middle,
    wrong_denominator_relative_frequency,
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


def _safe_sympify(text: str) -> object | None:
    """Parse a submitted expression string to a SymPy object, or ``None`` if it can't.

    The verifier must NEVER crash on what a learner types (CLAUDE.md §8.2). ``sympify`` raises
    ``SympifyError`` (or ``SyntaxError``/``TypeError`` on malformed input) for garbled strings; we
    catch and return ``None`` so the caller scores it wrong rather than raising. We do NOT evaluate
    with ``eval`` — ``sympify`` parses an algebraic expression, not arbitrary Python.
    """
    try:
        parsed: object = sympify(text)
        return parsed
    except (SympifyError, SyntaxError, TypeError, ValueError, AttributeError):
        return None


def _expressions_equivalent(a: object, b: object) -> bool:
    """True iff two SymPy expressions are symbolically equal — ``simplify(a - b) == 0``.

    This is the equivalence rule the EXPRESSION answer kind grades by (so "7+p" == "p+7"): not a
    string or structural match, but algebraic equality. Wrapped so a non-numeric ``simplify``
    result (it never should be here) is treated as not-equal rather than raising.
    """
    try:
        return bool(simplify(a - b) == 0)  # type: ignore[operator]
    except (TypeError, ValueError, AttributeError):
        return False


def _verify_expression(problem: Problem, submitted: Submitted) -> VerificationResult:
    """Verify an EXPRESSION answer by SymPy EQUIVALENCE against ``correct_expression``.

    Grading rule (the frozen expression contract): ``sympify`` the submission and the canonical
    answer, correct iff ``simplify(submitted - correct) == 0`` — so any algebraically equal form
    ("7+p" for "p+7", "p+7+0") is correct, never a string match. Unparseable input is wrong
    (OTHER), never a crash (CLAUDE.md §8.2). A wrong-but-parseable answer that equals the
    reversed-operands form (e.g. "7-p" for the canonical "p-7") is the reversed-operands
    misconception → OPERATION; any other wrong answer is OTHER (we do not over-claim a match).
    """
    canonical_text = problem.correct_expression
    if canonical_text is None:
        # Construction bug, not learner input: an EXPRESSION problem must carry its answer.
        raise ValueError(f"expression problem {problem.problem_id!r} needs a correct_expression")

    submitted_expr = _safe_sympify(str(submitted))
    if submitted_expr is None:
        return VerificationResult(
            is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
        )

    canonical_expr = sympify(canonical_text)  # generator-built, always parseable
    if _expressions_equivalent(submitted_expr, canonical_expr):
        return VerificationResult(
            is_correct=True, error_category=ErrorCategory.NONE, matched_misconception=None
        )

    # Reversed-operands misconception: the submission equals the order-swapped form of a
    # non-commutative answer (only defined for subtraction/division; None otherwise).
    reversed_text = reversed_operands(canonical_text)
    if reversed_text is not None and _expressions_equivalent(
        submitted_expr, sympify(reversed_text)
    ):
        return VerificationResult(
            is_correct=False,
            error_category=ErrorCategory.OPERATION,
            matched_misconception=MisconceptionId.REVERSED_OPERANDS,
        )

    # Distributive-error misconception (KC_equivalent_expressions): the submission equals the
    # partially-distributed form of the GIVEN expression — the multiplier reached only the first
    # term ("3x + 2" for "3(x + 2)"). Replayed from ``source_expression`` (it cannot be derived
    # from the answer alone); ``None`` when the source has no distributable structure.
    distributive_text = distributive_error(problem.source_expression)
    if distributive_text is not None and _expressions_equivalent(
        submitted_expr, sympify(distributive_text)
    ):
        return VerificationResult(
            is_correct=False,
            error_category=ErrorCategory.OPERATION,
            matched_misconception=MisconceptionId.DISTRIBUTIVE_ERROR,
        )

    return VerificationResult(
        is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
    )


def _safe_sympify_relational(text: str) -> Relational | None:
    """Parse a submitted string to a SymPy RELATIONAL, or ``None`` if it isn't one.

    Like ``_safe_sympify`` but additionally requires the result to be a ``Relational`` (an
    inequality) — a plain expression ("x + 3"), a bare number, or garbled input all yield ``None``
    so the inequality path scores them wrong rather than crashing (CLAUDE.md §8.2). Parsed with
    ``evaluate=False`` so "5 < 3" stays a relational rather than collapsing to ``False``.
    """
    try:
        parsed: object = sympify(text, evaluate=False)
    except (SympifyError, SyntaxError, TypeError, ValueError, AttributeError, IndexError):
        # IndexError: SymPy's evaluate=False parser raises it on empty / non-expression input.
        return None
    return parsed if isinstance(parsed, Relational) else None


def _inequalities_equivalent(a: Relational, b: Relational) -> bool:
    """True iff two inequalities have the SAME solution set — same variable, direction, and bound.

    The equivalence rule the INEQUALITY answer kind grades by (so "x>=5" == "5<=x", but "x>3" !=
    "x>=3"). ``.canonical`` puts the variable on the left and normalizes the operator class, so an
    order-flipped-but-equivalent form matches; then the operator CLASS must be identical (strict vs.
    non-strict differ) and the bounds must be equal. Wrapped so a non-numeric comparison is treated
    as not-equal rather than raising.
    """
    try:
        ca, cb = a.canonical, b.canonical
        if type(ca) is not type(cb):
            return False
        return ca.lhs == cb.lhs and bool(simplify(ca.rhs - cb.rhs) == 0)
    except (TypeError, ValueError, AttributeError):
        return False


def _verify_inequality(problem: Problem, submitted: Submitted) -> VerificationResult:
    """Verify an INEQUALITY answer by relational EQUIVALENCE against ``correct_inequality``.

    Grading rule (the frozen inequality contract): parse the submission and the canonical answer as
    relationals, correct iff they have the SAME solution set (same variable, direction, and bound) —
    so "x>=5" == "5<=x" (both ``>=``/``<=`` ASCII forms accepted), but "x>3" != "x>=3". Unparseable
    OR non-relational input (a plain expression, a bare number, an equality) is wrong (OTHER), never
    a crash (CLAUDE.md §8.2). A wrong-but-relational answer that equals the flipped-direction form
    (e.g. "x<5" for the canonical "x>=5") is the flipped-inequality misconception → OPERATION; any
    other wrong answer is OTHER (we do not over-claim a match).
    """
    canonical_text = problem.correct_inequality
    if canonical_text is None:
        # Construction bug, not learner input: an INEQUALITY problem must carry its answer.
        raise ValueError(f"inequality problem {problem.problem_id!r} needs a correct_inequality")

    submitted_rel = _safe_sympify_relational(str(submitted))
    if submitted_rel is None:
        return VerificationResult(
            is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
        )

    canonical_rel = sympify(canonical_text, evaluate=False)  # generator-built, always relational
    assert isinstance(canonical_rel, Relational)
    if _inequalities_equivalent(submitted_rel, canonical_rel):
        return VerificationResult(
            is_correct=True, error_category=ErrorCategory.NONE, matched_misconception=None
        )

    # Flipped-direction misconception: the submission equals the wrong-direction form (same bound,
    # reversed comparison) — "x<5" for the canonical "x>=5".
    flipped_text = flipped_inequality(canonical_text)
    if flipped_text is not None:
        flipped_rel = sympify(flipped_text, evaluate=False)
        if isinstance(flipped_rel, Relational) and _inequalities_equivalent(
            submitted_rel, flipped_rel
        ):
            return VerificationResult(
                is_correct=False,
                error_category=ErrorCategory.OPERATION,
                matched_misconception=MisconceptionId.FLIPPED_INEQUALITY,
            )

    return VerificationResult(
        is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
    )


def _verify_coordinate(problem: Problem, submitted: Submitted) -> VerificationResult:
    """Verify a COORDINATE answer by ORDER-INSENSITIVE SET equality against ``correct_points``.

    Grading rule (the frozen coordinate contract): parse the submission and the canonical answer to
    SETS of integer ``(x, y)`` points (``parse_points``) and compare the sets — a polygon's vertices
    match in any order, a single point is a one-element set. SymPy/domain decides by parsing integer
    tuples; never an LLM (CLAUDE.md §8.2). Unparseable input (blank, malformed, decimal/variable
    coordinates, wrong arity, trailing junk) is wrong (OTHER), never a crash. A wrong-but-parseable
    answer that equals the coordinate-swapped set (e.g. "(-1,2)" for the canonical "(2,-1)") is the
    coordinate-swap misconception → OPERATION; any other wrong set is OTHER.
    """
    canonical_text = problem.correct_points
    if canonical_text is None:
        # Construction bug, not learner input: a COORDINATE problem must carry its answer.
        raise ValueError(f"coordinate problem {problem.problem_id!r} needs correct_points")

    submitted_points = parse_points(str(submitted))
    if submitted_points is None:
        return VerificationResult(
            is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
        )

    canonical_points = parse_points(canonical_text)  # generator-built, always parseable
    if submitted_points == canonical_points:
        return VerificationResult(
            is_correct=True, error_category=ErrorCategory.NONE, matched_misconception=None
        )

    # Coordinate-swap misconception: the submission equals the (x, y) -> (y, x) transposed set of a
    # non-symmetric figure (``swap_coordinates`` returns None when swapping changes nothing).
    swapped_text = swap_coordinates(canonical_text)
    if swapped_text is not None and submitted_points == parse_points(swapped_text):
        return VerificationResult(
            is_correct=False,
            error_category=ErrorCategory.OPERATION,
            matched_misconception=MisconceptionId.COORDINATE_SWAP,
        )

    return VerificationResult(
        is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
    )


def _parse_label_set(text: str) -> frozenset[str] | None:
    """Parse a submitted comma-separated label list into a SET of known labels, or ``None``.

    Returns ``None`` when the input is blank, contains no known label, or contains ANY label not in
    ``NUMBER_SET_LABELS`` (an unknown label means the learner answered outside the vocabulary, so
    the answer is not gradeable as a valid set — scored wrong/OTHER by the caller, never a crash,
    CLAUDE.md §8.2). Whitespace around labels is stripped and duplicates collapse (set semantics).
    Case-insensitive on the fixed vocabulary so "Integer" and "integer" parse the same.
    """
    raw = [token.strip().lower() for token in text.split(",")]
    labels = [token for token in raw if token]
    if not labels:
        return None
    vocabulary = {label.lower(): label for label in NUMBER_SET_LABELS}
    if any(label not in vocabulary for label in labels):
        return None
    return frozenset(vocabulary[label] for label in labels)


def _verify_number_sets(problem: Problem, submitted: Submitted) -> VerificationResult:
    """Verify a NUMBER_SETS answer by ORDER-INSENSITIVE SET membership against ``correct_sets``.

    Grading rule (the frozen classify-sets contract): parse the submitted comma-separated labels
    into a SET, correct iff that set EQUALS the canonical membership set (order-insensitive, so
    "rational,integer" == "integer,rational"). An unparseable / unknown-label / empty submission is
    wrong (OTHER), never a crash (CLAUDE.md §8.2). A wrong set that equals the integer-not-rational
    form (the integer's set with ``rational`` dropped) is that misconception → CONCEPTUAL, routed
    OPERATION (the §3.6 routing key for a wrong procedure/concept); any other wrong set is OTHER.
    """
    canonical_text = problem.correct_sets
    if canonical_text is None:
        # Construction bug, not learner input: a NUMBER_SETS problem must carry its answer.
        raise ValueError(f"number-sets problem {problem.problem_id!r} needs a correct_sets")

    submitted_set = _parse_label_set(str(submitted))
    if submitted_set is None:
        return VerificationResult(
            is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
        )

    canonical_set = frozenset(canonical_text.split(","))
    if submitted_set == canonical_set:
        return VerificationResult(
            is_correct=True, error_category=ErrorCategory.NONE, matched_misconception=None
        )

    # integer-not-rational misconception: the submission equals the integer's set with ``rational``
    # dropped (None when the value is not an integer, so the error does not apply).
    omitted_text = omit_rational_for_integer(canonical_text)
    if omitted_text is not None and submitted_set == frozenset(omitted_text.split(",")):
        return VerificationResult(
            is_correct=False,
            error_category=ErrorCategory.OPERATION,
            matched_misconception=MisconceptionId.INTEGER_NOT_RATIONAL,
        )

    return VerificationResult(
        is_correct=False, error_category=ErrorCategory.OTHER, matched_misconception=None
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
    # The exact operand arity this model matches, or ``None`` to match ANY arity. ``None`` is for
    # VARIABLE-LENGTH operand KCs (e.g. KC_mean_absolute_deviation, KC_center_spread_shape, and
    # KC_summary_statistics, whose operands carry a data set, optionally behind a leading mode
    # flag): the predictor reads the whole tuple and the KC alone disambiguates the model. A fixed
    # int (the common case) keeps a model from firing on a wrong-shaped problem of that KC.
    operand_count: int | None
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
    # ratio-language part-part-whole confusion: compared against the WRONG reference. Operands are
    # (mode, colour_idx, part, other) — the confusion is the OTHER ratio, so which value is the
    # mistake depends on which question was asked (mode). A part-WHOLE question (mode 0) is missed
    # by answering the part-TO-part ratio (part/other); a part-PART question (mode 1) is missed by
    # answering the part-of-the-whole fraction (part/(part+other)). Either way a wrong OPERATION
    # (wrong reference), and either way always distinct from the correct value since part >= 1.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.RATIO_LANGUAGE,
        operand_count=4,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.PART_PART_WHOLE_CONFUSION,
        predict=lambda ops: (
            part_part_ratio(int(ops[2]), int(ops[3]))
            if int(ops[0]) == 0
            else part_whole_ratio(int(ops[2]), int(ops[3]))
        ),
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
    # (operands are (percent, whole, mode)). A wrong OPERATION (ignored the base). PERCENT_OF-
    # SPECIFIC: the predictor returns None on the find-the-whole mode (no "percent OF the whole" to
    # skip there), so it never fires off mode 0 — the decimal-point-misplacement gate pattern.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.PERCENT,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.PERCENT_AS_AMOUNT,
        predict=percent_as_amount,
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
    # (first, second, mode)). The DIGITS are right, the SIZE is wrong: a MAGNITUDE error (routes to
    # the size-exposing surface, §3.6), distinct from the OPERATION errors above. MULTIPLY-SPECIFIC:
    # the predictor returns None on add/subtract/divide modes (no product point to misplace), so it
    # never fires off multiply — the AREA_POLYGONS forgot-the-half gate pattern.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.DECIMAL_OPERATIONS,
        operand_count=3,
        error_category=ErrorCategory.MAGNITUDE,
        misconception=MisconceptionId.DECIMAL_POINT_MISPLACEMENT,
        predict=decimal_point_misplacement,
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
    # order-of-operations-slip: evaluated a*x + b left-to-right as a*(x + b) — added before
    # multiplying (operands are (a, x, b)). A wrong OPERATION: the substitution is right, but the
    # operation ORDER ignored precedence, so the value is a*(x + b) instead of a*x + b.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.EVALUATE_EXPRESSIONS,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.ORDER_OF_OPERATIONS_SLIP,
        predict=lambda ops: evaluate_left_to_right(int(ops[0]), int(ops[1]), int(ops[2])),
    ),
    # multiply-base-by-exponent: read a power as one multiplication — base * exponent (3^4 -> 12)
    # instead of base multiplied by itself exponent-many times (3*3*3*3 = 81). Operands are
    # (base, exp). A wrong OPERATION (the exponent was treated as a factor, not a repeat count); the
    # generator excludes 2^2, so the predicted value always differs from the correct power.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.EXPONENTS,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.MULTIPLY_BASE_BY_EXPONENT,
        predict=lambda ops: multiply_base_by_exponent(int(ops[0]), int(ops[1])),
    ),
    # inverse-operation-error: solved a one-step equation with the WRONG inverse — added b for
    # x + b = c, or subtracted a for a*x = c (operands are (mode, p, q)). A wrong OPERATION (reached
    # for the visible operation instead of the one that undoes it). The generator guarantees the
    # predicted value differs from the correct solution, so a match is always diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.ONE_STEP_EQUATIONS,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.INVERSE_OPERATION_ERROR,
        predict=inverse_operation_error,
    ),
    # part-confusion: named the wrong part of an expression — the CONSTANT when the COEFFICIENT was
    # asked (4 instead of 7 for "coefficient of x in 7x + 4"), or the coefficient when the constant
    # was asked. Operands are (mode, coefficient, constant); the predictor returns None for the
    # term-count mode (no swap), so it never fires there. A wrong OPERATION — the learner read the
    # wrong part, not a magnitude misjudgment. The generator keeps coefficient != constant, so the
    # swapped value always differs from the correct answer (the match is diagnostic).
    _WrongAnswerModel(
        kc=KnowledgeComponentId.EXPRESSION_PARTS,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.PART_CONFUSION,
        predict=confuse_coefficient_with_constant,
    ),
    # sign-rule-error: multiplied/divided the magnitudes right but applied the WRONG sign rule —
    # e.g. -3 × 4 -> 12 instead of -12 (operands are (a, b, mode); mode 1 == multiply, 0 == divide).
    # A wrong OPERATION (the arithmetic is right; only the sign rule was misapplied), so the answer
    # is the sign-flipped result -(a*b) / -(a/b). The result is nonzero (both operands nonzero), so
    # the flipped value always differs from the correct one — the match is always diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.SIGN_RULE_ERROR,
        predict=flip_result_sign,
    ),
    # triangle-formula-error: applied the WRONG fixed relationship — subtracted from 90 (not 180)
    # for a missing angle, or dropped the ½ and gave base × height for an area (operands are
    # (a, b, mode); mode 0 == missing angle, 1 == area). A wrong OPERATION (the numbers are read
    # right; the formula is wrong), so the answer is 90 - a - b or a*b. The wrong value always
    # differs from the correct one — an angle off by 90, an area off by a factor of 2 — so the
    # match is always diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.TRIANGLE_PROPERTIES,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.TRIANGLE_FORMULA_ERROR,
        predict=triangle_formula_error,
    ),
    # forgot-triangle-half: applied the rectangle formula b·h to a TRIANGLE, dropping the 1/2 — so
    # the area is twice too big (operands are (base, height, mode); mode 0 == triangle, 1 ==
    # parallelogram). A wrong OPERATION (used the wrong formula, not a magnitude misjudgment); the
    # predictor returns None for the parallelogram mode (b·h IS correct there, no error to model),
    # so it never fires on a parallelogram. base, height > 0, so b·h always differs from b·h/2 —
    # the match is always diagnostic. ``operand_count=3`` keeps this row off the trapezoid item,
    # whose 4-tuple (base1, base2, height, mode) is the forgot-trapezoid-half row's job below.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.AREA_POLYGONS,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.FORGOT_TRIANGLE_HALF,
        predict=forget_triangle_half,
    ),
    # forgot-trapezoid-half: summed the two parallel sides and multiplied by the height but skipped
    # the averaging 1/2 — answering (base1 + base2)·height instead of half of it, so the area is
    # twice too big (operands are the trapezoid's 4-tuple (base1, base2, height, mode); mode 2). The
    # SAME KC carries TWO half-dropping errors that differ ONLY by shape; they are disambiguated by
    # operand ARITY (``operand_count=4`` here vs 3 above), so each fires only on its own figure — no
    # mode branch needed in the loop. A wrong OPERATION (wrong formula). The bases are distinct and
    # positive, so (base1 + base2)·height always differs from its half — the match is diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.AREA_POLYGONS,
        operand_count=4,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.FORGOT_TRAPEZOID_HALF,
        predict=forget_trapezoid_half,
    ),
    # add-edges-error: found a prism's volume by ADDING the edges (l + w + h) instead of MULTIPLYING
    # them (V = l*w*h). Operands are (l, w, h). A wrong OPERATION (summed a perimeter-style total
    # rather than the product). The generator resamples the one l+w+h == l*w*h case, so the summed
    # value always differs from the correct volume — the match is always diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.ADD_EDGES_ERROR,
        predict=lambda ops: add_edges_instead_of_multiplying(ops[0], ops[1], ops[2]),
    ),
    # count-three-faces: summed only ONE face per pair (l*w + l*h + w*h) and forgot to double for
    # the matching opposite faces, so the surface area came out half. Operands are (l, w, h). A
    # wrong OPERATION (dropped the *2, not a face misread). Since l*w + l*h + w*h > 0 for positive,
    # the three-face value always differs from the correct 2*(...) — the match is always diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.SURFACE_AREA_NETS,
        operand_count=3,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.COUNT_THREE_FACES,
        predict=lambda ops: count_three_faces_only(ops[0], ops[1], ops[2]),
    ),
    # forgot-absolute-value: averaged the SIGNED deviations from the mean (skipping the absolute
    # value) instead of their distances, so the answer is always 0 (the deviations cancel). A wrong
    # OPERATION — the deviations are right; the absolute value was never applied. ``operand_count``
    # is None: the MAD's operands are a VARIABLE-LENGTH data set (4–6 values), so the model matches
    # on KC alone and the predictor reads the whole tuple.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION,
        operand_count=None,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.FORGOT_ABSOLUTE_VALUE,
        predict=lambda ops: mean_signed_deviation(ops),
    ),
    # range-as-sum: computed the RANGE by ADDING the extremes (max + min) instead of subtracting
    # them (max − min). Operands are VARIABLE-LENGTH: (mode_flag, *sorted_data) — so operand_count
    # is None (matches any data-set size) and the predictor recovers the mode + data from operands.
    # Only fires on a RANGE item (mode flag == SPREAD_RANGE); on a median/IQR item it returns None
    # so the model does not match (the misconception is range-specific). A wrong OPERATION (added
    # where subtraction was needed). With nonnegative distinct extremes, max + min != max − min.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.CENTER_SPREAD_SHAPE,
        operand_count=None,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.RANGE_AS_SUM,
        predict=lambda ops: range_as_sum(ops[1:]) if int(ops[0]) == SPREAD_RANGE else None,
    ),
    # median-without-sorting: read the middle of the UNSORTED data instead of sorting first. The
    # summary-statistics item is VARIABLE-LENGTH — operands are (mode_code, *data) — so this row
    # uses ``operand_count=None`` to match any arity; the predictor decodes operands[0] and returns
    # ``None`` for any non-median mode (so it only ever fires on a median item). A wrong OPERATION
    # (skipped the sort step). The generator emits only median items whose unsorted middle differs
    # from the sorted median, so a match is diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.SUMMARY_STATISTICS,
        operand_count=None,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.MEDIAN_WITHOUT_SORTING,
        predict=unsorted_middle,
    ),
    # distinct-value-count: counted how many DIFFERENT values lie above the threshold instead of
    # how many DATA POINTS do (reading the x-axis labels, not the dots). The data-displays item is
    # VARIABLE-LENGTH — operands are (question_code, param, *data) — so this row uses
    # ``operand_count=None`` to match any arity; the predictor decodes operands[0] and returns
    # ``None`` for any non-count-above question (so it only ever fires on a count-above item). A
    # wrong OPERATION (collapsed duplicate dots). The generator emits only count-above items with a
    # duplicated value above the threshold, so the distinct count differs and a match is diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.DATA_DISPLAYS,
        operand_count=None,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.DISTINCT_VALUE_COUNT,
        predict=distinct_value_count,
    ),
    # wrong-denominator: computed a category's RELATIVE FREQUENCY over another category's count
    # (count0 / count1) instead of over the total surveyed (count0 / total). The categorical item
    # is VARIABLE-LENGTH — operands are (mode_code, *category_counts) — so this row uses
    # ``operand_count=None`` to match any arity; the predictor decodes operands[0] and returns
    # ``None`` for any non-relative-frequency mode (so it only ever fires on a relative-frequency
    # item). A wrong OPERATION (a part-to-part ratio where a part-to-whole fraction was asked). The
    # generator emits three categories, so the total always differs from any single count and the
    # match is diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.CATEGORICAL_DATA,
        operand_count=None,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.WRONG_DENOMINATOR,
        predict=wrong_denominator_relative_frequency,
    ),
    # dependent-independent-swap: applied the multiplicative relationship y = a*x as ADDITIVE,
    # computing a + x instead of a*x ("y = 3x at x = 4" -> 7 instead of 12). Operands are (a, x).
    # A wrong OPERATION (the rate was added to the input, not multiplied by it); the generator
    # excludes a = x = 2, so the additive value always differs from the correct product and the
    # match is diagnostic. (Only the SYMBOLIC/NUMERIC surface routes here; the COORDINATE surface's
    # coordinate-swap is classified by _verify_coordinate, not this numeric path.)
    _WrongAnswerModel(
        kc=KnowledgeComponentId.DEPENDENT_VARS,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.DEPENDENT_INDEPENDENT_SWAP,
        predict=lambda ops: add_instead_of_applying_rate(int(ops[0]), int(ops[1])),
    ),
    # solution-substitution-error: solved x + b = c by ADDING b instead of subtracting it (moved
    # the constant without flipping its sign), answering c + b instead of c - b. Operands are
    # (b, c). A wrong OPERATION (the wrong inverse). With b > 0 the value c + b always differs from
    # the correct c - b, so the match is always diagnostic. (Only the SYMBOLIC/NUMERIC solve surface
    # routes here; the NUMBER_LINE yes/no surface is classified by _verify_yes_no, not this path.)
    _WrongAnswerModel(
        kc=KnowledgeComponentId.EQUATION_SOLUTIONS,
        operand_count=2,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.SOLUTION_SUBSTITUTION_ERROR,
        predict=solution_substitution_error,
    ),
    # add-withdrawal-instead-of-subtracting: ADDED a withdrawal to the running balance instead of
    # subtracting it (a sign slip), so the ending balance is too high by twice that withdrawal. The
    # check-register item is VARIABLE-LENGTH — operands are (start, *signed_transactions) — so this
    # row uses ``operand_count=None`` to match any arity; the predictor flips the first withdrawal.
    # A wrong OPERATION (the wrong sign on a withdrawal). The generator always includes a nonzero
    # withdrawal, so the slip always differs from the correct balance and the match is diagnostic.
    # (Only the SYMBOLIC ending-balance surface routes here; the NUMBER_LINE overdraft yes/no
    # surface is classified by _verify_yes_no, not this numeric path.)
    _WrongAnswerModel(
        kc=KnowledgeComponentId.CHECK_REGISTER,
        operand_count=None,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.ADD_WITHDRAWAL_INSTEAD_OF_SUBTRACTING,
        predict=add_withdrawal_instead_of_subtracting,
    ),
    # forgot-multiply-by-years: answered the ANNUAL figure (the salary, or the annual income
    # difference) instead of multiplying by the working years. The lifetime-income item carries a
    # leading MODE flag and has two arities — (0, salary, years) and (1, a, b, years) — so this row
    # uses ``operand_count=None`` to match any arity; the predictor decodes operands[0]. A wrong
    # OPERATION (skipped the × years step). The generator keeps years >= 2, so the un-multiplied
    # value always differs from the correct product and the match is diagnostic.
    _WrongAnswerModel(
        kc=KnowledgeComponentId.LIFETIME_INCOME,
        operand_count=None,
        error_category=ErrorCategory.OPERATION,
        misconception=MisconceptionId.FORGOT_MULTIPLY_BY_YEARS,
        predict=forgot_to_multiply_by_years,
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
        # ``operand_count is None`` matches any arity (variable-length data sets, e.g. the MAD);
        # otherwise the operand count must match exactly so a model never fires on the wrong shape.
        if model.kc is problem.kc and (
            model.operand_count is None or len(operands) == model.operand_count
        ):
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

    if problem.answer_kind is AnswerKind.EXPRESSION:
        return _verify_expression(problem, submitted)

    if problem.answer_kind is AnswerKind.INEQUALITY:
        return _verify_inequality(problem, submitted)

    if problem.answer_kind is AnswerKind.COORDINATE:
        return _verify_coordinate(problem, submitted)

    if problem.answer_kind is AnswerKind.NUMBER_SETS:
        return _verify_number_sets(problem, submitted)

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
