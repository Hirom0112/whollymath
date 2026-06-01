"""Tests for the display-only stats stimulus derivation (``app.domain.stats_stimulus``).

These pin the contract the Unit-7 stats lessons rely on: every in-scope stats KC emits a structured
stimulus whose data MATCHES the data set the generator carries in ``operands`` (single source of
truth — the picture can't disagree with the prompt), and the stimulus NEVER contains the answer (the
computed statistic). KC_statistical_questions (a yes/no judgment with no data set) gets no stimulus.

The data set is recovered from ``operands`` the same way the verifier does (the documented leading
sentinels), so a desync between the generator's encoding and this builder fails here.
"""

from __future__ import annotations

import random

import pytest
from app.domain.center_spread import CENTER_MEDIAN, SPREAD_IQR, SPREAD_RANGE
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import DATA_DISPLAY_QUESTION_CODE
from app.domain.problem_generators import (
    _CATEGORICAL_LABELS,
    _DISPLAY_BIN_WIDTH,
    GENERATORS,
    Problem,
)
from app.domain.stats_stimulus import _CATEGORICAL_LABELS as STIM_LABELS
from app.domain.stats_stimulus import (
    _HISTOGRAM_BIN_WIDTH,
    DotPlotStimulus,
    FrequencyTableStimulus,
    HistogramStimulus,
    stimulus_for,
)


def _problem(kc: KnowledgeComponentId, seed: int, difficulty: int | None = None) -> Problem:
    """Generate one problem for ``kc`` deterministically (SYMBOLIC surface — stats is symbolic)."""
    return GENERATORS[kc](random.Random(seed), seed, Representation.SYMBOLIC, difficulty)


def _ops(problem: Problem) -> tuple[int, ...]:
    """The problem's operands as ints — asserting they exist (a stats item always carries data)."""
    assert problem.operands is not None
    return tuple(int(v) for v in problem.operands)


def test_constants_stay_in_sync_with_the_generators() -> None:
    """The builder's bin width and category labels mirror the generator's (anti-desync)."""
    assert _HISTOGRAM_BIN_WIDTH == _DISPLAY_BIN_WIDTH
    assert STIM_LABELS == _CATEGORICAL_LABELS


def test_summary_statistics_emits_dot_plot_of_the_data_set() -> None:
    for seed in range(20):
        problem = _problem(KnowledgeComponentId.SUMMARY_STATISTICS, seed)
        stim = stimulus_for(problem.kc, problem.operands)
        assert isinstance(stim, DotPlotStimulus)
        # operands = (mode_code, *data); the dot plot is exactly the data set, in order.
        data = _ops(problem)[1:]
        assert stim.values == data


def test_mean_absolute_deviation_emits_dot_plot_of_the_full_data_set() -> None:
    for seed in range(20):
        problem = _problem(KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION, seed)
        stim = stimulus_for(problem.kc, problem.operands)
        assert isinstance(stim, DotPlotStimulus)
        # operands IS the data set (no sentinel) for MAD.
        assert stim.values == _ops(problem)


def test_center_spread_emits_dot_plot_of_sorted_data_for_every_mode() -> None:
    seen_modes: set[int] = set()
    for seed in range(30):
        problem = _problem(KnowledgeComponentId.CENTER_SPREAD_SHAPE, seed)
        seen_modes.add(_ops(problem)[0])
        stim = stimulus_for(problem.kc, problem.operands)
        assert isinstance(stim, DotPlotStimulus)
        # operands = (mode_flag, *sorted_data); the dot plot is the sorted data.
        assert stim.values == _ops(problem)[1:]
    # All three measure modes appeared (the dot plot is mode-independent — same data display).
    assert seen_modes == {CENTER_MEDIAN, SPREAD_RANGE, SPREAD_IQR}


