"""Tests for the persona registry (Slices 2.2 + 3.1).

Pin the registry contract: the personas are present and resolvable, ids are
unique, and lookups behave like the Layer-1 registries. Slice 3.1 completed the
five-persona roster (Nate, Priya, Hugo, Sam, Cleo) without changing the contract.
"""

import pytest
from app.personas.cleo import CLEO, CLEO_ID
from app.personas.hugo import HUGO, HUGO_ID
from app.personas.nate import NATE, NATE_ID
from app.personas.priya import PRIYA, PRIYA_ID
from app.personas.registry import PERSONA_REGISTRY, get_persona
from app.personas.sam import SAM, SAM_ID


def test_registry_contains_the_full_five_persona_roster() -> None:
    """The complete §4.2 roster ships after Slice 3.1: Nate, Priya, Hugo, Sam, Cleo."""
    ids = {p.persona_id for p in PERSONA_REGISTRY.all()}
    assert ids == {NATE_ID, PRIYA_ID, HUGO_ID, SAM_ID, CLEO_ID}


def test_lookup_resolves_to_the_canonical_config_objects() -> None:
    """get_persona resolves each id to the singleton config from its data module."""
    assert get_persona(NATE_ID) is NATE
    assert get_persona(PRIYA_ID) is PRIYA
    assert get_persona(HUGO_ID) is HUGO
    assert get_persona(SAM_ID) is SAM
    assert get_persona(CLEO_ID) is CLEO


def test_unknown_persona_id_raises_keyerror() -> None:
    """An unknown id raises KeyError naming the bad id — not a silent None."""
    with pytest.raises(KeyError) as exc:
        get_persona("anxious_quitter")  # deliberately not in the roster (PROJECT.md §4.3)
    assert "anxious_quitter" in str(exc.value)


def test_persona_ids_are_unique() -> None:
    """No two registered personas share an id."""
    ids = [p.persona_id for p in PERSONA_REGISTRY.all()]
    assert len(ids) == len(set(ids))
