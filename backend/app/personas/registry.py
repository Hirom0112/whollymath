"""The persona registry — the single home that collects the Layer-2 configs.

Mirrors the Layer-1 registries (``knowledge_components.py``,
``misconceptions.py``): a module-level singleton built once at import, the single
source of truth the eval harness and the (later) Layer-3 simulator resolve
personas through (ARCHITECTURE.md §4, §5). The configs themselves are data living
in per-persona modules (``priya.py``, ``sam.py``); this module only assembles them.

Slice 2.2 implements only Procedure Priya and Surface Sam (the two
diagnostically-richest personas, the Week-2 checkpoint in PROJECT.md §6). Nate,
Hugo and Cleo are later slices (Week 3); adding them is editing this tuple plus a
new data module — "adding a sixth persona is editing a config" (PROJECT.md §4.1).
"""

from __future__ import annotations

from app.personas.persona_config import PersonaConfig, PersonaRegistry
from app.personas.priya import PRIYA
from app.personas.sam import SAM

# Declared in PROJECT.md §6 priority order: Priya then Sam.
_PERSONAS: tuple[PersonaConfig, ...] = (PRIYA, SAM)

# The module-level registry is the single source of truth for the persona configs.
# Built once at import; immutable contents.
PERSONA_REGISTRY = PersonaRegistry(_PERSONAS)


def get_persona(persona_id: str) -> PersonaConfig:
    """Module-level shortcut for ``PERSONA_REGISTRY.get`` (the common case)."""
    return PERSONA_REGISTRY.get(persona_id)
