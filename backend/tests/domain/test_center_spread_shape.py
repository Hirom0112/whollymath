"""Behavioral tests for KC_center_spread_shape — a Grade-6 (Unit 7) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Skill:
CCSS 6.SP.2 — describe a distribution by a measure of CENTER and a measure of SPREAD. For
Grade 6 the answer is kept NUMERIC: a single value computed exactly from a small data set
given in the prompt, under one of three measure modes —

* MEDIAN (center): the middle value of the sorted data.
* RANGE (spread): max − min.
* IQR (spread): Q3 − Q1, the median-of-halves interquartile range.

Pins: the generator builds a clean, in-scope item for each mode (a single numeric answer,
the data set carried in ``operands`` behind a leading mode flag); the verifier confirms the
exact correct value and classifies the modeled misconception (RANGE computed as max + min
instead of max − min); the worked example lands on the answer; and generation is deterministic
(PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2).

NOTE on the variable-length operand encoding: a data set is variable-length, so unlike the
fixed-arity KCs ``operands`` here is ``(mode_flag, *sorted_data)`` — a leading ``Rational``
sentinel (0=median, 1=range, 2=IQR) followed by the sorted data values. The wrong-answer model
matches with ``operand_count=None`` (any length), and its predictor reads the same encoding.
"""

from __future__ import annotations

from app.domain.center_spread import (
    CENTER_MEDIAN,
    SPREAD_IQR,
    SPREAD_RANGE,
    iqr,
    median,
    range_as_sum,
    range_spread,
)
from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.stats_stimulus import stimulus_for
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.CENTER_SPREAD_SHAPE


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _mode_and_data(problem: Problem) -> tuple[int, tuple[Rational, ...]]:
    assert problem.operands is not None
    mode = int(problem.operands[0])
    data = problem.operands[1:]
    return mode, data


def test_center_spread_shape_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_number_line_is_the_same_item_over_the_rendered_display() -> None:
    """NUMBER_LINE serves the SAME answer as SYMBOLIC (same operands + value), over the data set's
    rendered dot plot (stats_stimulus) — the masterable second representation, no new input widget.
    Center & spread are read along the line (panel audit 2026-06-04)."""
    sym = generate_problem(_KC, seed=5, surface_format=Representation.SYMBOLIC)
    line = generate_problem(_KC, seed=5, surface_format=Representation.NUMBER_LINE)
    assert line.surface_format is Representation.NUMBER_LINE
    assert line.operands == sym.operands
    assert line.correct_value == sym.correct_value
    assert stimulus_for(_KC, line.operands) is not None


def test_generated_problem_is_a_clean_in_scope_numeric_item() -> None:
    """The generator yields a numeric item whose operands carry a mode flag + a data set."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None
    mode, data = _mode_and_data(problem)
    assert mode in (CENTER_MEDIAN, SPREAD_RANGE, SPREAD_IQR)
    assert len(data) >= 4  # enough values to split into halves for an IQR
    assert all(v.q == 1 for v in data)  # whole-number data values
    assert tuple(data) == tuple(sorted(data))  # the generator pre-sorts the data set


def test_all_three_measure_modes_are_generated() -> None:
    """Across seeds the generator produces median-center, range, AND IQR items."""
    modes = {_mode_and_data(_problem(s))[0] for s in range(1, 60)}
    assert modes == {CENTER_MEDIAN, SPREAD_RANGE, SPREAD_IQR}


def test_correct_value_matches_the_exact_measure() -> None:
    """correct_value equals the exact measure for that item's mode (the SymPy-computed answer)."""
    for seed in range(1, 60):
        problem = _problem(seed)
        mode, data = _mode_and_data(problem)
        if mode == CENTER_MEDIAN:
            expected = median(data)
        elif mode == SPREAD_RANGE:
            expected = range_spread(data)
        else:
            expected = iqr(data)
        assert problem.correct_value == expected


def test_correct_answer_verifies_correct() -> None:
    """The exact measure is graded correct by the tutor's own oracle."""
    for seed in range(1, 60):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_range_sum_misconception_is_classified() -> None:
    """On a RANGE item, answering max + min (instead of max − min) is flagged OPERATION.

    Routed OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — added the extremes
    rather than subtracting them. With nonnegative whole-number data and distinct extremes,
    max + min != max − min, so the wrong value is always diagnostic.
    """
    seen = False
    for seed in range(1, 80):
        problem = _problem(seed)
        mode, data = _mode_and_data(problem)
        if mode != SPREAD_RANGE:
            continue
        seen = True
        wrong = range_as_sum(data)
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.RANGE_AS_SUM
    assert seen, "no RANGE item produced in the seed range"


def test_median_of_even_set_is_the_mean_of_the_two_middles() -> None:
    """The median pins the standard even-count rule (average of the two middle values)."""
    data = (Rational(2), Rational(4), Rational(6), Rational(8))
    assert median(data) == Rational(5)  # (4 + 6) / 2


def test_median_of_odd_set_is_the_middle_value() -> None:
    """The median of an odd-count set is the single middle value."""
    data = (Rational(1), Rational(3), Rational(5), Rational(7), Rational(9))
    assert median(data) == Rational(5)


def test_iqr_matches_the_q3_minus_q1_worked_example() -> None:
    """IQR of 2,4,6,8,10,12 is 6 (Q1 = 4, Q3 = 10) — the spec's worked example."""
    data = (Rational(2), Rational(4), Rational(6), Rational(8), Rational(10), Rational(12))
    assert iqr(data) == Rational(6)


def test_range_is_max_minus_min() -> None:
    """range_spread is exactly max − min."""
    data = (Rational(3), Rational(5), Rational(9), Rational(14))
    assert range_spread(data) == Rational(11)


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in (3, 5, 11):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_center_spread_shape() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
