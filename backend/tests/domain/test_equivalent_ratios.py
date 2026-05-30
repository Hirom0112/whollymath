"""Behavioral tests for KC_equivalent_ratios — Grade-6 Unit 1 (2026-05-30).

Exercises the KC through the SAME oracle the tutor uses (the SymPy verifier). Pins: the
generator builds a scalable ratio with a clean multiplicative answer; the verifier confirms
the correct missing term and flags the additive-ratio misconception; the worked example lands
on the answer; generation is deterministic. Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, additive_ratio
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.EQUIVALENT_RATIOS


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_equivalent_ratios_is_live() -> None:
    assert _KC in LIVE_KCS


def test_generated_problem_is_a_scalable_ratio() -> None:
    """A numeric item with (a, b, target_den) operands where target_den is a multiple of b."""
    problem = _problem(5)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 3
    a, b, target_den = (int(o) for o in problem.operands)
    assert target_den % b == 0
    assert problem.correct_value == a * (target_den // b)


def test_correct_missing_term_verifies_correct() -> None:
    for seed in range(1, 12):
        problem = _problem(seed)
        assert verify(problem, str(problem.correct_value)).is_correct


def test_additive_answer_is_classified() -> None:
    """The additive (add-the-difference) answer is flagged OPERATION + additive-ratio."""
    for seed in range(1, 12):
        problem = _problem(seed)
        assert problem.operands is not None
        a, b, target_den = (int(o) for o in problem.operands)
        additive = additive_ratio(a, b, target_den)
        # The generator keeps scale factor ≥3, so the additive answer is always wrong here.
        assert additive != problem.correct_value
        result = verify(problem, str(additive))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.ADDITIVE_RATIO


def test_generation_is_deterministic() -> None:
    assert generate_problem(_KC, 9).statement == generate_problem(_KC, 9).statement
    assert generate_problem(_KC, 9).correct_value == generate_problem(_KC, 9).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    problem = _problem(4)
    assert worked_example_for(problem).final_value == problem.correct_value


def test_nudge_bank_covers_equivalent_ratios() -> None:
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
