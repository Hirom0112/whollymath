"""Behavioral tests for KC_summary_statistics — a Grade-6 (Unit 7) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope summary-statistic item over a small data set
(mean / median / mode / range, behind a stat-mode flag carried in operands[0]); the
verifier confirms the SymPy-exact statistic and classifies the median-without-sorting
misconception (taking the middle of the UNSORTED list); the worked example lands on the
answer; and generation is deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1
(CLAUDE.md §2). Skill: CCSS 6.SP.3 — summarize a data set with a single number.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, unsorted_middle
from app.domain.problem_generators import (
    _SUMMARY_STAT_MODE_CODE,
    AnswerKind,
    Problem,
    generate_problem,
)
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.SUMMARY_STATISTICS
_MEDIAN_CODE = _SUMMARY_STAT_MODE_CODE["median"]


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_summary_statistics_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_item_is_a_clean_in_scope_problem() -> None:
    """A numeric item whose operands are (mode_code, *data) over a small data set."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None
    # operands[0] is the stat-mode sentinel; the rest is the data set.
    mode_code, *data = problem.operands
    assert mode_code in set(_SUMMARY_STAT_MODE_CODE.values())
    assert 3 <= len(data) <= 6
    assert all(v.q == 1 for v in data)  # whole-number data values


def test_correct_statistic_verifies_correct() -> None:
    """The SymPy-exact statistic is graded correct by the tutor's own oracle, all modes."""
    for seed in range(1, 60):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct, f"seed={seed} statement={problem.statement!r}"
        assert result.error_category is ErrorCategory.NONE


def test_all_four_modes_are_generated() -> None:
    """Across seeds the generator produces mean, median, mode, AND range items."""
    modes = {int(_problem(s).operands[0]) for s in range(1, 80)}  # type: ignore[index]
    assert modes == set(_SUMMARY_STAT_MODE_CODE.values())


def test_mean_can_be_fractional() -> None:
    """At least one mean item has a non-integer (Rational) answer — exact, not rounded."""
    fractional = []
    for seed in range(1, 200):
        problem = _problem(seed)
        if int(problem.operands[0]) == _SUMMARY_STAT_MODE_CODE["mean"]:  # type: ignore[index]
            if problem.correct_value.q != 1:
                fractional.append(problem.correct_value)
    assert fractional, "no fractional mean produced — the exact-Rational mean is untested"


def test_mean_equals_sum_over_count() -> None:
    """A spot check: a mean item's answer equals SymPy sum(data) / len(data)."""
    for seed in range(1, 120):
        problem = _problem(seed)
        if int(problem.operands[0]) == _SUMMARY_STAT_MODE_CODE["mean"]:  # type: ignore[index]
            data = problem.operands[1:]  # type: ignore[index]
            assert problem.correct_value == sum(data, Rational(0)) / len(data)
            break
    else:  # pragma: no cover
        raise AssertionError("no mean item produced in seed range")


def test_range_equals_max_minus_min() -> None:
    """A spot check: a range item's answer equals max(data) - min(data)."""
    for seed in range(1, 120):
        problem = _problem(seed)
        if int(problem.operands[0]) == _SUMMARY_STAT_MODE_CODE["range"]:  # type: ignore[index]
            data = problem.operands[1:]  # type: ignore[index]
            assert problem.correct_value == max(data) - min(data)
            break
    else:  # pragma: no cover
        raise AssertionError("no range item produced in seed range")


def test_median_without_sorting_is_classified() -> None:
    """Taking the middle of the UNSORTED data is flagged OPERATION + the misconception.

    Routed to OPERATION (a wrong PROCEDURE): the learner skipped the SORT step and read the
    middle of the list as given. The generator guarantees, for the median items it exercises,
    that the unsorted middle differs from the true (sorted) median, so the error is diagnostic.
    """
    seen = 0
    for seed in range(1, 200):
        problem = _problem(seed)
        if int(problem.operands[0]) != _MEDIAN_CODE:  # type: ignore[index]
            continue
        wrong = unsorted_middle(problem.operands)  # type: ignore[arg-type]
        if wrong is None or wrong == problem.correct_value:
            continue  # only the diagnostic median items carry the misconception
        seen += 1
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.MEDIAN_WITHOUT_SORTING
        if seen >= 3:
            break
    assert seen >= 1, "no diagnostic median item produced — the misconception is untested"


def test_unsorted_middle_returns_none_for_non_median_modes() -> None:
    """The misconception is median-specific: it does not fire on mean/mode/range items."""
    for seed in range(1, 120):
        problem = _problem(seed)
        if int(problem.operands[0]) == _MEDIAN_CODE:  # type: ignore[index]
            continue
        assert unsorted_middle(problem.operands) is None  # type: ignore[arg-type]


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in range(1, 40):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value, f"seed={seed}"


def test_nudge_bank_covers_summary_statistics() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
