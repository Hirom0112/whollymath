"""Tests for the Layer-1 Knowledge Component registry (Slice 1.1).

Written test-first per CLAUDE.md §2 (TDD is mandatory for the domain model —
the single most load-bearing system). These tests pin down the contract that
PROJECT.md §3.1, §4.1 and ARCHITECTURE.md §4, §5, §14 require of Layer 1:

  - exactly the five KCs from PROJECT.md §3.1 exist
  - lookup-by-id works and unknown ids are handled clearly
  - ids are guaranteed unique
  - the registry is the single source of truth (the same ids the rest of the
    system — mastery model, personas, transfer test — will reference)

No SymPy, no LLM, no DB here (CLAUDE.md §8.1/§8.2): this slice is only the
deterministic KC identifiers and their typed metadata. Misconceptions (1.2),
problem generators (1.3) and the SymPy verifier (1.4) are intentionally NOT
tested here — they hang off these KCs in later slices.
"""

import json
from pathlib import Path

import pytest
from app.domain.knowledge_components import (
    KC_REGISTRY,
    LIVE_KCS,
    KnowledgeComponent,
    KnowledgeComponentId,
    Representation,
    get_kc,
)

# The five CONTENT-COMPLETE KCs (PROJECT.md §3.1): the foundation fraction skills that
# have the full Layer-1 stack (registry metadata + generator + lesson spec + hints). The
# registry, the gem catalog, and ``LIVE_KCS`` all equal this set — they track what is
# actually BUILT. The domain layer asserts these directly rather than reading a downstream
# data file (the gem bank is validated *against* this set below, only when present).
EXPECTED_CATALOG_IDS = {
    "KC_equivalence",
    "KC_common_denominator",
    "KC_addition_unlike",
    "KC_subtraction_unlike",
    "KC_number_line_placement",
    # Grade-6 content build (2026-05-30) — Unit 1 (numeric, on the existing infra).
    "KC_ratio_language",
    "KC_unit_rate",
    "KC_equivalent_ratios",
    "KC_percent",
    "KC_unit_conversion",
    # Unit 2 (numeric, T2).
    "KC_multiply_fractions",
    "KC_gcf_lcm",
    "KC_divide_fractions",
    "KC_multi_digit_division",
    "KC_decimal_operations",
    # Unit 3 (numeric).
    "KC_absolute_value",
    "KC_signed_numbers",
    # Unit-INT (TEKS 6.3C/D, numeric).
    "KC_integer_add_subtract",
    # Unit 4 (expression-answer; the first non-numeric answer kind).
    "KC_write_expressions",
}

# Content-complete KCs built BEYOND the fraction-only gem bank (the Grade-6 content build). They
# are in the registry/LIVE_KCS but NOT in diagnostic_gems.json, so the bank-vs-registry check
# subtracts them. Grows with each Grade-6 KC built on the procedural generators (no gem items).
GRADE6_BUILT_NOT_IN_BANK = {
    "KC_ratio_language",
    "KC_unit_rate",
    "KC_equivalent_ratios",
    "KC_percent",
    "KC_unit_conversion",
    "KC_multiply_fractions",
    "KC_gcf_lcm",
    "KC_divide_fractions",
    "KC_multi_digit_division",
    "KC_decimal_operations",
    "KC_absolute_value",
    "KC_integer_add_subtract",
    "KC_signed_numbers",
    "KC_write_expressions",
}

