"""Behavioral tests for KC_data_displays — a Grade-6 (Unit 7) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope data-display item over a small data set described
textually in the prompt (count-above-a-threshold / most-frequent-value / bin-frequency,
behind a display-question flag carried in operands[0]); the verifier confirms the
SymPy-exact answer and classifies the distinct-value-count misconception (counting how
many DIFFERENT values are above the threshold instead of how many DATA POINTS are); the
worked example lands on the answer; and generation is deterministic (PROJECT.md §4.1).
Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: CCSS 6.SP.4 — display numerical data
on dot plots / histograms, and read them.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import (
    DATA_DISPLAY_QUESTION_CODE,
    MisconceptionId,
    distinct_value_count,
)
from app.domain.problem_generators import (
    _DATA_DISPLAY_QUESTION_CODE,
    AnswerKind,
    Problem,
    generate_problem,
)
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.DATA_DISPLAYS
_COUNT_ABOVE_CODE = _DATA_DISPLAY_QUESTION_CODE["count_above"]


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_data_displays_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_item_is_a_clean_in_scope_problem() -> None:
    """A numeric item whose operands are (question_code, param, *data) over a small data set."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None
    question_code, _param, *data = problem.operands
    assert question_code in set(_DATA_DISPLAY_QUESTION_CODE.values())
    assert 4 <= len(data) <= 9
    assert all(v.q == 1 for v in data)  # whole-number data values
    assert problem.correct_value.q == 1  # the answer is a count or a value (whole number)


def test_correct_answer_verifies_correct() -> None:
    """The SymPy-exact answer is graded correct by the tutor's own oracle, all question types."""
    for seed in range(1, 80):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct, f"seed={seed} statement={problem.statement!r}"
        assert result.error_category is ErrorCategory.NONE


def test_all_three_question_types_are_generated() -> None:
    """Across seeds the generator produces count-above, most-frequent, AND bin-frequency items."""
    codes = {int(_problem(s).operands[0]) for s in range(1, 100)}  # type: ignore[index]
    assert codes == set(_DATA_DISPLAY_QUESTION_CODE.values())


def test_count_above_counts_all_data_points() -> None:
    """A spot check: a count-above item's answer is the count of ALL data points above threshold.

    (Not distinct values — that is the modeled misconception, asserted separately below.)
    """
    for seed in range(1, 120):
        problem = _problem(seed)
        if int(problem.operands[0]) != _COUNT_ABOVE_CODE:  # type: ignore[index]
            continue
        threshold = problem.operands[1]  # type: ignore[index]
        data = problem.operands[2:]  # type: ignore[index]
        expected = sum(1 for v in data if v > threshold)
        assert problem.correct_value == expected
        break
    else:  # pragma: no cover
        raise AssertionError("no count-above item produced in seed range")


def test_distinct_value_count_is_classified() -> None:
    """Counting DISTINCT values above the threshold is flagged OPERATION + the misconception.

    Routed to OPERATION (a wrong PROCEDURE): the learner counts how many DIFFERENT values lie
    above the threshold instead of how many DATA POINTS do — collapsing duplicate dots into one.
    The generator guarantees, for the count-above items it exercises, at least one duplicated value
    above the threshold, so the distinct count differs from the true count (so it is diagnostic).
    """
    seen = 0
    for seed in range(1, 200):
        problem = _problem(seed)
        if int(problem.operands[0]) != _COUNT_ABOVE_CODE:  # type: ignore[index]
            continue
        wrong = distinct_value_count(problem.operands)  # type: ignore[arg-type]
        if wrong is None or wrong == problem.correct_value:
            continue  # only the diagnostic count-above items carry the misconception
        seen += 1
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.DISTINCT_VALUE_COUNT
        if seen >= 3:
            break
    assert seen >= 1, "no diagnostic count-above item produced — the misconception is untested"


def test_distinct_value_count_returns_none_for_other_question_types() -> None:
    """The misconception is count-above-specific: it does not fire on mode/bin items."""
    for seed in range(1, 120):
        problem = _problem(seed)
        if int(problem.operands[0]) == _COUNT_ABOVE_CODE:  # type: ignore[index]
            continue
        assert distinct_value_count(problem.operands) is None  # type: ignore[arg-type]


def test_count_above_always_has_a_duplicate_above_threshold() -> None:
    """Every count-above item is diagnostic: the distinct count differs from the true count."""
    for seed in range(1, 120):
        problem = _problem(seed)
        if int(problem.operands[0]) != _COUNT_ABOVE_CODE:  # type: ignore[index]
            continue
        wrong = distinct_value_count(problem.operands)  # type: ignore[arg-type]
        assert wrong is not None
        assert wrong != problem.correct_value


def test_question_code_maps_agree() -> None:
    """The generator re-exports the canonical misconceptions code map (single source of truth)."""
    assert _DATA_DISPLAY_QUESTION_CODE == DATA_DISPLAY_QUESTION_CODE


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in range(1, 60):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value, f"seed={seed}"


def test_nudge_bank_covers_data_displays() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
