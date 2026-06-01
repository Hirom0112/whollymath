"""Behavioral tests for KC_lifetime_income — Grade-6 Unit 8 (TEKS 6.14H).

Salary & lifetime income: lifetime income = annual salary × working years, and comparing income
across education levels. One of the two SymPy-gradeable financial-literacy KCs (owner decision
DEC.FINLIT); the other four U8 lessons stay concept stubs.

PRIMARY rep — SYMBOLIC scalar (NUMBER_ENTRY): "A job pays $X/year. Over Y years, what is the
lifetime income?" -> X*Y (an integer). A SECOND item MODE on the same numeric surface frames the
education-level COMPARISON: "How much MORE does job A earn than job B over Y years?" -> (A−B)*Y. The
two modes are exact integer arithmetic (SymPy decides; CLAUDE.md §8.2). The KC advertises SYMBOLIC +
WORD_PROBLEM (the ≥2-rep contract); like KC_unit_rate it is PRACTICE-ONLY (live only on SYMBOLIC),
so errors route to SYMBOLIC (a rep WITH a surface state), never to WORD_PROBLEM.

The modeled misconception is forgetting to multiply by the YEARS — answering the annual salary (or
the annual difference) itself, the headline "lifetime income" mistake the lesson is built to catch.

Every assertion runs through the SAME oracle the tutor uses (the SymPy verifier). Mandatory-TDD
domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.lesson_spec import WidgetId, widget_for_representation
from app.domain.misconceptions import (
    MisconceptionId,
    forgot_to_multiply_by_years,
)
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.LIFETIME_INCOME


def _problem(seed: int, surface: Representation | None = None) -> Problem:
    return generate_problem(_KC, seed, surface)


def test_lifetime_income_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it — and so u8_l6
    ("Salary & lifetime income") goes live (repointed from the stale KC_income string)."""
    assert _KC in LIVE_KCS


def test_u8_l6_repointed_to_lifetime_income() -> None:
    """u8_l6 references KC_lifetime_income (the live enum member), and NO lesson references the
    stale KC_income string anymore."""
    from app.domain.curriculum import all_units

    lessons = [lesson for unit in all_units() for lesson in unit.lessons]
    u8_l6 = next(lesson for lesson in lessons if lesson.slug == "u8_l6")
    assert u8_l6.kc_id == "KC_lifetime_income"
    assert all(lesson.kc_id != "KC_income" for lesson in lessons)


# ─── The lifetime-income scalar (SYMBOLIC, NUMBER_ENTRY) ─────────────────────


def test_lifetime_income_is_a_numeric_scalar_item() -> None:
    """The default SYMBOLIC surface yields a NUMERIC integer item."""
    problem = _problem(3, Representation.SYMBOLIC)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.surface_format is Representation.SYMBOLIC
    assert problem.correct_value.q == 1  # an integer number of dollars


def test_lifetime_income_routes_to_number_entry_not_fraction_editor() -> None:
    """A whole-dollar answer goes in the single-box NUMBER_ENTRY, not the two-box fraction editor
    (it must NOT be in _FRACTION_ANSWER_KCS)."""
    assert widget_for_representation(Representation.SYMBOLIC, _KC) is WidgetId.NUMBER_ENTRY


def test_correct_value_grades_via_the_oracle() -> None:
    """The lifetime income / income difference grades correct through the tutor's own oracle for
    every seed (both item modes)."""
    for seed in range(0, 40):
        problem = _problem(seed, Representation.SYMBOLIC)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_both_item_modes_appear() -> None:
    """Across seeds the generator produces BOTH the lifetime-income mode and the income-COMPARISON
    mode (a richer, diagnostic lesson), distinguishable by the leading mode flag in operands."""
    modes = set()
    for seed in range(0, 40):
        problem = _problem(seed, Representation.SYMBOLIC)
        assert problem.operands is not None
        modes.add(int(problem.operands[0]))
    assert modes == {0, 1}, f"both item modes must appear, saw {modes}"


def test_forgetting_years_is_classified() -> None:
    """Answering the annual salary (or the annual difference) — forgetting to multiply by the YEARS
    — is flagged OPERATION + the forgot-multiply-by-years misconception, the headline lifetime
    mistake. The slip is always DISTINCT from the correct value (years >= 2)."""
    for seed in range(0, 40):
        problem = _problem(seed, Representation.SYMBOLIC)
        assert problem.operands is not None
        wrong = forgot_to_multiply_by_years(problem.operands)
        assert wrong is not None
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.FORGOT_MULTIPLY_BY_YEARS


# ─── Representations: practice-only, ≥2 advertised ───────────────────────────


def test_practice_only_symbolic_live_word_problem_advertised() -> None:
    """SYMBOLIC is the only LIVE answer surface (practice-only, like KC_unit_rate); WORD_PROBLEM is
    advertised for the ≥2-rep contract but is not a live answer surface (and never an error target).
    """
    assert live_representations(_KC) == (Representation.SYMBOLIC,)
    from app.domain.knowledge_components import get_kc

    assert set(get_kc(_KC).representations) == {
        Representation.SYMBOLIC,
        Representation.WORD_PROBLEM,
    }


# ─── Robustness + reproducibility ────────────────────────────────────────────


def test_unparseable_submissions_are_wrong_not_a_crash() -> None:
    """Garbled input grades wrong, never raises (CLAUDE.md §8.2)."""
    problem = _problem(1, Representation.SYMBOLIC)
    for junk in ("", "abc", "$", "/"):
        result = verify(problem, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    first = generate_problem(_KC, 42, Representation.SYMBOLIC)
    second = generate_problem(_KC, 42, Representation.SYMBOLIC)
    assert first.correct_value == second.correct_value
    assert first.statement == second.statement


def test_worked_example_lands_on_the_value() -> None:
    """The worked example lands on the correct lifetime income / difference."""
    problem = _problem(3, Representation.SYMBOLIC)
    assert worked_example_for(problem).final_value == problem.correct_value


def test_nudge_bank_covers_lifetime_income() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
