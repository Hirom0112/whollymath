"""Tests for the Layer-2 persona config schema (Slice 2.1).

These pin the DATA contract PROJECT.md §4.1 requires of Layer 2: a persona is a
typed, immutable config — "which KCs, in which mode ... plus behavioral
parameters ... Personas are *data*, not code." They assert the schema is typed and
frozen, that it references only real Layer-1 ids, and that its validation keeps the
"which mode" data consistent with the "active misconception" data.

These are NOT behavioral tests. The mandatory-TDD Layer-3 behavioral simulator —
given a persona + a problem, compute the action — is a SEPARATE later slice
(CLAUDE.md §2; PROJECT.md §4.1). No SymPy, no LLM, no DB here (CLAUDE.md §8.1/§8.2,
§8.3): Layer 2 is config the LLM never even sees.
"""

import dataclasses

import pytest
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId
from app.personas.persona_config import (
    BehavioralParameters,
    KnowledgeMode,
    KnowledgeState,
    PersonaConfig,
    PersonaRegistry,
)


def _valid_behavior() -> BehavioralParameters:
    """A behavioral-parameter block with all-valid values, for reuse."""
    return BehavioralParameters(
        response_latency_seconds=5.0,
        hint_request_probability=0.2,
        engagement_floor=0.8,
        scaffold_dependence_rate=0.2,
    )


# ─── Knowledge mode enum (PROJECT.md §4.1) ──────────────────────────────────


def test_knowledge_mode_enumerates_the_five_modes_from_project_section_4_1() -> None:
    """The mode enum is exactly the §4.1 list: procedure/concept/both/neither/with-misconception."""
    values = {member.value for member in KnowledgeMode}
    assert values == {
        "procedure_only",
        "concept_only",
        "both",
        "neither",
        "with_misconception",
    }


# ─── Typing + immutability (the schema is data, frozen) ─────────────────────


def test_behavioral_parameters_is_frozen() -> None:
    """Behavioral params are frozen — config is data, not mutable runtime state."""
    behavior = _valid_behavior()
    assert dataclasses.is_dataclass(behavior)
    with pytest.raises(dataclasses.FrozenInstanceError):
        behavior.hint_request_probability = 0.9  # type: ignore[misc]


def test_knowledge_state_is_frozen() -> None:
    """A per-KC knowledge state is frozen."""
    state = KnowledgeState(kc_id=KnowledgeComponentId.ADDITION_UNLIKE, mode=KnowledgeMode.BOTH)
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.mode = KnowledgeMode.NEITHER  # type: ignore[misc]