# The Grade-6 ontology added for the cross-topic HelpNeed model (T1_T2_COORDINATION.md §4):
# one KC per CURRICULUM_STANDARD.md §3–§7 lesson. These are part of the enum (the model's
# one-hot label space, KC_ORDER) and the curriculum ontology, but are NOT yet content-complete
# — no generator/spec/hints — so they are absent from the registry, the gem catalog, and
# LIVE_KCS until their content is built. The full enum is exactly CATALOG ∪ GRADE6.
EXPECTED_GRADE6_KCS = {
    # U1 — Ratios & Rates (6.RP). KC_ratio_language + KC_unit_rate + KC_equivalent_ratios +
    # KC_percent + KC_unit_conversion moved to EXPECTED_CATALOG_IDS (built 2026-05-30).
    "KC_rate_problems",
    # U2 — Fractions & Decimals (6.NS.1–4). KC_multiply_fractions + KC_gcf_lcm + KC_divide_fractions
    # + KC_multi_digit_division + KC_decimal_operations all moved to EXPECTED_CATALOG_IDS
    # (built 2026-05-30, T2 / kc-gcf / kc-conv); KC_unit_conversion likewise moved (Unit 1).
    # U3 — Rational Numbers (6.NS.5–8). KC_absolute_value + KC_signed_numbers moved to
    # EXPECTED_CATALOG_IDS (built 2026-05-30).
    "KC_rationals_on_line",
    "KC_ordering_inequalities",
    "KC_classify_number_sets",
    "KC_coordinate_plane",
    # U-INT — Integer Arithmetic (TEKS 6.3C/D). KC_integer_add_subtract moved to
    # EXPECTED_CATALOG_IDS (built 2026-05-30).
    "KC_integer_multiply_divide",
    # U4 — Expressions (6.EE.1–4, 6). KC_write_expressions moved to EXPECTED_CATALOG_IDS
    # (built 2026-05-30 — the first expression-answer KC).
    "KC_exponents",
    "KC_expression_parts",
    "KC_evaluate_expressions",
    "KC_equivalent_expressions",
    "KC_dependent_vars",
    # U5 — Equations & Inequalities (6.EE.5–9)
    "KC_equation_solutions",
    "KC_one_step_equations",
    "KC_inequalities",
    # U6 — Geometry (6.G)
    "KC_triangle_properties",
    "KC_area_polygons",
    "KC_volume_fractional_edges",
    "KC_polygons_coordinate_plane",
    "KC_surface_area_nets",
    # U7 — Statistics (6.SP)
    "KC_statistical_questions",
    "KC_data_displays",
    "KC_center_spread_shape",
    "KC_summary_statistics",
    "KC_mean_absolute_deviation",
    "KC_categorical_data",
    # U8 — Personal Financial Literacy (TEKS 6.14)
    "KC_check_register",
    "KC_lifetime_income",
}


def test_registry_contains_exactly_the_content_complete_kcs() -> None:
    """The registry holds exactly the 5 content-complete fraction KCs (PROJECT.md §3.1).

    The registry tracks what is BUILT, not the whole ontology — the Grade-6 label-space KCs
    live in the enum but get no registry entry until their content lands.
    """
    registry_ids = {kc.id.value for kc in KC_REGISTRY.all()}
    assert registry_ids == EXPECTED_CATALOG_IDS
    assert len(KC_REGISTRY.all()) == len(EXPECTED_CATALOG_IDS)


def test_enum_is_the_full_grade6_ontology() -> None:
    """The enum is the full label space: the 5 content KCs PLUS the Grade-6 ontology.

    This is the contract the HelpNeed one-hot (KC_ORDER) depends on, so it is pinned exactly.
    """
    enum_values = {member.value for member in KnowledgeComponentId}
    assert enum_values == EXPECTED_CATALOG_IDS | EXPECTED_GRADE6_KCS
    assert len(KnowledgeComponentId) == 46  # 19 content-complete + 27 Grade-6 ontology


def test_live_kcs_is_exactly_the_registry_subset() -> None:
    """LIVE_KCS (content-complete) == the registry, ⊆ the enum, and excludes unbuilt KCs."""
    assert LIVE_KCS == {kc.id for kc in KC_REGISTRY.all()}
    assert {kc.value for kc in LIVE_KCS} == EXPECTED_CATALOG_IDS
    assert all(kc in set(KnowledgeComponentId) for kc in LIVE_KCS)
    # A Grade-6 ontology KC exists in the enum but is NOT live (no content yet).
    # KC_rationals_on_line is unbuilt (KC_signed_numbers went live 2026-05-30, so it
    # is no longer a valid example).
    assert KnowledgeComponentId("KC_rationals_on_line") not in LIVE_KCS


