"""Tests for the unified scene dispatcher (app.domain.scene.scene_for).

Pins that each scene-bearing KC routes to the right display-only scene type, that a KC with no
picture returns None, and that the per-KC derivers are disjoint (no operand tuple ever matches two
derivers). The individual scene shapes/answer-leak guards are covered by each scene's own tests.
"""

from __future__ import annotations

from app.domain.decimal_place_value_stimulus import DecimalPlaceValueStimulus
from app.domain.exponent_product_stimulus import ExponentProductStimulus
from app.domain.fraction_area_stimulus import FractionAreaStimulus
from app.domain.gcf_factors_stimulus import GcfFactorsStimulus
from app.domain.integer_line_stimulus import (
    AbsoluteValueStimulus,
    IntegerJumpStimulus,
    SignedPointStimulus,
)
from app.domain.knowledge_components import KnowledgeComponentId as KC  # noqa: N814
from app.domain.percent_grid_stimulus import PercentGridStimulus
from app.domain.problem_generators import generate_problem
from app.domain.ratio_table_stimulus import RatioTableStimulus
from app.domain.scene import scene_for

_EXPECTED: dict[KC, type | tuple[type, ...]] = {
    KC.PERCENT: PercentGridStimulus,
    KC.UNIT_RATE: RatioTableStimulus,
    KC.EQUIVALENT_RATIOS: RatioTableStimulus,
    KC.INTEGER_ADD_SUBTRACT: IntegerJumpStimulus,
    KC.ABSOLUTE_VALUE: AbsoluteValueStimulus,
    KC.SIGNED_NUMBERS: SignedPointStimulus,
    KC.ADDITION_UNLIKE: FractionAreaStimulus,
    KC.SUBTRACTION_UNLIKE: FractionAreaStimulus,
    KC.MULTIPLY_FRACTIONS: FractionAreaStimulus,
    KC.DIVIDE_FRACTIONS: FractionAreaStimulus,
    KC.DECIMAL_OPERATIONS: DecimalPlaceValueStimulus,
    KC.GCF_LCM: GcfFactorsStimulus,
    KC.EXPONENTS: ExponentProductStimulus,
}


def test_each_scene_kc_routes_to_its_scene_type() -> None:
    """A generated problem for each scene-bearing KC yields the expected scene dataclass."""
    for kc, expected in _EXPECTED.items():
        problem = generate_problem(kc, 7)
        scene = scene_for(problem.kc, problem.operands)
        assert scene is not None, f"{kc} should carry a scene"
        assert isinstance(scene, expected), f"{kc} -> {type(scene).__name__}, want {expected}"


def test_non_scene_kc_has_no_scene() -> None:
    """A KC with no picture (number-line placement is its own interactive widget) returns None."""
    problem = generate_problem(KC.NUMBER_LINE_PLACEMENT, 3)
    assert scene_for(problem.kc, problem.operands) is None


def test_derivers_are_disjoint() -> None:
    """At most one deriver matches any scene-bearing problem (no double-claim across seeds)."""
    from app.domain.scene import _DERIVERS

    for kc in _EXPECTED:
        for seed in range(1, 12):
            problem = generate_problem(kc, seed)
            matches = [d for d in _DERIVERS if d(problem.kc, problem.operands) is not None]
            assert len(matches) == 1, f"{kc} seed {seed}: {len(matches)} derivers matched"
