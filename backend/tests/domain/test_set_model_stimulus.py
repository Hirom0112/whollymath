"""Tests for the display-only SET-MODEL stimulus (the coloured-counter jar for ratio language).

The stimulus must be DERIVED from the same operands the prompt text is built from, so the picture
and the words can never disagree (the §8.4 anti-drift rule). These pins assert: it fires only for
KC_ratio_language; its colours and counts match exactly what the generator put in the statement;
the asked colour is the first group; and it leaks no answer. Mandatory-TDD domain Layer 1
(CLAUDE.md §2). Skill: 6.RP.A.1.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import RATIO_COLOURS, generate_problem
from app.domain.set_model_stimulus import SetModelStimulus, set_model_for

_KC = KnowledgeComponentId.RATIO_LANGUAGE


def test_no_stimulus_for_non_ratio_kcs() -> None:
    """Every KC except ratio-language carries no counter picture."""
    for kc in KnowledgeComponentId:
        if kc is _KC:
            continue
        assert set_model_for(kc, None) is None
        assert set_model_for(kc, ()) is None


def test_malformed_operands_draw_no_picture() -> None:
    """A missing / wrong-shaped operand tuple returns None rather than crashing (defensive)."""
    assert set_model_for(_KC, None) is None
    assert set_model_for(_KC, ()) is None


def test_stimulus_matches_the_generated_statement() -> None:
    """Colours and counts in the picture appear verbatim in the prompt text, in order.

    The asked colour is the first group (the colour the question is about), and the two counts are
    the two colour counts the statement names — single source of truth, derived from operands.
    """
    for seed in range(1, 40):
        problem = generate_problem(_KC, seed)
        stimulus = set_model_for(problem.kc, problem.operands)
        assert isinstance(stimulus, SetModelStimulus)
        assert stimulus.kind == "set_model"
        assert len(stimulus.groups) == 2
        (c1, n1), (c2, n2) = stimulus.groups
        # The asked colour leads, and both colours are a real RATIO_COLOURS pair.
        assert stimulus.asked_colour == c1
        assert (c1, c2) in RATIO_COLOURS
        # Picture agrees with the words: "{n1} {c1}" and "{n2} {c2}" are both in the statement.
        assert f"{n1} {c1}" in problem.statement
        assert f"{n2} {c2}" in problem.statement


def test_stimulus_shows_the_givens_not_the_answer() -> None:
    """The picture holds exactly the two GIVEN counts (part, other) — the question input, not the
    computed fraction (no answer leak, §8.2). Counts come straight off the operands the prompt uses.
    """
    for seed in range(1, 20):
        problem = generate_problem(_KC, seed)
        assert problem.operands is not None
        part, other = int(problem.operands[2]), int(problem.operands[3])
        stimulus = set_model_for(problem.kc, problem.operands)
        assert isinstance(stimulus, SetModelStimulus)
        assert [count for _colour, count in stimulus.groups] == [part, other]
