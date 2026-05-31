"""Behavioral tests for KC_categorical_data — a Grade-6 (Unit 7, TEKS 6.12D) lesson (2026-05-30).

Exercises the KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope categorical-summary item (read counts from a
category breakdown and compute a summary — count-difference, total, or relative
frequency); the verifier confirms the correct summary and classifies the
wrong-denominator misconception (a relative-frequency error: dividing by another
category's count instead of the total); the worked example lands on the answer; and
generation is deterministic (PROJECT.md §4.1). The summary is computed EXACTLY as a
SymPy ``Rational`` (relative frequencies are fractions). Mandatory-TDD domain Layer 1
(CLAUDE.md §2). Skill: TEKS 6.12D — summarize categorical data.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import (
    CATEGORICAL_MODE_CODE,
    MisconceptionId,
    wrong_denominator_relative_frequency,
)
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.CATEGORICAL_DATA


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_categorical_data_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_advertises_symbolic_and_a_second_representation() -> None:
    """LessonSpec requires >=2 advertised reps; the second is the AREA_MODEL bar picture."""
    advertised = generate_problem(_KC, 1).representations_available
    assert Representation.SYMBOLIC in advertised
    assert Representation.AREA_MODEL in advertised
    assert len(advertised) >= 2


def test_generated_item_is_clean_and_in_scope() -> None:
    """The generator yields a numeric item: operands = (mode_code, *category_counts), counts > 0."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None
    mode_code, *counts = problem.operands
    assert int(mode_code) in set(CATEGORICAL_MODE_CODE.values())
    assert len(counts) >= 2  # a category breakdown has at least two categories
    assert all(c > 0 for c in counts)


def test_correct_summary_verifies_correct() -> None:
    """The correct summary value is graded correct by the tutor's own oracle, across modes/seeds."""
    for seed in range(1, 40):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_all_three_modes_are_generated() -> None:
    """Across seeds all three item modes appear (count-difference, total, relative-frequency)."""
    seen = set()
    for seed in range(1, 80):
        problem = _problem(seed)
        assert problem.operands is not None
        seen.add(int(problem.operands[0]))
    assert seen == set(CATEGORICAL_MODE_CODE.values())


def test_relative_frequency_is_an_exact_fraction() -> None:
    """A relative-frequency item's answer is category/total, kept exact (a SymPy Rational)."""
    rel_code = CATEGORICAL_MODE_CODE["relative_frequency"]
    for seed in range(1, 200):
        problem = _problem(seed)
        assert problem.operands is not None
        if int(problem.operands[0]) == rel_code:
            counts = [int(c) for c in problem.operands[1:]]
            assert problem.correct_value == Rational(counts[0], sum(counts))
            return
    raise AssertionError("no relative-frequency item produced in seed range")


def test_wrong_denominator_is_classified() -> None:
    """Dividing by another category's count (not the total) is flagged OPERATION + misconception.

    Relative-frequency-specific: the learner forms category0 / category1 instead of
    category0 / total. The misconception generator returns ``None`` on non-relative-frequency
    items (so the model never fires there); on a relative-frequency item the generator guarantees
    the wrong denominator differs from the total, so the match is diagnostic.
    """
    rel_code = CATEGORICAL_MODE_CODE["relative_frequency"]
    checked = 0
    for seed in range(1, 200):
        problem = _problem(seed)
        assert problem.operands is not None
        if int(problem.operands[0]) != rel_code:
            continue
        wrong = wrong_denominator_relative_frequency(problem.operands)
        assert wrong is not None
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.WRONG_DENOMINATOR
        checked += 1
        if checked >= 5:
            break
    assert checked >= 1


def test_wrong_denominator_model_skips_non_relative_items() -> None:
    """On a count-difference / total item the misconception generator returns None (won't fire)."""
    rel_code = CATEGORICAL_MODE_CODE["relative_frequency"]
    checked = 0
    for seed in range(1, 200):
        problem = _problem(seed)
        assert problem.operands is not None
        if int(problem.operands[0]) == rel_code:
            continue
        assert wrong_denominator_relative_frequency(problem.operands) is None
        checked += 1
        if checked >= 5:
            break
    assert checked >= 1


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in range(1, 12):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_categorical_data() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