def test_persona_config_is_frozen() -> None:
    """A persona config is frozen — its identity/knowledge cannot mutate at runtime."""
    config = PersonaConfig(
        persona_id="p",
        name="P",
        knowledge={},
        misconceptions=(),
        behavior=_valid_behavior(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.name = "Q"  # type: ignore[misc]


def test_persona_config_knowledge_mapping_is_read_only() -> None:
    """knowledge is exposed as a read-only mapping (frozen all the way down)."""
    state = KnowledgeState(kc_id=KnowledgeComponentId.ADDITION_UNLIKE, mode=KnowledgeMode.BOTH)
    config = PersonaConfig(
        persona_id="p",
        name="P",
        knowledge={KnowledgeComponentId.ADDITION_UNLIKE: state},
        misconceptions=(),
        behavior=_valid_behavior(),
    )
    with pytest.raises(TypeError):
        config.knowledge[KnowledgeComponentId.EQUIVALENCE] = state  # type: ignore[index]


def test_mutating_the_passed_dict_after_construction_does_not_change_config() -> None:
    """The config copies the knowledge dict, so later mutation of the caller's dict is inert."""
    source = {
        KnowledgeComponentId.ADDITION_UNLIKE: KnowledgeState(
            kc_id=KnowledgeComponentId.ADDITION_UNLIKE, mode=KnowledgeMode.BOTH
        )
    }
    config = PersonaConfig(
        persona_id="p", name="P", knowledge=source, misconceptions=(), behavior=_valid_behavior()
    )
    source[KnowledgeComponentId.EQUIVALENCE] = KnowledgeState(
        kc_id=KnowledgeComponentId.EQUIVALENCE, mode=KnowledgeMode.BOTH
    )
    assert KnowledgeComponentId.EQUIVALENCE not in config.knowledge


# ─── Behavioral-parameter validation (fail fast on impossible values) ───────


@pytest.mark.parametrize(
    "field",
    ["hint_request_probability", "engagement_floor", "scaffold_dependence_rate"],
)
def test_probability_fields_must_be_in_unit_interval(field: str) -> None:
    """A probability outside [0, 1] fails fast at construction, not silently later."""
    kwargs = {
        "response_latency_seconds": 5.0,
        "hint_request_probability": 0.2,
        "engagement_floor": 0.8,
        "scaffold_dependence_rate": 0.2,
    }
    kwargs[field] = 1.5
    with pytest.raises(ValueError, match=field):
        BehavioralParameters(**kwargs)


def test_negative_latency_is_rejected() -> None:
    """Negative think-time is impossible and is rejected."""
    with pytest.raises(ValueError, match="response_latency_seconds"):
        BehavioralParameters(
            response_latency_seconds=-1.0,
            hint_request_probability=0.2,
            engagement_floor=0.8,
            scaffold_dependence_rate=0.2,
        )


# ─── Knowledge/misconception consistency validation ─────────────────────────


def test_knowledge_key_must_match_state_kc_id() -> None:
    """A knowledge entry keyed by a KC that doesn't match its state is rejected."""
    mismatched = KnowledgeState(kc_id=KnowledgeComponentId.ADDITION_UNLIKE, mode=KnowledgeMode.BOTH)
    with pytest.raises(ValueError, match="does not match"):
        PersonaConfig(
            persona_id="p",
            name="P",
            knowledge={KnowledgeComponentId.EQUIVALENCE: mismatched},
            misconceptions=(),
            behavior=_valid_behavior(),
        )


def test_misconception_must_apply_to_a_configured_kc() -> None:
    """Naming a misconception with no applicable configured KC is rejected (no orphan ids).

    add-across applies only to KC_addition_unlike (Layer-1 catalog); a persona
    configured only on equivalence cannot carry it.
    """
    with pytest.raises(ValueError, match="add-across-error"):
        PersonaConfig(
            persona_id="p",
            name="P",
            knowledge={
                KnowledgeComponentId.EQUIVALENCE: KnowledgeState(
                    kc_id=KnowledgeComponentId.EQUIVALENCE,
                    mode=KnowledgeMode.WITH_MISCONCEPTION,
                )
            },
            misconceptions=(MisconceptionId.ADD_ACROSS_ERROR,),
            behavior=_valid_behavior(),
        )


def test_misconception_cannot_coexist_with_full_mastery_of_its_kc() -> None:
    """A misconception on a KC held in BOTH (genuine mastery) mode is contradictory and rejected."""
    with pytest.raises(ValueError, match="full mastery"):
        PersonaConfig(
            persona_id="p",
            name="P",
            knowledge={
                KnowledgeComponentId.ADDITION_UNLIKE: KnowledgeState(
                    kc_id=KnowledgeComponentId.ADDITION_UNLIKE, mode=KnowledgeMode.BOTH
                )
            },
            misconceptions=(MisconceptionId.ADD_ACROSS_ERROR,),
            behavior=_valid_behavior(),
        )


def test_misconception_coexists_with_procedure_only_mode() -> None:
    """A non-mastery mode (PROCEDURE_ONLY) can carry a misconception (Priya's shape)."""
    config = PersonaConfig(
        persona_id="p",
        name="P",
        knowledge={
            KnowledgeComponentId.ADDITION_UNLIKE: KnowledgeState(
                kc_id=KnowledgeComponentId.ADDITION_UNLIKE,
                mode=KnowledgeMode.PROCEDURE_ONLY,
            )
        },
        misconceptions=(MisconceptionId.PROCEDURE_WITHOUT_CONCEPT,),
        behavior=_valid_behavior(),
    )
    assert config.misconceptions == (MisconceptionId.PROCEDURE_WITHOUT_CONCEPT,)


# ─── mode_for default ───────────────────────────────────────────────────────


def test_mode_for_returns_neither_for_unconfigured_kc() -> None:
    """An unconfigured KC defaults to NEITHER — a persona is assumed not to hold what it omits."""
    config = PersonaConfig(
        persona_id="p", name="P", knowledge={}, misconceptions=(), behavior=_valid_behavior()
    )
    assert config.mode_for(KnowledgeComponentId.EQUIVALENCE) is KnowledgeMode.NEITHER


def test_mode_for_returns_configured_mode() -> None:
    """mode_for returns the configured mode for a KC that is present."""
    config = PersonaConfig(
        persona_id="p",
        name="P",
        knowledge={
            KnowledgeComponentId.ADDITION_UNLIKE: KnowledgeState(
                kc_id=KnowledgeComponentId.ADDITION_UNLIKE, mode=KnowledgeMode.PROCEDURE_ONLY
            )
        },
        misconceptions=(),
        behavior=_valid_behavior(),
    )
    assert config.mode_for(KnowledgeComponentId.ADDITION_UNLIKE) is KnowledgeMode.PROCEDURE_ONLY


# ─── format_tied_to ─────────────────────────────────────────────────────────


def test_format_tied_to_defaults_to_none() -> None:
    """Grip on a KC is format-independent by default (the normal case)."""
    state = KnowledgeState(kc_id=KnowledgeComponentId.ADDITION_UNLIKE, mode=KnowledgeMode.BOTH)
    assert state.format_tied_to is None


def test_format_tied_to_accepts_a_real_representation() -> None:
    """A format tie names a real Layer-1 Representation (Surface-Sam's signature slot)."""
    state = KnowledgeState(
        kc_id=KnowledgeComponentId.ADDITION_UNLIKE,
        mode=KnowledgeMode.WITH_MISCONCEPTION,
        format_tied_to=Representation.SYMBOLIC,
    )
    assert state.format_tied_to is Representation.SYMBOLIC


# ─── Registry ───────────────────────────────────────────────────────────────


def test_registry_lookup_and_all() -> None:
    """The registry resolves by id and returns all configs in declared order."""
    a = PersonaConfig(
        persona_id="a", name="A", knowledge={}, misconceptions=(), behavior=_valid_behavior()
    )
    b = PersonaConfig(
        persona_id="b", name="B", knowledge={}, misconceptions=(), behavior=_valid_behavior()
    )
    registry = PersonaRegistry((a, b))
    assert registry.get("a") is a
    assert registry.all() == (a, b)


def test_registry_rejects_duplicate_ids() -> None:
    """Two personas with the same id fail fast at construction."""
    a = PersonaConfig(
        persona_id="dup", name="A", knowledge={}, misconceptions=(), behavior=_valid_behavior()
    )
    b = PersonaConfig(
        persona_id="dup", name="B", knowledge={}, misconceptions=(), behavior=_valid_behavior()
    )
    with pytest.raises(ValueError, match="Duplicate persona id"):
        PersonaRegistry((a, b))


def test_registry_unknown_id_raises_keyerror_with_clear_message() -> None:
    """An unknown persona id raises KeyError naming the bad id — not a silent None."""
    registry = PersonaRegistry(())
    with pytest.raises(KeyError) as exc:
        registry.get("nobody")
    assert "nobody" in str(exc.value)
