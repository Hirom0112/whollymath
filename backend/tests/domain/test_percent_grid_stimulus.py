"""Tests for the display-only PERCENT HUNDRED-GRID stimulus (the 10x10 grid for KC_percent).

The stimulus must be DERIVED from the same operands the prompt text is built from, so the picture
and the words can never disagree (the §8.4 anti-drift rule). These pins assert: it fires only for
KC_percent; the shaded count equals the percent the generator put in the statement; it never shades
the computed answer (no leak, §8.2); and a malformed operand tuple draws nothing. Mandatory-TDD
domain Layer 1 (CLAUDE.md §2). Skill: 6.RP.A.3c.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.percent_grid_stimulus import PercentGridStimulus, percent_grid_for
from app.domain.problem_generators import generate_problem
from sympy import Rational

_KC = KnowledgeComponentId.PERCENT


def test_no_stimulus_for_non_percent_kcs() -> None:
    """Every KC except KC_percent carries no hundred-grid."""
    for kc in KnowledgeComponentId:
        if kc is _KC:
            continue
        assert percent_grid_for(kc, None) is None
        assert percent_grid_for(kc, (Rational(30), Rational(60))) is None


def test_malformed_operands_draw_no_picture() -> None:
    """A missing / wrong-shaped operand tuple returns None rather than crashing (defensive)."""
    assert percent_grid_for(_KC, None) is None
    assert percent_grid_for(_KC, ()) is None
    assert percent_grid_for(_KC, (Rational(30),)) is None
    assert percent_grid_for(_KC, (Rational(30), Rational(60), Rational(1))) is None


def test_stimulus_matches_the_generated_statement() -> None:
    """The shaded count equals the percent the statement names — single source of truth.

    The generator writes "What is {percent}% of {whole}?" with ``operands = (percent, whole)``. The
    grid shades exactly that percent out of 100, and that percent appears verbatim in the prompt.
    """
    for seed in range(1, 40):
        problem = generate_problem(_KC, seed)
        assert problem.operands is not None
        percent = int(problem.operands[0])
        stimulus = percent_grid_for(problem.kc, problem.operands)
        assert isinstance(stimulus, PercentGridStimulus)
        assert stimulus.kind == "percent_grid"
        assert stimulus.percent == percent
        assert stimulus.shaded == percent
        assert f"{percent}%" in problem.statement


def test_stimulus_shows_the_percent_not_the_answer() -> None:
    """The grid shades the GIVEN percent (the question input), never the computed answer (§8.2).

    For "30% of 60" the answer is 18; the grid must shade 30, not 18. The percent and the answer are
    distinct by construction (wholes exclude 100 in the generator), so this is a real guard.
    """
    for seed in range(1, 40):
        problem = generate_problem(_KC, seed)
        assert problem.operands is not None
        percent = int(problem.operands[0])
        answer = problem.correct_value
        stimulus = percent_grid_for(problem.kc, problem.operands)
        assert isinstance(stimulus, PercentGridStimulus)
        # Shades the percent, and the percent is never the answer for these problems.
        assert stimulus.shaded == percent
        assert Rational(stimulus.shaded) != answer


def test_shaded_count_clamped_to_grid() -> None:
    """Defensive: a percent outside [0, 100] shades no more than a full grid (and no negatives)."""
    over = percent_grid_for(_KC, (Rational(150), Rational(40)))
    assert isinstance(over, PercentGridStimulus)
    assert over.percent == 150
    assert over.shaded == 100
    under = percent_grid_for(_KC, (Rational(-10), Rational(40)))
    assert isinstance(under, PercentGridStimulus)
    assert under.shaded == 0
