"""Contract tests for the per-lesson spec (Slice HR.A1).

The gate's promise is that EVERY lesson spec satisfies the hyperreactive contract, so the engine
can read the spec uniformly. We parametrize over the whole registry and assert each invariant, plus
the registry/accessor behavior and the spec's bound generator.
"""

from __future__ import annotations

import pytest
from app.domain.knowledge_components import KnowledgeComponentId, get_kc
from app.domain.lesson_spec import (
    LESSON_SPEC_REGISTRY,
    LessonSpec,
    WidgetId,
    get_lesson_spec,
)
from app.domain.misconceptions import get_misconception

_ALL_SPECS = LESSON_SPEC_REGISTRY.all()
_FRACTION_KCS = {
    KnowledgeComponentId.EQUIVALENCE,
    KnowledgeComponentId.COMMON_DENOMINATOR,
    KnowledgeComponentId.ADDITION_UNLIKE,
    KnowledgeComponentId.SUBTRACTION_UNLIKE,
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
}


def test_registry_covers_the_five_fraction_kcs() -> None:
    assert {s.kc for s in _ALL_SPECS} == _FRACTION_KCS


def test_get_lesson_spec_accepts_enum_and_string() -> None:
    spec = get_lesson_spec(KnowledgeComponentId.EQUIVALENCE)
    assert spec.kc is KnowledgeComponentId.EQUIVALENCE
    assert get_lesson_spec("KC_equivalence") is spec


def test_get_lesson_spec_raises_for_unknown_kc() -> None:
    # An unknown KC string is a hard error (invalid enum value before the registry lookup).
    with pytest.raises((KeyError, ValueError)):
        get_lesson_spec("KC_not_a_real_kc")


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_spec_offers_at_least_two_representations(spec: LessonSpec) -> None:
    """§3.4 rule 2: a hyperreactive lesson must adapt across ≥2 representations."""
    assert len(spec.representations) >= 2
    assert len(set(spec.representations)) == len(spec.representations)  # no duplicates


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_representations_match_the_kc_registry(spec: LessonSpec) -> None:
    assert spec.representations == get_kc(spec.kc).representations


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_every_representation_has_a_widget(spec: LessonSpec) -> None:
    """Routing can only target a REAL widget — every representation must map to one."""
    assert len(spec.widgets) == len(spec.representations)
    for rep in spec.representations:
        assert isinstance(spec.widget_for(rep), WidgetId)


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_error_routes_target_an_offered_representation(spec: LessonSpec) -> None:
    """The core invariant: an error never routes to a representation the lesson doesn't render."""
    assert spec.error_routes  # at least one route
    for route in spec.error_routes:
        assert route.representation in spec.representations
        assert route.label.strip()


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_misconceptions_are_present_and_applicable(spec: LessonSpec) -> None:
    assert spec.misconceptions  # a hyperreactive lesson exhibits at least one misconception
    for mid in spec.misconceptions:
        assert spec.kc in get_misconception(mid).applicable_kcs


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_transfer_probe_draws_from_offered_representations(spec: LessonSpec) -> None:
    assert spec.transfer_probe.probe_representations
    assert set(spec.transfer_probe.probe_representations) <= set(spec.representations)


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_difficulty_tiers_present(spec: LessonSpec) -> None:
    assert spec.difficulty_tiers


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_bound_generator_produces_a_problem_for_this_kc(spec: LessonSpec) -> None:
    problem = spec.generate(seed=7)
    assert problem.kc is spec.kc
    # Deterministic in the seed.
    assert spec.generate(seed=7).problem_id == problem.problem_id


def test_codes_are_resolved_where_the_curriculum_has_them() -> None:
    """At least one spec resolves a real CCSS code from the catalog (proves wiring is real)."""
    assert any(s.ccss_code is not None for s in _ALL_SPECS)
