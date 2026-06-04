"""Tests for the display-only PLACE-VALUE CHART stimulus (the aligned decimal columns for decimals).

The stimulus must be DERIVED from the same operands the prompt text is built from, so the chart and
the words can never disagree (the CLAUDE.md §8.4 anti-drift rule). These pins assert: it fires only
for KC_decimal_operations; each row reads back to the same number the prompt names; the columns
align on the decimal point; the digits reconstruct the operands exactly (float-free); and it leaks
no product (§8.2). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: 6.NS.B.3.
"""

from __future__ import annotations

from app.domain.decimal_place_value_stimulus import (
    DecimalPlaceValueStimulus,
    decimal_place_value_for,
)
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from sympy import Rational

_KC = KnowledgeComponentId.DECIMAL_OPERATIONS


def test_no_stimulus_for_non_decimal_kcs() -> None:
    """Every KC except decimal-operations carries no place-value chart."""
    for kc in KnowledgeComponentId:
        if kc is _KC:
            continue
        assert decimal_place_value_for(kc, None) is None
        assert decimal_place_value_for(kc, (Rational(2, 10), Rational(5, 10))) is None


def test_malformed_operands_draw_no_chart() -> None:
    """A missing / empty operand tuple returns None rather than crashing (defensive)."""
    assert decimal_place_value_for(_KC, None) is None
    assert decimal_place_value_for(_KC, ()) is None


def test_columns_are_aligned_on_the_decimal_point() -> None:
    """``point_after`` indexes the ones column; integer places precede it, fractional follow it.

    Every row carries exactly one digit per column (same length as ``columns``), so the grid is
    rectangular and the surface can line the decimal point up across rows.
    """
    for seed in range(1, 40):
        problem = generate_problem(_KC, seed)
        stimulus = decimal_place_value_for(problem.kc, problem.operands)
        assert isinstance(stimulus, DecimalPlaceValueStimulus)
        assert stimulus.kind == "decimal_place_value"
        # The ones column is the last integer place; the point follows it.
        assert stimulus.columns[stimulus.point_after] == "ones"
        # Integer places are whole-number labels; fractional places end in "ths".
        for col in stimulus.columns[: stimulus.point_after + 1]:
            assert col in ("thousands", "hundreds", "tens", "ones")
        for col in stimulus.columns[stimulus.point_after + 1 :]:
            assert col.endswith("ths")
        # Rectangular grid: one digit per column, every digit is a single 0-9.
        for row in stimulus.rows:
            assert len(row.digits) == len(stimulus.columns)
            assert all(d.isdigit() and len(d) == 1 for d in row.digits)


def test_rows_match_the_generated_statement() -> None:
    """Each operand row reads back to the SAME number the prompt names, in order.

    Single source of truth: the row's digits are laid from the two decimal operands the statement is
    formatted from. ``operands = (first, second, mode)`` since the Slice-4a four-operation build, so
    only the first two operands are charted (``mode`` is a routing flag, not a decimal). The row's
    ``decimal_text`` is the chart's grid form, padded to the shared column width (e.g. ``0.50`` when
    another operand needs hundredths), so it can be longer than the prompt's minimal literal -- but
    it must denote the identical value. Chart and words cannot drift.
    """
    for seed in range(1, 40):
        problem = generate_problem(_KC, seed)
        stimulus = decimal_place_value_for(problem.kc, problem.operands)
        assert isinstance(stimulus, DecimalPlaceValueStimulus)
        assert problem.operands is not None
        factors = problem.operands[:2]  # drop the trailing mode flag; only the two operands chart
        assert len(stimulus.rows) == len(factors)
        for operand, row in zip(factors, stimulus.rows, strict=True):
            # The grid text denotes the operand exactly (trailing-zero padding aside).
            assert Rational(row.decimal_text) == operand


def test_digits_reconstruct_the_operands_exactly() -> None:
    """The digit grid encodes each decimal operand exactly (float-free): reading the digits back
    across the aligned point yields the operand Rational, never the answer (no leak, §8.2).
    """
    for seed in range(1, 20):
        problem = generate_problem(_KC, seed)
        assert problem.operands is not None
        stimulus = decimal_place_value_for(problem.kc, problem.operands)
        assert isinstance(stimulus, DecimalPlaceValueStimulus)
        frac_places = len(stimulus.columns) - 1 - stimulus.point_after
        factors = problem.operands[:2]  # the mode flag is not a charted decimal
        # Every row reconstructs to exactly one of the two OPERANDS -- and there is one row per
        # operand, so the chart holds the operands only. The answer is never among the rows.
        for operand, row in zip(factors, stimulus.rows, strict=True):
            scaled = int("".join(row.digits))
            assert Rational(scaled, 10**frac_places) == operand
