"""Behavioral tests for KC_absolute_value — Grade-6 Unit 3 (2026-05-30).

Exercises the KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator asks for the absolute value of an integer (distance from 0), with a single
integer answer; the verifier confirms |x| and classifies the "absolute value of a negative
stays negative" misconception (returning the signed input itself — conflating magnitude with
signed order); the worked example lands on the answer; and generation is deterministic
(PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2).

A note on the MAGNITUDE error category: absolute value IS a magnitude (distance from 0), and
the modeled error keeps the sign — reporting the signed value instead of its size. That is a
misjudged MAGNITUDE (the learner conflates "how far from 0" with the signed number / its order
on the line), not a wrong operation, so it routes to MAGNITUDE — matching the number-line
natural-number-bias precedent (also a magnitude misjudgment; verifier.py). Inputs are kept
strictly negative so the signed value (= the wrong answer) always differs from |x|, making the
misconception a genuinely wrong answer on every item.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, signed_not_magnitude
from app.domain.problem_generators import AnswerKind, generate_problem
from app.domain.scene import scene_for
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.ABSOLUTE_VALUE


def _problem(seed: int):  # type: ignore[no-untyped-def]
    return generate_problem(_KC, seed)


def test_absolute_value_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_number_line_is_the_same_item_with_a_picture() -> None:
    """NUMBER_LINE serves the SAME scalar answer as SYMBOLIC (same operands + value), now with a
    distance-from-zero scene attached — the masterable second representation, no new input widget.
    Absolute value IS a distance, so the line is the canonical picture (panel audit 2026-06-04)."""
    sym = generate_problem(_KC, seed=5, surface_format=Representation.SYMBOLIC)
    line = generate_problem(_KC, seed=5, surface_format=Representation.NUMBER_LINE)
    assert line.surface_format is Representation.NUMBER_LINE
    assert line.operands == sym.operands
    assert line.correct_value == sym.correct_value
    assert scene_for(_KC, line.operands) is not None


def test_generated_problem_is_a_negative_input_with_positive_answer() -> None:
    """A numeric item: one (negative) integer operand whose absolute value is the answer."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 1
    value = int(problem.operands[0])
    assert value < 0  # inputs are negative so |x| differs from x (the misconception is wrong)
    assert problem.correct_value == Rational(abs(value))
    assert problem.correct_value.q == 1 and problem.correct_value > 0


def test_correct_absolute_value_verifies_correct() -> None:
    """The SymPy absolute value is graded correct by the tutor's own oracle."""
    for seed in range(1, 30):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_signed_not_magnitude_is_classified() -> None:
    """Reporting the signed value itself (|-7| -> -7) is flagged MAGNITUDE + signed-not-magnitude —
    the "abs of a negative stays negative" misconception the lesson is designed to surface."""
    for seed in range(1, 30):
        problem = _problem(seed)
        value = int(problem.operands[0])
        wrong = signed_not_magnitude(value)
        assert wrong != problem.correct_value  # the signed value, so always wrong here
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.MAGNITUDE
        assert result.matched_misconception is MisconceptionId.SIGNED_NOT_MAGNITUDE


def test_signed_not_magnitude_helper_returns_the_signed_value() -> None:
    """The helper is exactly the (signed) input — the learner left the sign on the magnitude."""
    assert signed_not_magnitude(-7) == Rational(-7)
    assert signed_not_magnitude(-3) == Rational(-3)


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_difficulty_widens_the_magnitude() -> None:
    """Higher tiers reach larger magnitudes (the easy→hard ramp; CP.B)."""
    easy = {_magnitude(s, difficulty=1) for s in range(40)}
    hard = {_magnitude(s, difficulty=4) for s in range(40)}
    assert max(hard) > max(easy)


def _magnitude(seed: int, difficulty: int) -> int:
    """The |value| the generator samples at a difficulty tier — narrows the optional operands."""
    operands = generate_problem(_KC, seed, difficulty=difficulty).operands
    assert operands is not None
    return abs(int(operands[0]))


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in (3, 8):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_absolute_value() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
