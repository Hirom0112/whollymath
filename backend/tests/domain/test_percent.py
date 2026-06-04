"""Behavioral tests for KC_percent — Grade-6 Unit 1 (2026-05-30).

Exercises the KC through the SAME oracle the tutor uses (the SymPy verifier). Pins: the
generator builds BOTH directions of 6.RP.3c — "what is p% of whole?" (percent-of) AND "{part}
is p% of what number?" (find-the-whole) — selected by a seeded mode flag; the verifier confirms
the correct value and flags the percent-as-amount misconception ONLY on the percent-of direction
(answering the percent itself); the worked example lands on the answer for both directions;
generation is deterministic. Mandatory-TDD domain Layer 1 (CLAUDE.md §2).

The find-the-whole direction was added 2026-06-04 (Slice 4b) after a curriculum panel flagged that
6.RP.3c requires finding the WHOLE given a part and a percent, not only the part. The operand shape
is ``(percent, whole, mode)`` mirroring the KC_decimal_operations ``(first, second, mode)`` pattern.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId
from app.domain.problem_generators import (
    _PERCENT_FIND_WHOLE,
    _PERCENT_OF,
    AnswerKind,
    Problem,
    generate_problem,
)
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.PERCENT

# Span enough seeds that BOTH modes are exercised (the generator picks the mode from the seeded
# RNG, so a single seed only covers one direction).
_SEEDS = range(1, 40)


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _mode(problem: Problem) -> int:
    assert problem.operands is not None
    return int(problem.operands[2])


def test_percent_is_live() -> None:
    assert _KC in LIVE_KCS


def test_operand_shape_is_percent_whole_mode() -> None:
    """Every percent item carries (percent, whole, mode) — the decimal-operations shape."""
    for seed in _SEEDS:
        problem = _problem(seed)
        assert problem.kc is _KC
        assert problem.answer_kind is AnswerKind.NUMERIC
        assert problem.operands is not None and len(problem.operands) == 3
        assert _mode(problem) in (_PERCENT_OF, _PERCENT_FIND_WHOLE)


def test_both_modes_appear_across_seeds() -> None:
    """The seeded mode flag yields BOTH directions of 6.RP.3c over a span of seeds."""
    modes = {_mode(_problem(seed)) for seed in _SEEDS}
    assert _PERCENT_OF in modes
    assert _PERCENT_FIND_WHOLE in modes


def test_percent_of_correct_value_is_p_times_whole_over_100() -> None:
    """percent-of (mode 0): answer is p*whole/100; statement asks 'what is p% of whole?'."""
    for seed in _SEEDS:
        problem = _problem(seed)
        if _mode(problem) != _PERCENT_OF:
            continue
        assert problem.operands is not None
        percent, whole = int(problem.operands[0]), int(problem.operands[1])
        assert problem.correct_value == Rational(percent * whole, 100)
        assert f"{percent}% of {whole}" in problem.statement


def test_find_whole_answer_is_the_whole_and_part_is_a_positive_integer() -> None:
    """find-the-whole (mode 1): answer is the whole; the stated part is a positive whole number."""
    for seed in _SEEDS:
        problem = _problem(seed)
        if _mode(problem) != _PERCENT_FIND_WHOLE:
            continue
        assert problem.operands is not None
        percent, whole = int(problem.operands[0]), int(problem.operands[1])
        # The answer is the WHOLE itself, recoverable from operands[1].
        assert problem.correct_value == Rational(whole)
        # part = p% of whole must be a positive whole number so the prompt reads cleanly.
        part = Rational(percent * whole, 100)
        assert part.q == 1
        assert part.p > 0
        assert f"{part.p} is {percent}% of what number?" == problem.statement


def test_correct_value_verifies_correct_both_modes() -> None:
    for seed in _SEEDS:
        problem = _problem(seed)
        assert verify(problem, str(problem.correct_value)).is_correct


def test_percent_as_amount_is_classified_on_percent_of() -> None:
    """Answering the percent NUMBER itself is flagged OPERATION + percent-as-amount (mode 0)."""
    saw_percent_of = False
    for seed in _SEEDS:
        problem = _problem(seed)
        if _mode(problem) != _PERCENT_OF:
            continue
        saw_percent_of = True
        assert problem.operands is not None
        percent = int(problem.operands[0])
        # The generator excludes whole == 100, so the percent itself is always wrong here.
        assert Rational(percent) != problem.correct_value
        result = verify(problem, str(percent))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.PERCENT_AS_AMOUNT
    assert saw_percent_of


def test_percent_as_amount_is_inert_on_find_the_whole() -> None:
    """The percent-as-amount misconception is percent-of-specific: it must NOT fire on find-whole.

    Answering the percent number ``p`` on a find-the-whole item (where the answer is the whole) is
    a wrong answer, but it is NOT the percent-as-amount error (there is no 'percent OF the whole' to
    skip). The verifier must report OTHER, not a false percent-as-amount match.
    """
    saw_find_whole = False
    for seed in _SEEDS:
        problem = _problem(seed)
        if _mode(problem) != _PERCENT_FIND_WHOLE:
            continue
        saw_find_whole = True
        assert problem.operands is not None
        percent = int(problem.operands[0])
        result = verify(problem, str(percent))
        # ``p`` may or may not coincide with the whole; only assert the misconception when wrong.
        if not result.is_correct:
            assert result.matched_misconception is not MisconceptionId.PERCENT_AS_AMOUNT
    assert saw_find_whole


def test_correct_find_whole_answer_is_not_flagged_as_a_misconception() -> None:
    """A correct find-the-whole answer (the whole) is accepted, never mislabeled an error."""
    for seed in _SEEDS:
        problem = _problem(seed)
        if _mode(problem) != _PERCENT_FIND_WHOLE:
            continue
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.matched_misconception is None


def test_generation_is_deterministic() -> None:
    for seed in (2, 8, 13, 21):
        assert generate_problem(_KC, seed).statement == generate_problem(_KC, seed).statement
        assert (
            generate_problem(_KC, seed).correct_value == generate_problem(_KC, seed).correct_value
        )
        assert generate_problem(_KC, seed).operands == generate_problem(_KC, seed).operands


def test_worked_example_lands_on_the_answer_both_modes() -> None:
    saw_percent_of = False
    saw_find_whole = False
    for seed in _SEEDS:
        problem = _problem(seed)
        assert worked_example_for(problem).final_value == problem.correct_value
        if _mode(problem) == _PERCENT_OF:
            saw_percent_of = True
        else:
            saw_find_whole = True
    assert saw_percent_of and saw_find_whole


def test_nudge_bank_covers_percent() -> None:
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
