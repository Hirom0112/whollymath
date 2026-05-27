"""Tests for the persona registry (Slice 2.2).

Pin the registry contract: the two Slice-2.2 personas are present and resolvable,
ids are unique, and lookups behave like the Layer-1 registries. Adding Nate/Hugo/
Cleo later (Week 3) extends this without changing the contract.
"""

import pytest
from app.personas.priya import PRIYA, PRIYA_ID
from app.personas.registry import PERSONA_REGISTRY, get_persona
from app.personas.sam import SAM, SAM_ID


def test_registry_contains_priya_and_sam() -> None:
    """Slice 2.2 ships exactly Priya and Sam (PROJECT.md §6 Week-2 checkpoint)."""
    ids = {p.persona_id for p in PERSONA_REGISTRY.all()}
    assert ids == {PRIYA_ID, SAM_ID}


def test_lookup_resolves_to_the_canonical_config_objects() -> None:
    """get_persona resolves each id to the singleton config from its data module."""
    assert get_persona(PRIYA_ID) is PRIYA
    assert get_persona(SAM_ID) is SAM


def test_unknown_persona_id_raises_keyerror() -> None:
    """An unknown id raises KeyError naming the bad id — not a silent None."""
    with pytest.raises(KeyError) as exc:
        get_persona("anxious_quitter")  # deliberately not in the roster (PROJECT.md §4.3)
    assert "anxious_quitter" in str(exc.value)


def test_persona_ids_are_unique() -> None:
    """No two registered personas share an id."""
    ids = [p.persona_id for p in PERSONA_REGISTRY.all()]
    assert len(ids) == len(set(ids))
