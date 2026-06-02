"""Tests for the display-only FRACTION AREA-MODEL stimulus (operand bars for the four two-operand
fraction-arithmetic KCs: add / subtract / multiply / divide unlike-denominator fractions).

The stimulus must be DERIVED from the same operands the prompt text is built from, so the picture
and the words can never disagree (the §8.4 anti-drift rule). These pins assert: it fires only for
the four arithmetic KCs; each operand bar's numerator/denominator match exactly the fractions the
generator put in the statement; the ``op`` tag matches the KC; and it leaks NO answer (only the two
givens, never the sum/difference/product/quotient). Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.fraction_area_stimulus import (
    FractionAreaStimulus,
    fraction_area_for,
)
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from sympy import Rational

_KCS = {
    KnowledgeComponentId.ADDITION_UNLIKE: "add",
    KnowledgeComponentId.SUBTRACTION_UNLIKE: "subtract",
    KnowledgeComponentId.MULTIPLY_FRACTIONS: "multiply",
    KnowledgeComponentId.DIVIDE_FRACTIONS: "divide",
}


def test_no_stimulus_for_unrelated_kcs() -> None:
    """Every KC except the four two-operand fraction-arithmetic KCs carries no area picture."""
    for kc in KnowledgeComponentId:
        if kc in _KCS:
            continue
        assert fraction_area_for(kc, None) is None
        assert fraction_area_for(kc, ()) is None


def test_malformed_operands_draw_no_picture() -> None:
    """A missing / wrong-shaped operand tuple returns None rather than crashing (defensive)."""
    for kc in _KCS:
        assert fraction_area_for(kc, None) is None
        assert fraction_area_for(kc, ()) is None
        assert fraction_area_for(kc, (Rational(1, 2),)) is None  # only one operand


def test_op_tag_matches_the_kc() -> None:
    """The ``op`` field records the KC's operation (layout metadata, not a computed result)."""
    for kc, op in _KCS.items():
        problem = generate_problem(kc, seed=1)
        stimulus = fraction_area_for(problem.kc, problem.operands)
        assert isinstance(stimulus, FractionAreaStimulus)
        assert stimulus.kind == "fraction_area"
        assert stimulus.op == op


def test_bars_match_the_generated_statement() -> None:
    """Each operand bar's numerator/denominator appear verbatim in the prompt text, in order.

    Single source of truth: the two bars are the two operand fractions the statement names,
    derived straight from operands — the picture cannot drift from the words.
    """
    for kc in _KCS:
        for seed in range(1, 30):
            problem = generate_problem(kc, seed)
            stimulus = fraction_area_for(problem.kc, problem.operands)
            assert isinstance(stimulus, FractionAreaStimulus)
            f, s = stimulus.first, stimulus.second
            # Bars are proper, well-formed partitions.
            assert f.denominator >= 1
            assert s.denominator >= 1
            # Picture agrees with the words: both operand fractions are in the statement.
            assert f"{f.numerator}/{f.denominator}" in problem.statement
            assert f"{s.numerator}/{s.denominator}" in problem.statement


def test_bars_are_exactly_the_operands_not_the_answer() -> None:
    """The picture holds exactly the two GIVEN operands — never the computed result (no answer
    leak, §8.2). Numerators/denominators come straight off the operand Rationals.
    """
    for kc in _KCS:
        for seed in range(1, 20):
            problem = generate_problem(kc, seed)
            assert problem.operands is not None
            first, second = problem.operands[0], problem.operands[1]
            stimulus = fraction_area_for(problem.kc, problem.operands)
            assert isinstance(stimulus, FractionAreaStimulus)
            assert (stimulus.first.numerator, stimulus.first.denominator) == (
                int(first.p),
                int(first.q),
            )
            assert (stimulus.second.numerator, stimulus.second.denominator) == (
                int(second.p),
                int(second.q),
            )
            # The stimulus carries exactly the two operands and nothing else — no third bar, no
            # field derived from the result the student must compute (answer-leak guard, §8.2).
            assert set(vars(stimulus).keys()) == {"kind", "op", "first", "second"}
