"""Layer-2 persona config schema — personas as DATA, not code.

This is Slice 2.1 of the synthetic-learner harness (ARCHITECTURE.md §5 Layer 2;
PROJECT.md §4.1). Layer 2's whole point is that "a persona is a config: which KCs
they have, in which mode ... plus behavioral parameters ... Personas are *data*,
not code. Adding a sixth persona is editing a config" (PROJECT.md §4.1). So this
module defines the typed, frozen schema a persona is expressed in; the concrete
persona instances (Priya, Sam, ...) live in their own data modules and the
registry below collects them.

What this module is NOT: it is not the behavioral simulator. Layer 3 — the
deterministic code that, given a persona config + a problem, computes the
persona's action — is a SEPARATE later slice (PROJECT.md §4.1 Layer 3,
ARCHITECTURE.md §5). This module only declares the data the simulator will read.
There is therefore deliberately no behavior here beyond holding and validating
config; no SymPy, no DB, and — critically — NO LLM. Per CLAUDE.md §8.3 the LLM
(Layer 4) never sees a persona's knowledge state, so the knowledge state must be
captured here as plain data the LLM never touches.

The schema references the Layer-1 source-of-truth ids directly
(``KnowledgeComponentId``, ``MisconceptionId``, ``Representation``) rather than
raw strings, so a persona config cannot name a KC or misconception that does not
exist — construction fails fast if it tries (ARCHITECTURE.md §4: one set of ids
across the whole system).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId, get_misconception


class KnowledgeMode(StrEnum):
    """How thoroughly a persona holds a given KC (PROJECT.md §4.1).

    PROJECT.md §4.1 enumerates the modes verbatim: "procedure-only / concept-only
    / both / neither / with-named-misconception". These five members are that
    enumeration. The mode is what lets the Layer-3 simulator (a later slice) decide
    deterministically whether the persona answers a routine item correctly, whether
    it can explain *why*, and whether it falls into a named wrong-answer pattern —
    without any LLM involvement (CLAUDE.md §8.3).
    """

    # Runs the algorithm correctly on routine items but cannot justify it and
    # fails "explain why" / error-finding (the Procedure-Priya shape, §4.2 P2).
    PROCEDURE_ONLY = "procedure_only"
    # Understands the concept but is not fluent in the routine procedure.
    CONCEPT_ONLY = "concept_only"
    # Genuine mastery: correct procedure AND able to justify it.
    BOTH = "both"
    # Does not hold the KC in any usable form.
    NEITHER = "neither"
    # Holds the KC only through a named misconception — produces that
    # misconception's specific wrong-answer pattern (the named id is in
    # ``PersonaConfig.misconceptions``).
    WITH_MISCONCEPTION = "with_misconception"


@dataclass(frozen=True)
class KnowledgeState:
    """A persona's grip on ONE knowledge component (PROJECT.md §4.1).

    Frozen because a persona config is data, not mutable runtime state — the whole
    harness's reproducibility depends on the config not changing under the
    simulator's feet (ARCHITECTURE.md §5 Layer 3: "same input always yields the
    same output"). The KC is named by its Layer-1 id so a config can never point at
    a KC that doesn't exist.

    ``format_tied_to`` encodes Surface Sam's defining property (PROJECT.md §4.2
    Persona 4): "Knows the procedure for the most recent format he saw. Does not
    see that the underlying KC is the same across formats." When set, the persona
    holds this KC only within that one representation/format; the same KC presented
    in any other representation collapses to baseline. ``None`` means the persona's
    grip on the KC is format-independent (the normal case). This is DATA the
    Layer-3 simulator will read; the collapse BEHAVIOR is the simulator's job, not
    this module's.
    """

    kc_id: KnowledgeComponentId
    mode: KnowledgeMode
    # The single representation/format this KC is tied to, or None if grip is
    # format-independent. Tying to a format is the Surface-Sam signature (§4.2 P4).
    format_tied_to: Representation | None = None


@dataclass(frozen=True)
class BehavioralParameters:
    """The deterministic behavioral knobs the Layer-3 simulator reads (§4.1).

    PROJECT.md §4.1 names the behavioral parameters a persona config carries:
    "response latency, hint-request probability, engagement floor, scaffold-
    dependence rate". These four fields are exactly that list. They are plain
    numbers (no randomness, no LLM) so that, given the same problem, the simulator
    derives the same action every time (ARCHITECTURE.md §5 Layer 3 reproducibility).

    Frozen, and validated on construction so a config with an impossible value
    (a probability outside [0, 1], a negative latency) fails fast at import time
    rather than producing a quietly-wrong simulation later.
    """

    # Characteristic time the persona "thinks" before answering, in seconds. Used
    # by the simulator and is itself a mastery signal (Cleo's sub-2s floor, §4.2 P5;
    # the engagement-floor rule, §3.4). A fast confident guesser (Nate) is low; a
    # slow-but-correct memorizer (Priya) is higher.
    response_latency_seconds: float
    # Probability the persona requests a hint on a given problem (Hugo's >0.70
    # signature, §4.2 P3; the ≥1-unassisted-attempt rule, §3.4).
    hint_request_probability: float
    # Engagement floor in [0, 1]: how much genuine effort the persona puts in
    # before answering. Cleo sits at the bottom (§4.2 P5); a diligent persona is
    # high. The mastery model's engagement-floor signals (§3.4) read this.
    engagement_floor: float
    # Scaffold-dependence rate in [0, 1]: how much the persona leans on UI
    # assistance / worked steps. Hugo is high; a self-sufficient persona is low
    # (the over-scaffolding failure mode, §3.4, §4.2 P3).
    scaffold_dependence_rate: float

    def __post_init__(self) -> None:
        # Fail fast on impossible values: a silently-out-of-range probability would
        # make the later simulator quietly wrong, which is exactly the kind of drift
        # CLAUDE.md §8.4 warns against. We validate here, at the data boundary.
        if self.response_latency_seconds < 0:
            raise ValueError(
                f"response_latency_seconds must be >= 0, got {self.response_latency_seconds}"
            )
        for name, value in (
            ("hint_request_probability", self.hint_request_probability),
            ("engagement_floor", self.engagement_floor),
            ("scaffold_dependence_rate", self.scaffold_dependence_rate),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")


@dataclass(frozen=True)
class PersonaConfig:
    """One synthetic learner, expressed entirely as data (PROJECT.md §4.1).

    This is the Layer-2 unit. It carries everything the §4.1 definition lists: a
    stable ``persona_id`` and human-readable ``name``; the per-KC ``knowledge``
    state (which KCs, in which mode, optionally format-tied); the named
    ``misconceptions`` the persona carries (Layer-1 ``MisconceptionId`` values);
    and the ``behavior`` parameters. From these, the Layer-3 simulator (a later
    slice) can compute the persona's action deterministically.

    Frozen and hashable: ``knowledge`` is exposed as an immutable mapping and
    ``misconceptions`` as a tuple, so a persona config genuinely cannot mutate at
    runtime (reproducibility, ARCHITECTURE.md §5). Construction validates that
    every misconception named is one the persona actually holds via a
    ``WITH_MISCONCEPTION`` KC mode somewhere — keeping the "which KCs, in which
    mode" data and the "active misconception" data from drifting apart (§4.2 pins
    one named misconception per persona).
    """

    persona_id: str
    name: str
    # Per-KC knowledge state, keyed by KC id. Stored as an immutable mapping so the
    # config stays frozen all the way down.
    knowledge: Mapping[KnowledgeComponentId, KnowledgeState]
    # The named misconception(s) this persona carries (Layer-1 ids). A tuple so the
    # config is hashable/immutable; §4.2 gives each of our two personas exactly one.
    misconceptions: tuple[MisconceptionId, ...]
    behavior: BehavioralParameters

    def __post_init__(self) -> None:
        # Re-wrap knowledge in a read-only view so callers cannot mutate the dict
        # they passed in after construction (frozen dataclass freezes the binding,
        # not the dict's contents). object.__setattr__ is the documented way to set
        # a field on a frozen dataclass from __post_init__.
        object.__setattr__(self, "knowledge", MappingProxyType(dict(self.knowledge)))

        # Each entry must be keyed by its own kc_id, or lookups by KC id would lie.
        for kc_id, state in self.knowledge.items():
            if state.kc_id is not kc_id:
                raise ValueError(
                    f"knowledge key {kc_id.value!r} does not match state.kc_id "
                    f"{state.kc_id.value!r}"
                )

        # A named misconception must have a real home in this persona's KCs, so the
        # §4.1 "which KCs, in which mode" data cannot drift from the §4.2 "active
        # misconception" data (CLAUDE.md §8.4: no orphan ids). For each misconception
        # the persona names, require: (a) it is applicable to at least one KC the
        # persona is configured on, per the Layer-1 catalog's ``applicable_kcs`` —
        # so a config can't claim a misconception on a KC it can't appear on; and
        # (b) that KC is NOT held in BOTH (genuine mastery) mode — a misconception
        # that corrupts a KC cannot coexist with full mastery of it. This keeps the
        # schema faithful whether the misconception manifests as PROCEDURE_ONLY
        # (Priya: right answer, no concept) or WITH_MISCONCEPTION (Sam: a specific
        # wrong-answer pattern).
        configured_kcs = set(self.knowledge)
        for misconception_id in self.misconceptions:
            applicable = set(get_misconception(misconception_id).applicable_kcs)
            home_kcs = configured_kcs & applicable
            if not home_kcs:
                raise ValueError(
                    f"persona {self.persona_id!r} names misconception "
                    f"{misconception_id.value!r} but holds none of the KCs it applies "
                    f"to ({tuple(kc.value for kc in applicable)})"
                )
            if all(self.knowledge[kc].mode is KnowledgeMode.BOTH for kc in home_kcs):
                raise ValueError(
                    f"persona {self.persona_id!r} names misconception "
                    f"{misconception_id.value!r} but holds every applicable KC in "
                    f"mode {KnowledgeMode.BOTH.value!r} (full mastery cannot carry it)"
                )

    def mode_for(self, kc_id: KnowledgeComponentId) -> KnowledgeMode:
        """The persona's mode on ``kc_id``, or NEITHER if it isn't configured.

        Treating an unconfigured KC as ``NEITHER`` is the safe default: a persona
        is assumed not to hold a KC it says nothing about, rather than silently
        raising and forcing every config to enumerate all five KCs.
        """
        state = self.knowledge.get(kc_id)
        return state.mode if state is not None else KnowledgeMode.NEITHER


class PersonaRegistry:
    """The single, deduplicated home for the persona configs.

    Mirrors ``KnowledgeComponentRegistry`` / ``MisconceptionRegistry`` (Slices 1.1,
    1.2): construction enforces id uniqueness so a duplicate persona id fails fast
    at import time; lookups are by ``persona_id`` string (the join key the eval
    harness and logs will use).
    """

    def __init__(self, personas: tuple[PersonaConfig, ...]) -> None:
        by_id: dict[str, PersonaConfig] = {}
        for persona in personas:
            if persona.persona_id in by_id:
                raise ValueError(f"Duplicate persona id: {persona.persona_id!r}")
            by_id[persona.persona_id] = persona
        # Preserve declared order for deterministic iteration (reproducibility).
        self._by_id = by_id

    def all(self) -> tuple[PersonaConfig, ...]:
        """Every persona, in the registry's declared order."""
        return tuple(self._by_id.values())

    def get(self, persona_id: str) -> PersonaConfig:
        """Resolve a persona by its id, or raise KeyError naming the bad id.

        A clear failure beats a silent ``None`` (CLAUDE.md §8.5: write for the
        reader).
        """
        try:
            return self._by_id[persona_id]
        except KeyError as exc:
            raise KeyError(f"Unknown persona id: {persona_id!r}") from exc
