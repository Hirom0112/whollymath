"""One front door for every display-only problem "scene".

Each KC family that benefits from a picture has its own deriver module (percent_grid_stimulus,
ratio_table_stimulus, integer_line_stimulus, fraction_area_stimulus, decimal_place_value_stimulus,
gcf_factors_stimulus, exponent_product_stimulus), each a pure projection of a problem's ``operands``
into a renderable, DISPLAY-ONLY dataclass (the question input, never the answer — §8.2; single
source of truth from operands — §8.4). This module unifies them: ``scene_for(kc, operands)`` asks
each
deriver in turn and returns the first scene that matches, so the API and surface have ONE slot
(``ProblemView.scene``) and a new scene plugs in by adding its deriver here.

Each deriver returns ``None`` for any KC it does not own, and the KC→deriver mapping is disjoint
(every KC is owned by at most one deriver), so the order below does not change the result. No LLM,
no SymPy decision-making — pure data projection (CLAUDE.md §7, §8.2).
"""

from __future__ import annotations

from collections.abc import Callable

from sympy import Rational

from app.domain.decimal_place_value_stimulus import (
    DecimalPlaceValueStimulus,
    decimal_place_value_for,
)
from app.domain.exponent_product_stimulus import ExponentProductStimulus, exponent_product_for
from app.domain.fraction_area_stimulus import FractionAreaStimulus, fraction_area_for
from app.domain.gcf_factors_stimulus import GcfFactorsStimulus, gcf_factors_for
from app.domain.integer_line_stimulus import IntegerLineStimulus, integer_line_for
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.percent_grid_stimulus import PercentGridStimulus, percent_grid_for
from app.domain.ratio_table_stimulus import RatioTableStimulus, ratio_table_for

# Every display-only scene a problem can carry (each is itself answer-free). A union so the API
# projection and the surface can switch on the scene's ``kind``.
Scene = (
    PercentGridStimulus
    | RatioTableStimulus
    | IntegerLineStimulus
    | FractionAreaStimulus
    | DecimalPlaceValueStimulus
    | GcfFactorsStimulus
    | ExponentProductStimulus
)

_DERIVERS: tuple[
    Callable[[KnowledgeComponentId, tuple[Rational, ...] | None], Scene | None], ...
] = (
    percent_grid_for,
    ratio_table_for,
    integer_line_for,
    fraction_area_for,
    decimal_place_value_for,
    gcf_factors_for,
    exponent_product_for,
)


def scene_for(kc: KnowledgeComponentId, operands: tuple[Rational, ...] | None) -> Scene | None:
    """The display-only scene for a problem, or ``None`` when its KC has no picture.

    Asks each deriver in turn; returns the first non-``None`` scene. The mapping is disjoint, so at
    most one deriver ever matches.
    """
    for derive in _DERIVERS:
        scene = derive(kc, operands)
        if scene is not None:
            return scene
    return None
