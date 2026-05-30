"""Unit tests for spec-driven signal routing (Slice HR.A3).

Pins that routing reads the lesson spec's error_routes (not a KC branch), that every routed
representation maps to a real surface state, and that the primary remediation representation
reproduces the §3.6 KC→S2/S3 mapping for the 5 fraction lessons.
"""

from __future__ import annotations

import pytest
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.lesson_spec import LESSON_SPEC_REGISTRY, get_lesson_spec
from app.domain.verifier import ErrorCategory
from app.policy.signal_routing import (
    next_representation_on_correct,
    primary_remediation_representation,
    representation_for_error,
    surface_state_for_representation,
)
from app.policy.surface_states import SurfaceState

_ALL_SPECS = LESSON_SPEC_REGISTRY.all()


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_representation_for_error_matches_a_declared_route(spec) -> None:  # type: ignore[no-untyped-def]
    for route in spec.error_routes:
        assert representation_for_error(spec, route.error_category) is route.representation


def test_representation_for_error_is_none_for_unrouted_category() -> None:
    spec = get_lesson_spec(KnowledgeComponentId.EQUIVALENCE)
    # EQUIVALENCE routes OPERATION/MAGNITUDE; NONE is never routed.
    assert representation_for_error(spec, ErrorCategory.NONE) is None


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_every_routed_representation_has_a_surface_state(spec) -> None:  # type: ignore[no-untyped-def]
    for route in spec.error_routes:
        assert surface_state_for_representation(route.representation) is not None


def test_surface_state_mapping_is_the_36_table() -> None:
    assert (
        surface_state_for_representation(Representation.NUMBER_LINE)
        is SurfaceState.NUMBER_LINE_PRIMARY
    )
    assert (
        surface_state_for_representation(Representation.AREA_MODEL)
        is SurfaceState.FRACTION_BARS_PRIMARY
    )
    assert surface_state_for_representation(Representation.SYMBOLIC) is SurfaceState.SYMBOLIC_FOCUS
    # WORD_PROBLEM is a framing, not a manipulative — no own surface state.
    assert surface_state_for_representation(Representation.WORD_PROBLEM) is None


def test_primary_remediation_reproduces_the_legacy_kc_routing() -> None:
    """The first error route per spec must reproduce the old KC→S2/S3 transfer-fail mapping."""
    # Number-line placement is the magnitude skill → S2 (number line).
    nl = get_lesson_spec(KnowledgeComponentId.NUMBER_LINE_PLACEMENT)
    assert (
        surface_state_for_representation(primary_remediation_representation(nl))
        is SurfaceState.NUMBER_LINE_PRIMARY
    )
    # The operative KCs → S3 (fraction bars).
    for kc in (
        KnowledgeComponentId.EQUIVALENCE,
        KnowledgeComponentId.COMMON_DENOMINATOR,
        KnowledgeComponentId.ADDITION_UNLIKE,
        KnowledgeComponentId.SUBTRACTION_UNLIKE,
    ):
        spec = get_lesson_spec(kc)
        assert (
            surface_state_for_representation(primary_remediation_representation(spec))
            is SurfaceState.FRACTION_BARS_PRIMARY
        )


def test_fade_target_is_symbolic() -> None:
    assert next_representation_on_correct() is Representation.SYMBOLIC
