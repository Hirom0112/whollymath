"""Behavioral tests for KC_expression_parts — a Grade-6 (Unit 4) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Skill:
6.EE.2b — identify parts of an algebraic expression (name the COEFFICIENT, the CONSTANT,
or the number of TERMS). The answer is a single number entered in the existing NUMERIC
editor (NO new widget). An item-mode flag varies which part is asked.

Pins: the generator builds a clean, in-scope "parts of an expression" item in each of the
three modes; the verifier confirms the correct part and classifies the coefficient↔constant
confusion (answering the constant when the coefficient was asked, and vice versa); the
worked example lands on the answer; and generation is deterministic (PROJECT.md §4.1).
Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, confuse_coefficient_with_constant
from app.domain.problem_generators import (
    _MODE_COEFFICIENT,
    _MODE_CONSTANT,
    _MODE_TERM_COUNT,
    AnswerKind,
    Problem,
    generate_problem,
)
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.EXPRESSION_PARTS


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _mode(problem: Problem) -> int:
    assert problem.operands is not None
    return int(problem.operands[0])


def test_expression_parts_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_item_is_clean_and_in_scope() -> None:
    """The generator yields a NUMERIC item with operands (mode, coefficient, constant); the mode
    is one of the three; coefficient != constant (so the swap misconception is diagnostic)."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.kc is _KC
        assert problem.answer_kind is AnswerKind.NUMERIC
        assert problem.operands is not None and len(problem.operands) == 3
        mode, coefficient, constant = problem.operands
        assert int(mode) in (_MODE_COEFFICIENT, _MODE_CONSTANT, _MODE_TERM_COUNT)
        assert coefficient.q == 1 and constant.q == 1  # whole-number parts
        assert coefficient != constant  # coefficient↔constant swap is always distinguishable
        assert problem.correct_value.q == 1  # the answer is always a single whole number


def test_all_three_modes_are_generated() -> None:
    """Across seeds, every item-mode (coefficient / constant / term-count) appears."""
    modes = {_mode(_problem(seed)) for seed in range(1, 60)}
    assert modes == {_MODE_COEFFICIENT, _MODE_CONSTANT, _MODE_TERM_COUNT}


def test_coefficient_mode_answer_is_the_coefficient() -> None:
    """A coefficient-mode item's correct value equals the coefficient operand."""
    for seed in range(1, 60):
        problem = _problem(seed)
        if _mode(problem) == _MODE_COEFFICIENT:
            assert problem.operands is not None
            assert problem.correct_value == problem.operands[1]
            return
    raise AssertionError("no coefficient-mode item produced in seed range")


def test_constant_mode_answer_is_the_constant() -> None:
    """A constant-mode item's correct value equals the constant operand."""
    for seed in range(1, 60):
        problem = _problem(seed)
        if _mode(problem) == _MODE_CONSTANT:
            assert problem.operands is not None
            assert problem.correct_value == problem.operands[2]
            return
    raise AssertionError("no constant-mode item produced in seed range")


def test_term_count_mode_answer_is_at_least_two() -> None:
    """A term-count item's answer is the number of terms (always >= 2 for our expressions)."""
    for seed in range(1, 60):
        problem = _problem(seed)
        if _mode(problem) == _MODE_TERM_COUNT:
            assert problem.correct_value >= 2
            return
    raise AssertionError("no term-count-mode item produced in seed range")


def test_correct_answer_verifies_correct() -> None:
    """The correct part is graded correct by the tutor's own oracle, in every mode."""
    for seed in range(1, 60):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_coefficient_constant_confusion_is_classified() -> None:
    """Answering the constant for a coefficient question (or vice versa) is flagged OPERATION +
    the coefficient↔constant-confusion misconception — e.g. 4 instead of 7 for "coefficient of x
    in 7x + 4". Routed OPERATION: the learner read the wrong part of the expression (the wrong
    procedure for naming a part), not a magnitude misjudgment. Term-count items are NOT subject to
    this swap, so the model must not fire on them.
    """
    saw_coefficient_or_constant = False
    for seed in range(1, 60):
        problem = _problem(seed)
        assert problem.operands is not None
        mode = _mode(problem)
        wrong = confuse_coefficient_with_constant(problem.operands)
        if mode in (_MODE_COEFFICIENT, _MODE_CONSTANT):
            saw_coefficient_or_constant = True
            assert wrong is not None
            assert wrong != problem.correct_value
            result = verify(problem, str(wrong))
            assert not result.is_correct
            assert result.error_category is ErrorCategory.OPERATION
            assert result.matched_misconception is MisconceptionId.PART_CONFUSION
        else:  # term-count: the swap does not apply
            assert wrong is None
    assert saw_coefficient_or_constant


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency),
    in every mode."""
    seen: set[int] = set()
    for seed in range(1, 60):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value
        seen.add(_mode(problem))
    assert seen == {_MODE_COEFFICIENT, _MODE_CONSTANT, _MODE_TERM_COUNT}


def test_nudge_bank_covers_expression_parts() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