def test_unbuilt_kc_has_no_registry_entry() -> None:
    """Resolving an ontology-only KC through the registry fails loudly (not a silent None)."""
    with pytest.raises(KeyError):
        get_kc(KnowledgeComponentId("KC_rationals_on_line"))


def test_lookup_by_id_returns_the_matching_kc() -> None:
    """get_kc resolves a known id (both enum and raw string) to its KC object."""
    kc_from_enum = get_kc(KnowledgeComponentId.EQUIVALENCE)
    assert kc_from_enum.id is KnowledgeComponentId.EQUIVALENCE

    kc_from_string = get_kc("KC_equivalence")
    assert kc_from_string is kc_from_enum  # registry returns the canonical singleton


def test_lookup_resolves_every_contract_id() -> None:
    """Every contract id is resolvable through the registry (single source of truth)."""
    for raw_id in EXPECTED_CATALOG_IDS:
        kc = get_kc(raw_id)
        assert kc.id.value == raw_id


def test_unknown_id_raises_keyerror_with_clear_message() -> None:
    """An unknown id raises KeyError naming the bad id — not a silent None."""
    with pytest.raises(KeyError) as exc:
        get_kc("KC_does_not_exist")
    assert "KC_does_not_exist" in str(exc.value)


def test_ids_are_unique() -> None:
    """No two registered KCs share an id (guaranteed-unique requirement)."""
    ids = [kc.id for kc in KC_REGISTRY.all()]
    assert len(ids) == len(set(ids))


def test_each_kc_has_human_readable_name_and_description() -> None:
    """Every KC carries a non-empty skill name and description for humans."""
    for kc in KC_REGISTRY.all():
        assert kc.skill_name.strip()
        assert kc.description.strip()


def test_each_kc_declares_at_least_one_representation() -> None:
    """KCs hang multi-representation mastery (§3.4 rule 2) off these slots.

    The mastery model requires correctness across >=2 representations; a KC must
    therefore advertise the representations it can be exercised in. We assert the
    slot exists and is populated, without asserting later-slice behavior.
    """
    for kc in KC_REGISTRY.all():
        assert len(kc.representations) >= 1
        assert all(isinstance(rep, Representation) for rep in kc.representations)


def test_knowledge_component_is_immutable() -> None:
    """KC objects are frozen — Layer 1 is a source of truth, not mutable state."""
    kc = get_kc(KnowledgeComponentId.EQUIVALENCE)
    assert isinstance(kc, KnowledgeComponent)
    with pytest.raises(AttributeError):
        kc.skill_name = "tampered"  # type: ignore[misc]


def test_registry_all_is_stable_and_ordered() -> None:
    """all() returns the KCs in a deterministic order (reproducibility, §4.1)."""
    first = [kc.id for kc in KC_REGISTRY.all()]
    second = [kc.id for kc in KC_REGISTRY.all()]
    assert first == second


def test_gem_bank_catalog_matches_registry_when_present() -> None:
    """If the diagnostic-gem bank is on disk, its catalog must match the registry.

    Skipped when the bank file isn't present, so the domain layer's tests never
    depend on a downstream data asset (CI stays green independently of whether the
    bank has been committed). When the bank IS present, this catches drift between
    the registry and the gem bank's `_meta.kc_catalog`.
    """
    gems_path = Path(__file__).resolve().parents[2] / "app" / "domain" / "diagnostic_gems.json"
    if not gems_path.exists():
        pytest.skip("diagnostic_gems.json not present — bank-vs-registry check skipped")
    catalog = set(json.loads(gems_path.read_text())["_meta"]["kc_catalog"])
    # The gem bank is the fraction-only corpus; Grade-6 build KCs are content-complete (in the
    # registry) but not in the bank, so the bank catalog == the registry MINUS those additions.
    assert catalog == EXPECTED_CATALOG_IDS - GRADE6_BUILT_NOT_IN_BANK
