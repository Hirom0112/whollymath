"""Tests for the Layer-1 SymPy answer verifier (Slice 1.4).

Written test-first per CLAUDE.md §2 — TDD is MANDATORY for the domain model and
"every SymPy verifier gets a test before the implementation." The verifier is the
one thing in the system that decides "is this answer correct?" (PROJECT.md §3.10,
ARCHITECTURE.md §9, §14 invariant 2): SymPy decides, never an LLM, never a
heuristic. These tests pin that contract and the wrong-answer classification the
policy routes on.

What these tests assert:

  - a correct numeric answer verifies True with ``error_category == none`` and no
    matched misconception, for EVERY procedural KC (the five §3.1 KCs);
  - the submitted answer may be an ``"a/b"`` string, an ``int``, or a ``Rational``
    — all parse to the same SymPy ``Rational`` and SymPy decides equality;
  - a wrong answer is CLASSIFIED by matching it against the misconception
    generators on the problem's operands, into the §3.6 routing categories:
      * add-across on an addition problem  -> operation  (routes to S3, §3.6);
      * subtract-across on a subtraction   -> operation  (S3, §3.6);
      * number-line bias position          -> magnitude  (routes to S2, §3.6);
  - any other wrong answer is ``other`` (no invented routing — CLAUDE.md §12);
  - cross-checked against the SymPy-verified ``diagnostic_gems.json`` oracle for
    correct answers and the bank's ``wrong_answer_produced`` values, skipped if the
    bank is absent (mirrors the other domain tests — no hard dep on a data asset).

SymPy IS allowed here (this is ``domain/`` — CLAUDE.md §7, ARCHITECTURE.md §14
invariant 5). No LLM, no DB. The §3.6 categories are the SAME string values as the
api ``ErrorType`` enum so the API can import the domain enum later.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import (
    MisconceptionId,
    add_across,
    natural_number_bias_number_line,
    subtract_across,
)
from app.domain.problem_generators import (
    AnswerKind,
    Problem,
    generate_problem,
    problem_from_bank_item,
)
from app.domain.verifier import ErrorCategory, VerificationResult, verify
from sympy import Rational

ALL_KCS = (
    KnowledgeComponentId.EQUIVALENCE,
    KnowledgeComponentId.COMMON_DENOMINATOR,
    KnowledgeComponentId.ADDITION_UNLIKE,
    KnowledgeComponentId.SUBTRACTION_UNLIKE,
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
)

_GEMS_PATH = Path(__file__).resolve().parents[2] / "app" / "domain" / "diagnostic_gems.json"


def _load_items() -> list[dict[str, Any]]:
    """Load the gem-bank items; skip the bank cross-checks if the bank is absent.

    The domain layer's tests must not hard-depend on a downstream data asset
    (mirrors test_problem_generators.py / test_misconceptions.py), so the
    bank cross-checks skip when the bank is not on disk rather than failing.
    """
    if not _GEMS_PATH.exists():
        pytest.skip("diagnostic_gems.json not present — bank cross-checks skipped")
    data = json.loads(_GEMS_PATH.read_text())
    items: list[dict[str, Any]] = list(data["items"])
    return items


# ─── ErrorCategory: the canonical domain enum aligned with the api ──────────


def test_error_category_values_match_api_error_type() -> None:
    """The domain ErrorCategory values are exactly the api ErrorType strings.

    The domain enum is the source of truth the API imports later (the api
    ``ErrorType`` placeholder must be replaceable by ``ErrorCategory`` without a
    value change). If these drift, the policy that routes on the error string
    (PROJECT.md §3.6) breaks at the API boundary.
    """
    assert {c.value for c in ErrorCategory} == {
        "none",
        "magnitude",
        "operation",
        "format",
        "other",
    }


# ─── Correct answers verify True with category=none ─────────────────────────


@pytest.mark.parametrize("kc", ALL_KCS)
@pytest.mark.parametrize("seed", range(10))
def test_correct_answer_for_every_kc_verifies_true(kc: KnowledgeComponentId, seed: int) -> None:
    """The SymPy-computed correct answer of each KC's generator verifies True.

    Correctness is decided by SymPy equality against ``problem.correct_value`` —
    the same oracle the generator used to build the problem. A correct answer is
    ``error_category == none`` and matches no misconception.
    """
    problem = generate_problem(kc, seed=seed)
    result = verify(problem, problem.correct_value)
    assert result.is_correct is True
    assert result.error_category is ErrorCategory.NONE
    assert result.matched_misconception is None


def test_result_is_immutable() -> None:
    """VerificationResult is frozen — a verdict is a fact, not mutable state."""
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=1)
    result = verify(problem, problem.correct_value)
    with pytest.raises(AttributeError):
        result.is_correct = False  # type: ignore[misc]


# ─── Submitted-answer parsing: string / int / Rational all accepted ─────────


def test_correct_answer_accepts_a_b_string_form() -> None:
    """An "a/b" string submission parses to a Rational and SymPy decides equality."""
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=2)
    value = problem.correct_value
    submitted = f"{value.p}/{value.q}"
    assert verify(problem, submitted).is_correct is True


def test_correct_answer_accepts_unreduced_string_form() -> None:
    """An equivalent but unreduced "a/b" string is correct — SymPy reduces it.

    A learner who writes 2/4 for the answer 1/2 is correct: SymPy equality is on
    VALUE, not on the written form. (The verifier judges magnitude; representation
    nuances like "must be in lowest terms" are not in §3.1 scope.)
    """
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=2)
    value = problem.correct_value
    unreduced = f"{value.p * 2}/{value.q * 2}"
    assert verify(problem, unreduced).is_correct is True


def test_integer_answer_accepts_int_and_string() -> None:
    """A whole-number answer (common denominator) verifies from an int or a string."""
    problem = generate_problem(KnowledgeComponentId.COMMON_DENOMINATOR, seed=4)
    integer_value = int(problem.correct_value)
    assert verify(problem, integer_value).is_correct is True
    assert verify(problem, str(integer_value)).is_correct is True


def test_rational_answer_accepts_rational_object() -> None:
    """A SymPy Rational submission is accepted directly."""
    problem = generate_problem(KnowledgeComponentId.SUBTRACTION_UNLIKE, seed=5)
    assert verify(problem, problem.correct_value).is_correct is True


def test_unparseable_submission_is_wrong_and_other() -> None:
    """A submission that is not a number at all is wrong, category=other.

    Garbage in is not "correct"; SymPy cannot parse it to a magnitude, so it
    cannot match any misconception value — there is no defensible routing, so
    ``other`` (CLAUDE.md §12: do not invent a routing).
    """
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=2)
    result = verify(problem, "not a fraction")
    assert result.is_correct is False
    assert result.error_category is ErrorCategory.OTHER
    assert result.matched_misconception is None


def test_zero_denominator_submission_is_wrong_and_other() -> None:
    """A submission with a zero denominator is an impossible value, not a crash.

    The verifier must never raise on learner input; an undefined magnitude (n/0)
    cannot equal the answer and cannot be matched, so it is wrong and ``other``.
    """
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=2)
    result = verify(problem, "1/0")
    assert result.is_correct is False
    assert result.error_category is ErrorCategory.OTHER


# ─── Wrong-answer classification (PROJECT.md §3.6 routing) ───────────────────


@pytest.mark.parametrize("seed", range(10))
def test_add_across_wrong_answer_classifies_as_operation(seed: int) -> None:
    """add-across on an addition problem -> operation (routes to S3, §3.6).

    The add-across error (tops+tops / bottoms+bottoms) is an OPERATION error: the
    learner ran the wrong procedure. §3.6 routes operation/format errors to S3
    (fraction bars), where part-manipulation makes the operation visible.
    """
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=seed)
    assert problem.operands is not None
    a, b = problem.operands
    wrong = add_across(a.p, a.q, b.p, b.q).as_rational()
    result = verify(problem, wrong)
    assert result.is_correct is False
    assert result.error_category is ErrorCategory.OPERATION
    assert result.matched_misconception is MisconceptionId.ADD_ACROSS_ERROR


@pytest.mark.parametrize("seed", range(10))
def test_subtract_across_wrong_answer_classifies_as_operation(seed: int) -> None:
    """subtract-across on a subtraction problem -> operation (S3, §3.6).

    Operating on the parts separately in subtraction is the same wrong-procedure
    family; misconceptions.py labels it natural-number-bias (a citation-honesty
    choice). It is an operation error and routes to S3.
    """
    problem = generate_problem(KnowledgeComponentId.SUBTRACTION_UNLIKE, seed=seed)
    assert problem.operands is not None
    minuend, subtrahend = problem.operands
    wrong = subtract_across(minuend.p, minuend.q, subtrahend.p, subtrahend.q).as_rational()
    result = verify(problem, wrong)
    # subtract-across can coincide with the correct value only for unlike pairs that
    # never occur here (the generators guarantee unlike denominators), so this is a
    # genuine wrong answer for every seed.
    assert result.is_correct is False
    assert result.error_category is ErrorCategory.OPERATION
    assert result.matched_misconception is MisconceptionId.NATURAL_NUMBER_BIAS


@pytest.mark.parametrize("seed", range(10))
def test_number_line_bias_wrong_answer_classifies_as_magnitude(seed: int) -> None:
    """number-line bias position -> magnitude (routes to S2, §3.6).

    Reading the denominator as a whole-number position is a MAGNITUDE error — the
    learner misjudged how big the fraction is. §3.6 routes magnitude errors to S2
    (the number line), the representation that exposes magnitude.
    """
    problem = generate_problem(KnowledgeComponentId.NUMBER_LINE_PLACEMENT, seed=seed)
    assert problem.operands is not None
    (target,) = problem.operands
    biased = natural_number_bias_number_line(target.p, target.q).biased_position
    result = verify(problem, biased)
    assert result.is_correct is False
    assert result.error_category is ErrorCategory.MAGNITUDE
    assert result.matched_misconception is MisconceptionId.NATURAL_NUMBER_BIAS


@pytest.mark.parametrize("seed", range(10))
def test_random_wrong_answer_classifies_as_other(seed: int) -> None:
    """A wrong answer matching no misconception generator is ``other``.

    We do not invent a routing for an unrecognized error (CLAUDE.md §12). A value
    that is neither the correct answer nor any modeled misconception's output is
    wrong with category ``other`` and no matched misconception.
    """
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=seed)
    # A deliberately off value: the correct answer plus 100 cannot be any in-scope
    # fraction sum nor the add-across value (which is < either addend).
    wrong = problem.correct_value + 100
    result = verify(problem, wrong)
    assert result.is_correct is False
    assert result.error_category is ErrorCategory.OTHER
    assert result.matched_misconception is None


def test_wrong_answer_on_equivalence_is_other() -> None:
    """A wrong equivalence answer has no §3.6-mapped misconception -> other.

    The task scope maps add-across, subtract-across, and number-line bias to a
    category; equivalence/common-denominator wrong answers are not in that map, so
    a wrong value there is ``other`` rather than an invented routing (CLAUDE.md §12).
    """
    problem = generate_problem(KnowledgeComponentId.EQUIVALENCE, seed=1)
    wrong = problem.correct_value + Rational(1, 7)
    result = verify(problem, wrong)
    assert result.is_correct is False
    assert result.error_category is ErrorCategory.OTHER
    assert result.matched_misconception is None


# ─── Cross-check against the SymPy-verified gem bank (skip-if-absent) ────────


def test_bank_fraction_items_correct_answers_verify_true() -> None:
    """Every bank fraction/point item's correct answer verifies True.

    Cross-checks the verifier against the bank's SymPy-verified oracle: the
    handpicked correct answer of each numeric item must pass the verifier, just as
    a generated correct answer does (decision 0.D.1 — one shared Problem type).
    """
    items = _load_items()
    checked = 0
    for item in items:
        if item["correct_answer"]["type"] not in ("fraction", "point_on_unit_interval"):
            continue
        problem = problem_from_bank_item(item)
        result = verify(problem, problem.correct_value)
        assert result.is_correct is True, f"{item['id']} correct answer failed to verify"
        assert result.error_category is ErrorCategory.NONE
        checked += 1
    assert checked > 0, "expected at least one fraction/point bank item to cross-check"


def test_bank_add_across_wrong_answers_classify_as_operation() -> None:
    """Bank ADD items' ``wrong_answer_produced`` classify as add-across/operation.

    The bank records the SymPy-computed wrong answer for the add-across probe on
    each addition item (e.g. ADD-001: 1/2+1/4 -> 2/6). Feeding that exact value to
    the verifier must reproduce the operation/add-across classification — the
    strongest possible check that classification matches the research oracle.
    """
    items = _load_items()
    checked = 0
    for item in items:
        if item["kc_primary"] != KnowledgeComponentId.ADDITION_UNLIKE.value:
            continue
        problem = problem_from_bank_item(item)
        if problem.operands is None or len(problem.operands) != 2:
            continue
        for probe in item.get("misconceptions_probed", []):
            if probe["name"] != MisconceptionId.ADD_ACROSS_ERROR.value:
                continue
            raw = str(probe["wrong_answer_produced"])
            result = verify(problem, raw)
            assert result.is_correct is False, f"{item['id']}: {raw} unexpectedly correct"
            assert result.error_category is ErrorCategory.OPERATION, item["id"]
            assert result.matched_misconception is MisconceptionId.ADD_ACROSS_ERROR
            checked += 1
    assert checked > 0, "expected at least one ADD item with an add-across probe"


def test_bank_subtract_across_wrong_answers_classify_as_operation() -> None:
    """Bank SUB items' parseable ``wrong_answer_produced`` classify as operation.

    SUB items record the natural-number-bias subtract-across wrong answer as a raw
    "a/b" form (e.g. SUB-001: 1/2-1/4 -> 0/2; SUB-003 -> 1/-3). Where the raw form
    is a parseable fraction, the verifier must classify it operation/
    natural-number-bias. (Forms with a zero/negative denominator are kept raw by the
    bank as the diagnostic tell; SymPy parses a negative denominator to a negative
    value, and a zero denominator is skipped as an impossible magnitude.)
    """
    items = _load_items()
    checked = 0
    for item in items:
        if item["kc_primary"] != KnowledgeComponentId.SUBTRACTION_UNLIKE.value:
            continue
        problem = problem_from_bank_item(item)
        if problem.operands is None or len(problem.operands) != 2:
            continue
        minuend, subtrahend = problem.operands
        expected = subtract_across(minuend.p, minuend.q, subtrahend.p, subtrahend.q)
        if expected.denominator == 0:
            continue  # n/0 is undefined; the bank keeps it raw as the tell
        result = verify(problem, expected.as_rational())
        assert result.is_correct is False, item["id"]
        assert result.error_category is ErrorCategory.OPERATION, item["id"]
        assert result.matched_misconception is MisconceptionId.NATURAL_NUMBER_BIAS
        checked += 1
    assert checked > 0, "expected at least one SUB item to cross-check"


def test_verification_result_carries_the_three_fields() -> None:
    """A VerificationResult exposes is_correct, error_category, matched_misconception."""
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=1)
    result = verify(problem, problem.correct_value)
    assert isinstance(result, VerificationResult)
    assert isinstance(result.is_correct, bool)
    assert isinstance(result.error_category, ErrorCategory)
    assert result.matched_misconception is None or isinstance(
        result.matched_misconception, MisconceptionId
    )


def test_problem_carries_an_answer_kind_defaulting_to_numeric() -> None:
    """The Problem type now carries ``answer_kind`` to distinguish a numeric answer
    from a yes/no relational judgment (the formerly-deferred Slice 1.4 extension).

    The default is NUMERIC, so every existing generator/bank item is unchanged: a
    yes/no item opts in explicitly. The truth of a yes/no item is still computed from
    SymPy over the operands (no separate stored answer), so the verifier — not a
    stored string — decides correctness (ARCHITECTURE.md §9, §14 invariant 2).
    """
    fields = Problem.__dataclass_fields__
    assert "answer_kind" in fields
    # Numeric is the default — a generated problem opts into yes/no, nothing else changes.
    assert generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=1).answer_kind is (
        AnswerKind.NUMERIC
    )


# ───────────────── yes/no relational judgments (formerly deferred) ─────────────────


def _yes_no_equivalence(first: Rational, second: Rational) -> Problem:
    """A yes/no equivalence probe — 'Is `first` the same amount as `second`?'. The
    truth is `first == second` (SymPy); the verifier computes it from the operands."""
    return Problem(
        problem_id=f"YESNO-{first}-{second}",
        kc=KnowledgeComponentId.EQUIVALENCE,
        surface_format=Representation.SYMBOLIC,
        statement=f"Is {first} the same amount as {second}?",
        correct_value=first,
        representations_available=(Representation.SYMBOLIC,),
        operands=(first, second),
        answer_kind=AnswerKind.YES_NO,
    )


def test_yes_no_correct_when_the_judgment_matches_sympy() -> None:
    """For equal operands the true answer is YES; for unequal it is NO. SymPy decides
    the equality, the verifier maps the learner's yes/no onto it."""
    equal = _yes_no_equivalence(Rational(2, 3), Rational(4, 6))  # truly equal
    unequal = _yes_no_equivalence(Rational(1, 2), Rational(1, 3))  # truly unequal

    assert verify(equal, "yes").is_correct is True
    assert verify(equal, "no").is_correct is False
    assert verify(unequal, "no").is_correct is True
    assert verify(unequal, "yes").is_correct is False


