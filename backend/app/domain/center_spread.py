"""Exact center/spread measures for KC_center_spread_shape (CCSS 6.SP.2).

Grade-6 keeps the answer NUMERIC: a single value describing a distribution by a measure of
CENTER (the median) or SPREAD (the range, or the interquartile range). All computation is exact
SymPy ``Rational`` arithmetic — no floats — so the verifier's value-equality grading is exact
(CLAUDE.md §8.2: the domain decides the math, never an LLM).

The three measure MODES are encoded as small integer sentinels so the problem generator can carry
the mode in front of the data set inside ``Problem.operands`` (a variable-length data set), and the
verifier's wrong-answer predictor can recover both the mode and the data from that one field.

IQR uses the standard Grade-6 median-of-halves method (Q1 = median of the lower half, Q3 = median
of the upper half; for an odd count the overall median is excluded from both halves).
"""

from __future__ import annotations

from sympy import Rational

# Measure-mode sentinels carried as ``operands[0]`` (see the _generate_center_spread generator).
CENTER_MEDIAN = 0  # center: the median (middle) value
SPREAD_RANGE = 1  # spread: max - min
SPREAD_IQR = 2  # spread: Q3 − Q1 (interquartile range)


def median(data: tuple[Rational, ...]) -> Rational:
    """The median of an already-sorted, non-empty data set (exact ``Rational``).

    Odd count → the single middle value; even count → the mean of the two middle values.
    """
    n = len(data)
    if n == 0:
        raise ValueError("median of an empty data set is undefined")
    mid = n // 2
    if n % 2 == 1:
        return data[mid]
    return (data[mid - 1] + data[mid]) / 2


def range_spread(data: tuple[Rational, ...]) -> Rational:
    """The range of a non-empty data set: ``max − min`` (the correct spread)."""
    if not data:
        raise ValueError("range of an empty data set is undefined")
    return max(data) - min(data)


def range_as_sum(data: tuple[Rational, ...]) -> Rational:
    """range-as-sum misconception: ``max + min`` instead of ``max − min``.

    The learner computes the range by ADDING the extremes rather than subtracting them. With the
    generator's nonnegative whole-number data and distinct extremes (max > min ≥ 0), the sum always
    differs from the correct difference, so this wrong value is diagnostic.
    """
    if not data:
        raise ValueError("range of an empty data set is undefined")
    return max(data) + min(data)


def iqr(data: tuple[Rational, ...]) -> Rational:
    """The interquartile range of a sorted data set: ``Q3 − Q1`` (median-of-halves method).

    Splits the sorted data at the middle: the lower half is everything below the center, the upper
    half everything above it. For an odd count the overall median is excluded from both halves
    (the standard Grade-6 convention). Q1 = median of the lower half, Q3 = median of the upper half.
    Requires at least four values so each half is non-empty.
    """
    n = len(data)
    if n < 4:
        raise ValueError("IQR needs at least four values to split into two non-empty halves")
    half = n // 2
    lower = data[:half]
    upper = data[half:] if n % 2 == 0 else data[half + 1 :]
    return median(upper) - median(lower)
