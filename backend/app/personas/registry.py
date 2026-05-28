"""The persona registry — the single home that collects the Layer-2 configs.

Mirrors the Layer-1 registries (``knowledge_components.py``,
``misconceptions.py``): a module-level singleton built once at import, the single
source of truth the eval harness and the (later) Layer-3 simulator resolve
personas through (ARCHITECTURE.md §4, §5). The configs themselves are data living
in per-persona modules (``priya.py``, ``sam.py``); this module only assembles them.

Slice 2.2 implemented Procedure Priya and Surface Sam (the two diagnostically-
richest personas, the Week-2 checkpoint in PROJECT.md §6). Slice 3.1 completes the
roster with Natural-number Nate, Hint-hunter Hugo and Click-through Cleo (Week 3);
adding each is editing this tuple plus a new data module — "adding a sixth persona
is editing a config" (PROJECT.md §4.1).
"""

from __future__ import annotations

from app.personas.cleo import CLEO
from app.personas.hugo import HUGO
from app.personas.nate import NATE
from app.personas.persona_config import PersonaConfig, PersonaRegistry
from app.personas.priya import PRIYA
from app.personas.sam import SAM

# The five personas, in PROJECT.md §4.2 roster order: Nate (P1), Priya (P2),
# Hugo (P3), Sam (P4), Cleo (P5).
_PERSONAS: tuple[PersonaConfig, ...] = (NATE, PRIYA, HUGO, SAM, CLEO)

# The module-level registry is the single source of truth for the persona configs.
# Built once at import; immutable contents.
PERSONA_REGISTRY = PersonaRegistry(_PERSONAS)


def get_persona(persona_id: str) -> PersonaConfig:
    """Module-level shortcut for ``PERSONA_REGISTRY.get`` (the common case)."""
    return PERSONA_REGISTRY.get(persona_id)