def test_yes_no_accepts_case_and_whitespace_variants() -> None:
    """A kid's 'Yes', ' YES ', 'no' all parse — the verifier normalizes the answer."""
    equal = _yes_no_equivalence(Rational(2, 3), Rational(4, 6))
    for yes in ("yes", "Yes", " YES ", "YES"):
        assert verify(equal, yes).is_correct is True
    for no in ("no", "No", " NO "):
        assert verify(equal, no).is_correct is False


def test_yes_no_wrong_answer_is_a_magnitude_error() -> None:
    """A wrong equivalence judgment means the learner misjudged whether the amounts
    match — a MAGNITUDE error, which §3.6 routes to the number line (S2). We do not
    over-claim a specific misconception match."""
    equal = _yes_no_equivalence(Rational(2, 3), Rational(4, 6))
    wrong = verify(equal, "no")
    assert wrong.is_correct is False
    assert wrong.error_category is ErrorCategory.MAGNITUDE
    assert wrong.matched_misconception is None


def test_yes_no_unparseable_answer_is_wrong_never_crashes() -> None:
    """The verifier must never crash on what a kid types. A non-yes/no string on a
    yes/no item is simply wrong (OTHER), like an unparseable numeric answer."""
    equal = _yes_no_equivalence(Rational(2, 3), Rational(4, 6))
    for junk in ("maybe", "", "2/3", "idk"):
        result = verify(equal, junk)
        assert result.is_correct is False
        assert result.error_category is ErrorCategory.OTHER


