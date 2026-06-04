"""Behavioral tests for KC_decimal_operations — Grade-6 Unit 2 (2026-05-30).

Multiply decimals and read the answer's place value (CCSS 6.NS.3 / TEKS 6.3E). Exercises
the KC through the SAME oracle the tutor uses (the SymPy verifier), so "correct"/"wrong"
means exactly what it means in production (ARCHITECTURE.md §9). Pins: the generator builds a
clean, in-scope decimal product; the verifier confirms the correct product (entered as a
DECIMAL string — the capability added in the prior commit) and classifies the
decimal-point-misplacement misconception; the worked example lands on the answer; and
generation is deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2).

Misconception classification choice (justified): point-misplacement leaves the DIGITS right
but the SIZE wrong — the wrong value is the correct one off by a power of ten — so it is a
MAGNITUDE error (routes to the size-exposing surface, §3.6), not OPERATION. The lead's brief
explicitly allows MAGNITUDE "if the value is off by a power of ten"; it is, by construction.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, decimal_point_misplacement
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.scene import scene_for
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.DECIMAL_OPERATIONS


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_decimal_operations_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_area_model_is_the_same_item_with_a_picture() -> None:
    """AREA_MODEL serves the SAME numeric answer as SYMBOLIC (same operands + value), now with a
    place-value display scene attached — the masterable second representation, no new input widget
    (EVALUATE_EXPRESSIONS pattern). Closes the practice-only gap flagged in the panel audit
    (2026-06-04)."""
    sym = generate_problem(_KC, seed=5, surface_format=Representation.SYMBOLIC)
    area = generate_problem(_KC, seed=5, surface_format=Representation.AREA_MODEL)
    assert area.surface_format is Representation.AREA_MODEL
    assert area.operands == sym.operands
    assert area.correct_value == sym.correct_value
    assert scene_for(_KC, area.operands) is not None


def test_generated_decimal_product_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with two decimal operands and a positive product."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    a, b = problem.operands
    assert problem.correct_value == a * b
    assert problem.correct_value > 0
    # Both operands are genuine decimals (denominator a power of ten > 1), so point placement
    # in the product is non-trivial — what makes the misplacement error diagnostic.
    assert a.q > 1 and b.q > 1


def test_correct_decimal_product_verifies_correct_as_a_decimal_string() -> None:
    """The product, typed as a DECIMAL string, is graded correct by the tutor's own oracle.

    This is the end-to-end payoff of the verifier decimal-parsing commit: the natural answer
    form for a decimal lesson now grades correctly.
    """
    for seed in range(1, 12):
        problem = _problem(seed)
        value = problem.correct_value
        # Render the exact rational as a finite decimal string (its denominator is a power of 10).
        decimal_text = _as_decimal_string(value)
        assert Rational(decimal_text) == value  # the rendering is exact (sanity)
        result = verify(problem, decimal_text)
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_point_misplacement_is_classified_as_magnitude() -> None:
    """The misplaced product (off by a power of ten) is flagged MAGNITUDE + the misconception."""
    for seed in range(1, 12):
        problem = _problem(seed)
        assert problem.operands is not None
        a, b = problem.operands
        wrong = decimal_point_misplacement(a, b)
        # The misplacement is genuinely a DIFFERENT, wrong value (off by a power of ten > 1).
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.MAGNITUDE
        assert result.matched_misconception is MisconceptionId.DECIMAL_POINT_MISPLACEMENT


def test_misplacement_is_off_by_a_power_of_ten() -> None:
    """The modeled wrong value is the correct one scaled by a power of ten (the magnitude tell)."""
    problem = _problem(5)
    assert problem.operands is not None
    a, b = problem.operands
    wrong = decimal_point_misplacement(a, b)
    ratio = wrong / problem.correct_value
    # ratio is a power of ten (here >= 10, since both operands have >= 1 decimal place).
    assert ratio == int(ratio) and int(ratio) % 10 == 0


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_decimal_operations() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def _as_decimal_string(value: Rational) -> str:
    """Render an exact rational with a power-of-ten denominator as a finite decimal string.

    Helper for the test only (the production answer would come from the UI). Uses Python's
    exact integer arithmetic, never a float, so the rendering itself introduces no fuzz.
    """
    den = value.q
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    assert den == 1, "a decimal product is a terminating decimal by construction"
    places = max(twos, fives)
    if places == 0:
        return str(value.p)
    scaled = int(value * (10**places))  # exact — value has exactly ``places`` decimal places
    digits = str(scaled).zfill(places + 1)
    return f"{digits[:-places]}.{digits[-places:]}"