def test_data_displays_uses_histogram_for_bin_freq_and_dot_plot_otherwise() -> None:
    saw_hist = saw_dot = False
    for seed in range(60):
        problem = _problem(KnowledgeComponentId.DATA_DISPLAYS, seed, difficulty=4)
        ops = _ops(problem)
        question_code = ops[0]
        data = ops[2:]
        stim = stimulus_for(problem.kc, problem.operands)
        if question_code == DATA_DISPLAY_QUESTION_CODE["bin_freq"]:
            assert isinstance(stim, HistogramStimulus)
            saw_hist = True
            # Every data point lands in exactly one shown bin; bin counts total the data set size.
            assert sum(count for _, _, count in stim.bins) == len(data)
            for lo, hi, count in stim.bins:
                assert hi - lo + 1 == _HISTOGRAM_BIN_WIDTH
                assert count == sum(1 for v in data if lo <= v <= hi)
        else:
            assert isinstance(stim, DotPlotStimulus)
            assert stim.values == data
            saw_dot = True
    assert saw_hist and saw_dot  # both display kinds were exercised


def test_categorical_data_emits_frequency_table_of_label_counts() -> None:
    for seed in range(20):
        problem = _problem(KnowledgeComponentId.CATEGORICAL_DATA, seed)
        stim = stimulus_for(problem.kc, problem.operands)
        assert isinstance(stim, FrequencyTableStimulus)
        # operands = (mode_code, *counts); the table pairs each label with its count, in order.
        counts = _ops(problem)[1:]
        assert stim.rows == tuple(zip(_CATEGORICAL_LABELS, counts, strict=True))


def test_statistical_questions_has_no_stimulus() -> None:
    """A yes/no 'is this a statistical question?' item carries no data set → no stimulus."""
    for seed in range(10):
        problem = _problem(KnowledgeComponentId.STATISTICAL_QUESTIONS, seed)
        assert stimulus_for(problem.kc, problem.operands) is None


def test_non_stats_kc_has_no_stimulus() -> None:
    """A non-stats problem (fraction addition) never gets a stats stimulus."""
    problem = _problem(KnowledgeComponentId.ADDITION_UNLIKE, 0)
    assert stimulus_for(problem.kc, problem.operands) is None


def test_none_operands_yield_no_stimulus() -> None:
    """A stats KC with no operands degrades gracefully to no stimulus (surface uses prompt text)."""
    assert stimulus_for(KnowledgeComponentId.SUMMARY_STATISTICS, None) is None
    assert stimulus_for(KnowledgeComponentId.SUMMARY_STATISTICS, ()) is None


def test_stimulus_never_contains_the_answer_value() -> None:
    """The stimulus carries only the QUESTION INPUT (the data set), never the computed statistic.

    For each in-scope stats KC, the set of numbers the stimulus exposes must equal the data set the
    generator carried — the answer (``correct_value``) is not added in as an extra fact (it can of
    course coincidentally equal a data value; the guard is on the SHAPE, not on value-absence).
    """
    in_scope = [
        KnowledgeComponentId.SUMMARY_STATISTICS,
        KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION,
        KnowledgeComponentId.CENTER_SPREAD_SHAPE,
        KnowledgeComponentId.DATA_DISPLAYS,
        KnowledgeComponentId.CATEGORICAL_DATA,
    ]
    for kc in in_scope:
        for seed in range(10):
            problem = _problem(kc, seed)
            stim = stimulus_for(problem.kc, problem.operands)
            assert stim is not None
            if isinstance(stim, DotPlotStimulus):
                exposed = set(stim.values)
            elif isinstance(stim, FrequencyTableStimulus):
                exposed = {count for _, count in stim.rows}
            else:
                exposed = {count for _, _, count in stim.bins}
            # The exposed numbers are a subset of the data set the generator carried (no answer
            # injected). For a dot plot that's the operand data verbatim.
            data = set(_ops(problem))
            if isinstance(stim, DotPlotStimulus):
                assert exposed <= data
            # (Frequency-table counts ARE the operand data; histogram counts are frequencies, not
            # data values, so they need not be operand members — the SHAPE guards leakage.)


@pytest.mark.parametrize("difficulty", [None, 1, 2, 3, 4])
def test_in_scope_stats_kc_emits_a_stimulus_at_every_difficulty(difficulty: int | None) -> None:
    for kc in (
        KnowledgeComponentId.SUMMARY_STATISTICS,
        KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION,
        KnowledgeComponentId.CENTER_SPREAD_SHAPE,
        KnowledgeComponentId.DATA_DISPLAYS,
        KnowledgeComponentId.CATEGORICAL_DATA,
    ):
        problem = _problem(kc, 7, difficulty)
        assert stimulus_for(problem.kc, problem.operands) is not None
