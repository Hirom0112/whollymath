"""Contract tests for the per-lesson spec (Slice HR.A1).

The gate's promise is that EVERY lesson spec satisfies the hyperreactive contract, so the engine
can read the spec uniformly. We parametrize over the whole registry and assert each invariant, plus
the registry/accessor behavior and the spec's bound generator.
"""

from __future__ import annotations

import pytest
from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc
from app.domain.lesson_spec import (
    LESSON_SPEC_REGISTRY,
    LessonSpec,
    WidgetId,
    get_lesson_spec,
    widget_for_representation,
)
from app.domain.misconceptions import get_misconception
from app.policy.scheduler import live_representations

_ALL_SPECS = LESSON_SPEC_REGISTRY.all()

# The KCs whose canonical SYMBOLIC answer is a numerator-over-denominator FRACTION (the two-box
# fraction editor). Every OTHER SYMBOLIC + NUMERIC KC answers with a SCALAR (a plain integer,
# decimal, or negative — or, for the mixed stats KCs, an exact a/b) and gets the single-box
# NUMBER_ENTRY. Pinned here independently of the implementation so a future edit to the set is a
# deliberate, test-visible decision (these are the genuine fraction-answer KCs verified against the
# canonical answers the generators emit). See lesson_spec._FRACTION_ANSWER_KCS.
_FRACTION_EDITOR_KCS = {
    KnowledgeComponentId.EQUIVALENCE,
    KnowledgeComponentId.ADDITION_UNLIKE,
    KnowledgeComponentId.SUBTRACTION_UNLIKE,
    KnowledgeComponentId.MULTIPLY_FRACTIONS,
    KnowledgeComponentId.DIVIDE_FRACTIONS,
    KnowledgeComponentId.RATIO_LANGUAGE,
    KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES,
}


def test_registry_covers_every_live_kc() -> None:
    """Every content-complete KC has a lesson spec, and only those — the engine reads a spec
    per live KC (HR.A1). Compares against LIVE_KCS so it holds as the Grade-6 build adds KCs."""
    from app.domain.knowledge_components import LIVE_KCS

    assert {s.kc for s in _ALL_SPECS} == LIVE_KCS


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


# ── SYMBOLIC fraction-vs-scalar widget tie-break (the number_entry routing fix) ──


def test_symbolic_fraction_kc_resolves_to_fraction_editor() -> None:
    """A SYMBOLIC fraction-answer KC keeps the two-box fraction editor."""
    assert (
        widget_for_representation(Representation.SYMBOLIC, KnowledgeComponentId.ADDITION_UNLIKE)
        is WidgetId.FRACTION_EDITOR
    )


def test_symbolic_scalar_kc_resolves_to_number_entry() -> None:
    """A SYMBOLIC scalar-answer KC (percent / an integer sum / a polygon area) gets the single-box
    NUMBER_ENTRY, NOT the fraction editor — the bug this fix closes (a plain/negative/decimal answer
    on a two-box fraction widget). Representative one per family."""
    for kc in (
        KnowledgeComponentId.PERCENT,
        KnowledgeComponentId.INTEGER_ADD_SUBTRACT,
        KnowledgeComponentId.AREA_POLYGONS,
    ):
        assert widget_for_representation(Representation.SYMBOLIC, kc) is WidgetId.NUMBER_ENTRY


def test_symbolic_without_kc_keeps_fraction_editor_default() -> None:
    """With no KC in hand the resolver keeps the representation-only default for SYMBOLIC."""
    assert widget_for_representation(Representation.SYMBOLIC) is WidgetId.FRACTION_EDITOR


def test_non_symbolic_widget_is_unaffected_by_kc() -> None:
    """The KC tie-break only touches SYMBOLIC; other representations map 1:1 regardless of KC."""
    assert (
        widget_for_representation(
            Representation.NUMBER_LINE, KnowledgeComponentId.NUMBER_LINE_PLACEMENT
        )
        is WidgetId.NUMBER_LINE
    )
    assert (
        widget_for_representation(Representation.COORDINATE_PLANE, KnowledgeComponentId.PERCENT)
        is WidgetId.COORDINATE_PLANE
    )


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda s: s.kc.value)
def test_live_symbolic_kc_emits_the_right_widget_id(spec: LessonSpec) -> None:
    """For every live KC whose first live representation is SYMBOLIC, the widget it emits is
    FRACTION_EDITOR iff the KC is a genuine fraction-answer KC, else NUMBER_ENTRY — so no scalar KC
    can render the two-box fraction editor and no fraction KC loses it. This is the per-problem
    widget_id the wire ships (service._problem_view passes the same (surface_format, kc))."""
    live_rep = live_representations(spec.kc)[0]
    if live_rep is not Representation.SYMBOLIC:
        pytest.skip("KC's live surface is not symbolic; its widget is fixed by representation.")
    widget = widget_for_representation(live_rep, spec.kc)
    expected = (
        WidgetId.FRACTION_EDITOR if spec.kc in _FRACTION_EDITOR_KCS else WidgetId.NUMBER_ENTRY
    )
    assert widget is expected
