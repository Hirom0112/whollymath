"""Behavioral tests for KC_multi_digit_division — Grade-6 Unit 2 (2026-05-30).

Exercises the KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a CLEAN exact-division problem (the divisor divides the dividend
evenly, so the quotient is a single integer); the verifier confirms the correct quotient
and classifies the place-value-slip misconception (an answer off by a factor of 10 — the
right digits in the wrong place, the classic long-division zero-drop); the worked example
lands on the answer; and generation is deterministic (PROJECT.md §4.1). Mandatory-TDD
domain Layer 1 (CLAUDE.md §2).

A note on the MAGNITUDE error category: a place-value slip produces the right digit string
at the wrong SIZE (e.g. 24 for 240) — the learner ran the right procedure but misplaced the
quotient digit, a misjudged MAGNITUDE, not a wrong operation. So it routes to MAGNITUDE,
matching the number-line natural-number-bias precedent (also a magnitude misjudgment;
verifier.py). The slipped answer is always quotient * 10, which is never the correct value
(the quotient is >= 1), so the misconception is a genuinely wrong answer on every item.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, place_value_slip
from app.domain.problem_generators import AnswerKind, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.MULTI_DIGIT_DIVISION


def _problem(seed: int):  # type: ignore[no-untyped-def]
    return generate_problem(_KC, seed)


def test_multi_digit_division_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_problem_is_a_clean_exact_division() -> None:
    """A numeric item: (dividend, divisor) operands whose exact quotient is the integer answer."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    dividend, divisor = int(problem.operands[0]), int(problem.operands[1])
    assert divisor != 0
    assert dividend % divisor == 0  # exact division — a clean single-integer quotient
    assert problem.correct_value == Rational(dividend // divisor)
    assert problem.correct_value.q == 1  # a whole-number answer
    assert problem.correct_value >= 1


def test_correct_quotient_verifies_correct() -> None:
    """The SymPy quotient is graded correct by the tutor's own oracle."""
    for seed in range(1, 30):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_place_value_slip_is_classified() -> None:
    """An answer off by a factor of 10 (the long-division zero-slip) is flagged MAGNITUDE +
    place-value-slip — the misconception the lesson is designed to surface."""
    for seed in range(1, 30):
        problem = _problem(seed)
        dividend, divisor = int(problem.operands[0]), int(problem.operands[1])
        slipped = place_value_slip(dividend, divisor)
        assert slipped != problem.correct_value  # off by a factor of 10, so always wrong
        result = verify(problem, str(slipped))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.MAGNITUDE
        assert result.matched_misconception is MisconceptionId.PLACE_VALUE_SLIP


def test_place_value_slip_helper_is_ten_times_the_quotient() -> None:
    """The helper is exactly the quotient with a zero appended (digits right, magnitude wrong)."""
    assert place_value_slip(240, 6) == Rational(400)  # 240 / 6 = 40, slipped to 400
    assert place_value_slip(144, 12) == Rational(120)  # 144 / 12 = 12, slipped to 120


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def _dividend(seed: int, difficulty: int) -> int:
    """The sampled dividend (operands[0]) at a difficulty tier — narrows the optional operands."""
    operands = generate_problem(_KC, seed, difficulty=difficulty).operands
    assert operands is not None
    return int(operands[0])


def test_difficulty_widens_the_dividend() -> None:
    """Higher tiers reach larger dividends (the easy→hard ramp; CP.B)."""
    easy = {_dividend(s, difficulty=1) for s in range(40)}
    hard = {_dividend(s, difficulty=4) for s in range(40)}
    assert max(hard) > max(easy)


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in (3, 8):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_multi_digit_division() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
