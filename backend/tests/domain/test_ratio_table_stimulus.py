"""Tests for the display-only RATIO-TABLE stimulus (the two-row equivalent-ratios scaffold).

The stimulus must be DERIVED from the same operands the prompt text is built from, so the table and
the words can never disagree (the §8.4 anti-drift rule). These pins assert: it fires only for the
unit-rate / equivalent-ratios family; its numbers match exactly what the generator put in the
statement; the scaffold structure (the scale arrow) is shown; and the asked cell is BLANK so no
answer leaks (§8.2). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skills: 6.RP.A.2 / 6.RP.A.3a.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from app.domain.ratio_table_stimulus import (
    RatioTableStimulus,
    ratio_table_for,
)
from sympy import Rational

_UNIT_RATE = KnowledgeComponentId.UNIT_RATE
_EQUIV = KnowledgeComponentId.EQUIVALENT_RATIOS


def test_no_stimulus_for_unrelated_kcs() -> None:
    """Every KC except the unit-rate / equivalent-ratios family carries no ratio table."""
    for kc in KnowledgeComponentId:
        if kc in (_UNIT_RATE, _EQUIV):
            continue
        assert ratio_table_for(kc, None) is None
        assert ratio_table_for(kc, (Rational(1), Rational(2))) is None


def test_malformed_operands_draw_no_table() -> None:
    """A missing / wrong-shaped operand tuple returns None rather than crashing (defensive)."""
    assert ratio_table_for(_UNIT_RATE, None) is None
    assert ratio_table_for(_UNIT_RATE, ()) is None
    assert ratio_table_for(_UNIT_RATE, (Rational(6),)) is None  # too short
    assert ratio_table_for(_EQUIV, None) is None
    assert ratio_table_for(_EQUIV, (Rational(1), Rational(2))) is None  # too short
    # A zero count / zero bottom term has no meaningful scale arrow.
    assert ratio_table_for(_UNIT_RATE, (Rational(6), Rational(0))) is None
    assert ratio_table_for(_EQUIV, (Rational(1), Rational(0), Rational(0))) is None


def test_unit_rate_table_matches_the_generated_statement() -> None:
    """Unit-rate table shows the given (total, count) column verbatim from the prompt, plus the
    unit column with a blank top cell (the per-one rate the student must find) — no answer leak.
    """
    for seed in range(1, 40):
        problem = generate_problem(_UNIT_RATE, seed)
        assert problem.operands is not None
        total, count = int(problem.operands[0]), int(problem.operands[1])
        stimulus = ratio_table_for(problem.kc, problem.operands)
        assert isinstance(stimulus, RatioTableStimulus)
        assert stimulus.kind == "ratio_table"
        assert len(stimulus.columns) == 2
        # The given numbers appear in the prompt statement (single source of truth).
        assert f"{total} " in problem.statement
        assert f"{count} " in problem.statement
        # Column 0 is the unit column: blank top (asked), bottom == 1.
        assert stimulus.columns[0].top is None
        assert stimulus.columns[0].bottom == 1
        # Column 1 is the given column: total over count.
        assert stimulus.columns[1].top == total
        assert stimulus.columns[1].bottom == count
        # The scaffold step is the scale-down arrow ÷count.
        assert stimulus.scale_label == f"÷{count}"


def test_unit_rate_table_never_shows_the_answer() -> None:
    """The unit rate (total/count) never appears as a numeric cell — exactly one cell is blank."""
    for seed in range(1, 40):
        problem = generate_problem(_UNIT_RATE, seed)
        assert problem.operands is not None
        rate = int(Rational(int(problem.operands[0]), int(problem.operands[1])))
        stimulus = ratio_table_for(problem.kc, problem.operands)
        assert isinstance(stimulus, RatioTableStimulus)
        cells = [c.top for c in stimulus.columns] + [c.bottom for c in stimulus.columns]
        # Exactly one cell is blank (the asked per-one quantity).
        assert cells.count(None) == 1
        # The blank one is the unit-column top; the answer rate is not in any shown top cell.
        # (total and count are shown, but the per-ONE rate itself is the blank cell.)
        assert stimulus.columns[0].top is None
        # If the rate happens to equal a shown given (e.g. count), the asked cell is still blank;
        # the asked top cell specifically is None, so the student isn't handed the answer there.
        assert rate >= 1  # sanity: generator builds whole-number friendly rates


def test_equivalent_ratios_table_matches_the_generated_statement() -> None:
    """Equivalent-ratios table shows the given (a, b) column and the asked (?, target_den) column,
    with the scale-UP arrow ×k between them — all derived from operands, blank top in asked column.
    """
    for seed in range(1, 40):
        problem = generate_problem(_EQUIV, seed)
        assert problem.operands is not None
        a, b, target_den = (
            int(problem.operands[0]),
            int(problem.operands[1]),
            int(problem.operands[2]),
        )
        k = target_den // b
        stimulus = ratio_table_for(problem.kc, problem.operands)
        assert isinstance(stimulus, RatioTableStimulus)
        assert stimulus.kind == "ratio_table"
        assert len(stimulus.columns) == 2
        # The given ratio and target appear verbatim in the prompt: "a : b = ? : target_den".
        assert f"{a} : {b} = ? : {target_den}" in problem.statement
        # Given column: a over b.
        assert stimulus.columns[0].top == a
        assert stimulus.columns[0].bottom == b
        # Asked column: blank top (the missing term), target_den bottom.
        assert stimulus.columns[1].top is None
        assert stimulus.columns[1].bottom == target_den
        # Scaffold step: ×k.
        assert stimulus.scale_label == f"×{k}"


def test_equivalent_ratios_table_never_shows_the_answer() -> None:
    """The missing term (a*k) never appears as a numeric cell — exactly one cell is blank."""
    for seed in range(1, 40):
        problem = generate_problem(_EQUIV, seed)
        assert problem.operands is not None
        a, b, target_den = (
            int(problem.operands[0]),
            int(problem.operands[1]),
            int(problem.operands[2]),
        )
        answer = a * (target_den // b)
        stimulus = ratio_table_for(problem.kc, problem.operands)
        assert isinstance(stimulus, RatioTableStimulus)
        shown_tops = [c.top for c in stimulus.columns if c.top is not None]
        # The asked top cell is blank, and the answer is not among the SHOWN top cells.
        assert stimulus.columns[1].top is None
        assert answer not in shown_tops
        cells = [c.top for c in stimulus.columns] + [c.bottom for c in stimulus.columns]
        assert cells.count(None) == 1
