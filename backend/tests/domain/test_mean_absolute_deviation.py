"""Behavioral tests for KC_mean_absolute_deviation — a Grade-6 (Unit 7) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope MAD item over a small data set; the verifier confirms
the correct MAD and classifies the forgot-absolute-value misconception (averaging the SIGNED
deviations, which always sum to zero, so the wrong "MAD" is 0); the worked example lands on
the answer; and generation is deterministic (PROJECT.md §4.1). The data set is a VARIABLE-
LENGTH operand tuple (4–6 values), so the wrong-answer model matches on KC alone
(``operand_count=None``) rather than a fixed arity. Mandatory-TDD domain Layer 1
(CLAUDE.md §2). Skill: CCSS 6.SP.5c — summarize spread with the mean absolute deviation.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, mean_signed_deviation
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _mad(data: tuple[Rational, ...]) -> Rational:
    """Reference MAD: the mean of the absolute deviations from the data's mean."""
    mean = sum(data, Rational(0)) / len(data)
    return sum((abs(x - mean) for x in data), Rational(0)) / len(data)


def test_mad_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_mad_is_a_clean_in_scope_problem() -> None:
    """A numeric item over a small (4–6 value) integer data set; answer = the exact MAD > 0."""
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.kc is _KC
        assert problem.answer_kind is AnswerKind.NUMERIC
        assert problem.operands is not None
        data = problem.operands
        assert 4 <= len(data) <= 6
        assert all(x.q == 1 for x in data), "data values are whole numbers"
        # The mean is an integer and the MAD is positive (a non-degenerate spread).
        mean = sum(data, Rational(0)) / len(data)
        assert mean.q == 1, f"mean should be a whole number, got {mean}"
        assert problem.correct_value == _mad(data)
        assert problem.correct_value > 0


def test_correct_mad_verifies_correct() -> None:
    """The exact MAD is graded correct by the tutor's own oracle."""
    for seed in range(1, 30):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_forgot_absolute_value_is_classified() -> None:
    """Averaging the SIGNED deviations (skipping absolute value) is flagged OPERATION + the
    forgot-absolute-value misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — summed the
    deviations without taking their absolute values first, so the positives and negatives cancel
    and the mean of the signed deviations is always 0. That zero is DISTINCT from the correct MAD
    because the generator only emits data sets with a positive spread (MAD > 0).
    """
    for seed in range(1, 30):
        problem = _problem(seed)
        assert problem.operands is not None
        wrong = mean_signed_deviation(problem.operands)
        assert wrong == 0
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.FORGOT_ABSOLUTE_VALUE


def test_data_set_lengths_vary() -> None:
    """Across seeds the data set takes more than one length (variable-length operands)."""
    lengths = {len(_problem(s).operands) for s in range(1, 60)}  # type: ignore[arg-type]
    assert len(lengths) >= 2
    assert lengths <= {4, 5, 6}


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_statement_lists_every_data_value() -> None:
    """The prompt text carries the full data set (values given in the prompt, not a widget)."""
    problem = _problem(5)
    assert problem.operands is not None
    for value in problem.operands:
        assert str(int(value)) in problem.statement


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_mad() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
