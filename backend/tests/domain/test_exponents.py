"""Behavioral tests for KC_exponents — a Grade-6 (Unit 4) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope "evaluate base^exp" item; the verifier confirms the
correct power and classifies the multiply-base-by-exponent misconception (3^4 -> 12 instead of
81 — repeated multiplication mistaken for one multiplication); the worked example lands on the
answer; generation is deterministic (PROJECT.md §4.1); and the KC is MASTERABLE — it offers two
REAL live surfaces (SYMBOLIC + AREA_MODEL) answered with the same numeric value, so the §3.4
rule-2 representation-diversity gate is reachable live. Mandatory-TDD domain Layer 1
(CLAUDE.md §2). Skill: 6.EE.1 — evaluate whole-number exponents.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, multiply_base_by_exponent
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import is_masterable_live, live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.EXPONENTS


def _problem(seed: int, surface: Representation | None = None) -> Problem:
    return generate_problem(_KC, seed, surface)


def test_exponents_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_power_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with (base, exp) operands; answer = base**exp.

    The base >= 2 and exp >= 2 (excluding base == 2 and exp == 2), so the correct power
    (base**exp) always differs from the multiply slip (base*exp) — keeping the misconception
    diagnostic.
    """
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    base, exp = problem.operands
    assert base >= 2 and exp >= 2
    assert not (base == 2 and exp == 2)
    assert all(operand.q == 1 for operand in problem.operands)  # whole-number operands
    assert problem.correct_value == base**exp


def test_correct_power_verifies_correct() -> None:
    """The repeated-multiplication value (base**exp) is graded correct by the tutor's oracle."""
    for seed in range(1, 16):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_multiply_base_by_exponent_is_classified() -> None:
    """The base*exp value is flagged OPERATION + the multiply-base-by-exponent misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG PROCEDURE — multiplied the
    base BY the exponent once (3^4 -> 3*4 = 12) instead of multiplying the base by itself exp
    times (3*3*3*3 = 81). The slip value base*exp is always DISTINCT from the correct base**exp
    in the generator's scope (base >= 2, exp >= 2, excluding the single 2^2 = 2*2 collision).
    """
    for seed in range(1, 16):
        problem = _problem(seed)
        assert problem.operands is not None
        base, exp = problem.operands
        wrong = multiply_base_by_exponent(int(base), int(exp))
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.MULTIPLY_BASE_BY_EXPONENT


def test_two_live_surfaces_share_the_same_numeric_answer() -> None:
    """SYMBOLIC and AREA_MODEL are BOTH live and answered with the same value (masterable).

    The two surfaces reframe the SAME base^exp item (the area/volume picture vs. the symbolic
    power); the operands and correct value are identical, only the statement differs. This is the
    representation-agnostic answer that makes §3.4 rule 2 reachable live.
    """
    assert set(live_representations(_KC)) == {Representation.SYMBOLIC, Representation.AREA_MODEL}
    assert is_masterable_live(_KC)
    for seed in range(1, 16):
        symbolic = _problem(seed, Representation.SYMBOLIC)
        area = _problem(seed, Representation.AREA_MODEL)
        assert symbolic.operands == area.operands
        assert symbolic.correct_value == area.correct_value
        assert symbolic.statement != area.statement  # genuinely different framing
        for problem in (symbolic, area):
            assert verify(problem, str(problem.correct_value)).is_correct


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_exponents() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
