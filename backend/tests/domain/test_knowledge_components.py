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
    KnowledgeComponent,
    KnowledgeComponentId,
    Representation,
    get_kc,
)

# The five KC ids are the Layer-1 contract (PROJECT.md §3.1). The registry is the
# SOURCE OF TRUTH for these, so the test asserts them directly rather than reading
# them from a downstream data file — the domain layer must not depend on a data
# asset to know what it is. (The diagnostic-gem bank is validated *against* this
# set below, only when the bank is present.)
EXPECTED_CATALOG_IDS = {
    "KC_equivalence",
    "KC_common_denominator",
    "KC_addition_unlike",
    "KC_subtraction_unlike",
    "KC_number_line_placement",
}


def test_registry_contains_exactly_the_five_kcs() -> None:
    """The registry has exactly the 5 KCs from PROJECT.md §3.1 — no more, no fewer."""
    registry_ids = {kc.id.value for kc in KC_REGISTRY.all()}
    assert registry_ids == EXPECTED_CATALOG_IDS
    assert len(KC_REGISTRY.all()) == 5


def test_enum_members_match_the_contract_exactly() -> None:
    """The KnowledgeComponentId enum is the typed mirror of the id contract."""
    enum_values = {member.value for member in KnowledgeComponentId}
    assert enum_values == EXPECTED_CATALOG_IDS


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
    assert catalog == EXPECTED_CATALOG_IDS
