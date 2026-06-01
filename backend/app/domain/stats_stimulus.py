"""Display-only statistics stimulus derivation for the Unit-7 stats KCs (CCSS 6.SP, TEKS 6.12D).

Grade-6 statistics is read off a VISUAL — a dot plot, a frequency/data table, or a histogram —
not a bare list of numbers in a sentence. The six Unit-7 stats KCs already generate a small data
set and list it in their prompt text; this module turns that SAME data set into a structured,
display-only ``StatsStimulus`` the surface can draw.

Single source of truth (the §8.4 anti-drift rule): the stimulus is DERIVED from the problem's
``operands`` — the exact data the generator also formats into the prompt text — so the picture and
the words can never disagree. Nothing here recomputes or invents data.

This is DISPLAY-ONLY, like ``FigureStimulus`` on the frontend: it carries the QUESTION INPUT (the
data set), never the ANSWER. The computed statistic (mean / median / MAD / a count / a relative
frequency) lives only in ``Problem.correct_value`` and never enters the stimulus — so showing the
picture leaks nothing the prompt text doesn't already say. The answer is still graded by the SymPy
verifier server-side (CLAUDE.md §8.2); this changes nothing about grading.

No SymPy decision-making and no LLM here — this is a pure projection of already-decided domain data
into a renderable shape (CLAUDE.md §7, §8.2). It lives in ``domain/`` because it reads the domain's
operand encoding (the leading mode/question sentinels documented on each generator).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sympy import Rational

from app.domain.center_spread import CENTER_MEDIAN, SPREAD_IQR, SPREAD_RANGE
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.misconceptions import DATA_DISPLAY_QUESTION_CODE

# The histogram bin width the data-displays generator uses (width-10 bins: 0-9, 10-19, ...).
# Kept in sync with ``problem_generators._DISPLAY_BIN_WIDTH`` (the generator that emits bin_freq
# items); duplicated as a small constant here so the stimulus builder needs no generator import
# cycle. A test pins the two to the same value.
_HISTOGRAM_BIN_WIDTH = 10

# Category labels for KC_categorical_data, in the order the counts are carried (descending). Kept in
# sync with ``problem_generators._CATEGORICAL_LABELS``; a test pins the two together so a relabel of
# the survey categories updates both.
_CATEGORICAL_LABELS: tuple[str, ...] = ("red", "blue", "green")

StatsStimulusKind = Literal["dot_plot", "frequency_table", "histogram"]


@dataclass(frozen=True)
class DotPlotStimulus:
    """A dot plot: one dot stacked above each occurrence of a value on a number line.

    ``values`` is the raw data set (whole numbers), in the order the generator produced it; the
    surface counts occurrences to stack the dots. ``axis_label`` names what the axis measures.
    """

    kind: Literal["dot_plot"]
    values: tuple[int, ...]
    axis_label: str


@dataclass(frozen=True)
class FrequencyTableStimulus:
    """A frequency / data table: a labeled count per category (categorical data).

    ``rows`` pairs each category label with its count, in the order the generator produced them.
    ``category_label`` / ``count_label`` head the two columns.
    """

    kind: Literal["frequency_table"]
    rows: tuple[tuple[str, int], ...]
    category_label: str
    count_label: str


@dataclass(frozen=True)
class HistogramStimulus:
    """A histogram: data grouped into equal-width bins, one bar per bin showing its frequency.

    ``bins`` pairs each bin's inclusive ``[lo, hi]`` range with the count of data points in it,
    ordered by ``lo``. ``bin_width`` is the equal width; ``axis_label`` names what the axis shows.
    """

    kind: Literal["histogram"]
    bins: tuple[tuple[int, int, int], ...]  # (lo, hi, count)
    bin_width: int
    axis_label: str


StatsStimulus = DotPlotStimulus | FrequencyTableStimulus | HistogramStimulus


def _ints(operands: tuple[Rational, ...]) -> list[int]:
    """The operand Rationals as plain ints (the stats data sets are whole numbers)."""
    return [int(v) for v in operands]


def _dot_plot(values: list[int], axis_label: str) -> DotPlotStimulus:
    return DotPlotStimulus(kind="dot_plot", values=tuple(values), axis_label=axis_label)


def _histogram(values: list[int], axis_label: str) -> HistogramStimulus:
    """Group ``values`` into width-``_HISTOGRAM_BIN_WIDTH`` bins, one bar per occupied bin.

    Bins are anchored on multiples of the width (0-9, 10-19, ...) — the same bins the
    data-displays generator's ``bin_freq`` question reads — and only occupied bins are shown,
    so the bars span exactly the data's range.
    """
    width = _HISTOGRAM_BIN_WIDTH
    lows = sorted({(v // width) * width for v in values})
    bins = tuple(
        (lo, lo + width - 1, sum(1 for v in values if lo <= v <= lo + width - 1)) for lo in lows
    )
    return HistogramStimulus(
        kind="histogram", bins=bins, bin_width=_HISTOGRAM_BIN_WIDTH, axis_label=axis_label
    )


def stimulus_for(
    kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None
) -> StatsStimulus | None:
    """The display-only stimulus for a stats problem, derived from its ``operands``; ``None`` for
    any problem that carries no stats data set (every non-stats KC, and KC_statistical_questions —
    a yes/no judgment with no data set).

    The per-KC operand encoding (documented on each generator in ``problem_generators``):

    - SUMMARY_STATISTICS: ``(mode_code, *data)`` -> dot plot of ``data``.
    - MEAN_ABSOLUTE_DEVIATION: ``data`` (no sentinel) -> dot plot of ``data``.
    - CENTER_SPREAD_SHAPE: ``(mode_flag, *sorted_data)`` -> dot plot of ``sorted_data``.
    - DATA_DISPLAYS: ``(question_code, param, *data)`` -> histogram for the bin-frequency question
      (the generator literally frames it as a histogram), else a dot plot of ``data``.
    - CATEGORICAL_DATA: ``(mode_code, *counts)`` -> frequency table of label -> count.

    Returns ``None`` (graceful: the surface falls back to the prompt text) when a problem has no
    operands at all, so a malformed item degrades rather than crashing the turn (CLAUDE.md §8.5).
    """
    if operands is None or len(operands) == 0:
        return None

    if kc is KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION:
        return _dot_plot(_ints(operands), axis_label="Value")

    if kc is KnowledgeComponentId.SUMMARY_STATISTICS:
        return _dot_plot(_ints(operands[1:]), axis_label="Value")

    if kc is KnowledgeComponentId.CENTER_SPREAD_SHAPE:
        # operands[0] is a measure-mode flag (CENTER_MEDIAN / SPREAD_RANGE / SPREAD_IQR); the data
        # set is the rest. The display is the same dot plot regardless of which measure is asked.
        if int(operands[0]) not in (CENTER_MEDIAN, SPREAD_RANGE, SPREAD_IQR):
            return None
        return _dot_plot(_ints(operands[1:]), axis_label="Value")

    if kc is KnowledgeComponentId.DATA_DISPLAYS:
        if len(operands) < 2:
            return None
        question_code = int(operands[0])
        data = _ints(operands[2:])
        if not data:
            return None
        if question_code == DATA_DISPLAY_QUESTION_CODE["bin_freq"]:
            return _histogram(data, axis_label="Value")
        return _dot_plot(data, axis_label="Value")

    if kc is KnowledgeComponentId.CATEGORICAL_DATA:
        counts = _ints(operands[1:])
        rows = tuple(
            (label, count) for label, count in zip(_CATEGORICAL_LABELS, counts, strict=False)
        )
        if not rows:
            return None
        return FrequencyTableStimulus(
            kind="frequency_table",
            rows=rows,
            category_label="Choice",
            count_label="Count",
        )

    return None