def _yes_no_comparison(first: Rational, second: Rational) -> Problem:
    """A magnitude comparison — 'Is `first` greater than `second`?' — the symbolic
    representation of the number-line placement KC. Truth is `first > second`."""
    return Problem(
        problem_id=f"CMP-{first}-{second}",
        kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        surface_format=Representation.SYMBOLIC,
        statement=f"Is {first} greater than {second}?",
        correct_value=first,
        representations_available=(Representation.SYMBOLIC,),
        operands=(first, second),
        answer_kind=AnswerKind.YES_NO,
        yes_no_relation="greater",
    )


def test_yes_no_greater_relation_uses_comparison_not_equality() -> None:
    """A 'greater' yes/no judges first > second (not equality) — so the SAME yes/no
    machinery serves a magnitude comparison. SymPy decides the order."""
    bigger = _yes_no_comparison(Rational(3, 5), Rational(1, 2))  # 3/5 > 1/2 → YES
    smaller = _yes_no_comparison(Rational(1, 3), Rational(1, 2))  # 1/3 > 1/2 → NO
    assert verify(bigger, "yes").is_correct is True
    assert verify(bigger, "no").is_correct is False
    assert verify(smaller, "no").is_correct is True
    assert verify(smaller, "yes").is_correct is False


def test_equal_operands_are_not_greater() -> None:
    """Equal amounts are not 'greater than' each other → the answer is NO."""
    equal = _yes_no_comparison(Rational(1, 2), Rational(2, 4))  # equal value, unlike denoms
    assert verify(equal, "no").is_correct is True
    assert verify(equal, "yes").is_correct is False
