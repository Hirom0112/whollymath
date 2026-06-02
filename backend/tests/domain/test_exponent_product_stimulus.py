"""Tests for the display-only EXPONENT repeated-product stimulus (base^exp as expanded x ... x).

The stimulus must be DERIVED from the same operands the prompt text is built from, so the picture
and the words can never disagree (the §8.4 anti-drift rule). These pins assert: it fires only for
KC_exponents; the base and exponent match the generator's operands; the factor list is the base
repeated exponent-many times; and it leaks no answer (it never states the evaluated power).
Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: 6.EE.1.
"""

from __future__ import annotations

from app.domain.exponent_product_stimulus import ExponentProductStimulus, exponent_product_for
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from sympy import Rational

_KC = KnowledgeComponentId.EXPONENTS


def test_no_stimulus_for_non_exponent_kcs() -> None:
    """Every KC except exponents carries no repeated-product view."""
    for kc in KnowledgeComponentId:
        if kc is _KC:
            continue
        assert exponent_product_for(kc, None) is None
        assert exponent_product_for(kc, ()) is None


def test_malformed_operands_draw_no_picture() -> None:
    """A missing / wrong-shaped operand tuple returns None rather than crashing (defensive)."""
    assert exponent_product_for(_KC, None) is None
    assert exponent_product_for(_KC, ()) is None
    assert exponent_product_for(_KC, (Rational(2),)) is None  # too short
    assert exponent_product_for(_KC, (Rational(2), Rational(0))) is None  # non-positive exponent


def test_factors_are_the_base_repeated_exponent_times() -> None:
    """2^4 expands to (2, 2, 2, 2); the factor list length equals the exponent."""
    stimulus = exponent_product_for(_KC, (Rational(2), Rational(4)))
    assert isinstance(stimulus, ExponentProductStimulus)
    assert stimulus.kind == "exponent_product"
    assert stimulus.base == 2
    assert stimulus.exponent == 4
    assert stimulus.factors == (2, 2, 2, 2)
    assert len(stimulus.factors) == stimulus.exponent
    assert all(f == stimulus.base for f in stimulus.factors)


def test_stimulus_matches_the_generated_operands() -> None:
    """Base/exponent in the picture equal the generator's operands; factors are base x exp times."""
    for seed in range(1, 40):
        problem = generate_problem(_KC, seed)
        assert problem.operands is not None
        base, exponent = int(problem.operands[0]), int(problem.operands[1])
        stimulus = exponent_product_for(problem.kc, problem.operands)
        assert isinstance(stimulus, ExponentProductStimulus)
        assert stimulus.base == base
        assert stimulus.exponent == exponent
        assert stimulus.factors == tuple(base for _ in range(exponent))


def test_stimulus_shows_input_form_not_the_value() -> None:
    """The picture holds the expanded product (the input), never the evaluated power (§8.2)."""
    for seed in range(1, 20):
        problem = generate_problem(_KC, seed)
        assert problem.operands is not None
        base, exponent = int(problem.operands[0]), int(problem.operands[1])
        stimulus = exponent_product_for(problem.kc, problem.operands)
        assert isinstance(stimulus, ExponentProductStimulus)
        value = base**exponent
        # No field of the stimulus equals the answer (the expanded factors stay the input form).
        assert stimulus.base != value or base == value  # base only equals value when exp == 1
        assert value not in stimulus.factors or base == value
        # The product of the factors would BE the answer — assert we never store that product.
        assert not hasattr(stimulus, "value")
        assert not hasattr(stimulus, "result")
