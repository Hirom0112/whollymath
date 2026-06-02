"""Tests for the display-only GCF/LCM FACTOR-VIEW stimulus (the two numbers + their factor lists).

The stimulus must be DERIVED from the same operands the prompt text is built from, so the picture
and the words can never disagree (the §8.4 anti-drift rule). These pins assert: it fires only for
KC_gcf_lcm; the two numbers and their factor lists match the generated statement; the mode label is
read off the operand flag; and it leaks no answer (it never states the chosen GCF/LCM).
Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: 6.NS.4 / TEKS 6.7A.
"""

from __future__ import annotations

from app.domain.gcf_factors_stimulus import GcfFactorsStimulus, gcf_factors_for
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from sympy import Rational, igcd, ilcm

_KC = KnowledgeComponentId.GCF_LCM


def test_no_stimulus_for_non_gcf_kcs() -> None:
    """Every KC except GCF/LCM carries no factor view."""
    for kc in KnowledgeComponentId:
        if kc is _KC:
            continue
        assert gcf_factors_for(kc, None) is None
        assert gcf_factors_for(kc, ()) is None


def test_malformed_operands_draw_no_picture() -> None:
    """A missing / wrong-shaped operand tuple returns None rather than crashing (defensive)."""
    assert gcf_factors_for(_KC, None) is None
    assert gcf_factors_for(_KC, ()) is None
    assert gcf_factors_for(_KC, (Rational(4), Rational(6))) is None  # too short


def test_factor_lists_are_correct_and_ascending() -> None:
    """The factor lists are the true positive divisors of each number, in ascending order."""
    stimulus = gcf_factors_for(_KC, (Rational(12), Rational(18), Rational(0)))
    assert isinstance(stimulus, GcfFactorsStimulus)
    assert stimulus.first == 12
    assert stimulus.second == 18
    assert stimulus.first_factors == (1, 2, 3, 4, 6, 12)
    assert stimulus.second_factors == (1, 2, 3, 6, 9, 18)
    # Each list is sorted, starts at 1, ends at the number itself.
    for factors, n in ((stimulus.first_factors, 12), (stimulus.second_factors, 18)):
        assert list(factors) == sorted(factors)
        assert factors[0] == 1
        assert factors[-1] == n


def test_mode_is_read_off_the_operand_flag() -> None:
    """mode 0 → 'gcf', mode 1 → 'lcm' (the single-source-of-truth encoding the generator uses)."""
    gcf = gcf_factors_for(_KC, (Rational(8), Rational(12), Rational(0)))
    lcm = gcf_factors_for(_KC, (Rational(8), Rational(12), Rational(1)))
    assert gcf is not None and gcf.mode == "gcf"
    assert lcm is not None and lcm.mode == "lcm"


def test_stimulus_matches_the_generated_statement() -> None:
    """The two numbers in the picture appear verbatim in the prompt text, in order."""
    for seed in range(1, 40):
        problem = generate_problem(_KC, seed)
        stimulus = gcf_factors_for(problem.kc, problem.operands)
        assert isinstance(stimulus, GcfFactorsStimulus)
        assert stimulus.kind == "gcf_factors"
        assert f"of {stimulus.first} and {stimulus.second}" in problem.statement
        # The mode label agrees with which question the statement asks.
        if stimulus.mode == "lcm":
            assert "least common multiple" in problem.statement
        else:
            assert "greatest common factor" in problem.statement


def test_stimulus_shows_givens_not_the_answer() -> None:
    """The picture holds the two GIVEN numbers' own factors, never the chosen GCF/LCM (§8.2).

    The factor lists are full divisor lists of the inputs; they must NOT collapse to a single
    answer, and the computed GCF/LCM must not be exposed as a dedicated field of the stimulus.
    """
    for seed in range(1, 20):
        problem = generate_problem(_KC, seed)
        assert problem.operands is not None
        a, b = int(problem.operands[0]), int(problem.operands[1])
        stimulus = gcf_factors_for(problem.kc, problem.operands)
        assert isinstance(stimulus, GcfFactorsStimulus)
        # The stimulus exposes only givens + their factors — no field equals the computed answer.
        answer = int(ilcm(a, b)) if stimulus.mode == "lcm" else int(igcd(a, b))
        fields = {stimulus.first, stimulus.second}
        assert answer not in fields
        # The factor lists are the inputs' divisors, not a single chosen value.
        assert len(stimulus.first_factors) >= 2
        assert len(stimulus.second_factors) >= 2
