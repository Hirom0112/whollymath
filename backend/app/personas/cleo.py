"""Click-through Cleo — the engagement-floor adversary (§4.2 P5), as DATA.

A concrete Layer-2 persona config, data on top of the Slice-2.1 schema
(``persona_config.py``). No behavior lives here — the low-effort guess BEHAVIOR is
the Layer-3 simulator's job (``simulator.py``). This module only pins Cleo's §4.2
spec into the typed schema.

Cleo's §4.2 definition, mapped field-by-field:

  - Knowledge state: "Variable — sometimes knows the answer, sometimes doesn't.
    Failure isn't knowledge, it's engagement." → her grip is irrelevant; we hold the
    operational KCs in mode ``NEITHER`` because the diagnostic point is that she never
    produces engaged evidence, not that she lacks a specific skill. (Modeling her as
    NEITHER keeps her a low-effort guesser via the simulator's deterministic-guess
    path; the SIGNAL the mastery model reads is her sub-floor latency, not her answer.)
  - Active behavior: "Optimize for shortest path to 'done'." → captured by the
    behavioral parameters below, not a named domain misconception (she carries none).
  - Behavior signature: "Submits answers in 1–2 seconds, often before reading; picks
    first option; types the shortest plausible answer (often the digit she sees);
    ignores hint screens; skips explanation prompts." → ``response_latency_seconds``
    BELOW the mastery model's ENGAGEMENT_FLOOR_MS (so every turn is flagged
    low-engagement), a low ``engagement_floor``, and very low ``hint_request_probability``
    (she ignores hints). The "shortest plausible answer / the digit she sees" is the
    simulator's existing deterministic guess (the first operand's denominator read as
    a whole number) — no new answer behavior needed for Cleo.

Cleo forces the §3.4 engagement-floor rule: a sub-floor answer is flagged and does
not count as mastery evidence; a lucky run of fast guesses must not declare mastery
(§4.2 P5). The mastery model's ENGAGEMENT_FLOOR_MS is 2_000 ms, so her latency is
set strictly below 2 s. Nothing here computes that; it only encodes the learner the
rule is for.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.personas.persona_config import (
    BehavioralParameters,
    KnowledgeMode,
    KnowledgeState,
    PersonaConfig,
)

CLEO_ID = "click_through_cleo"

# Cleo is configured on the operational KCs in NEITHER mode: the point is not which
# skill she lacks (her knowledge is "variable") but that she never engages. NEITHER
# routes her through the simulator's deterministic low-effort guess; her sub-floor
# LATENCY — not her answer — is the signal the mastery model flags (§4.2 P5).
_OPERATIONAL_KCS = (
    KnowledgeComponentId.COMMON_DENOMINATOR,
    KnowledgeComponentId.ADDITION_UNLIKE,
    KnowledgeComponentId.SUBTRACTION_UNLIKE,
)

CLEO = PersonaConfig(
    persona_id=CLEO_ID,
    name="Click-through Cleo",
    knowledge={
        kc_id: KnowledgeState(kc_id=kc_id, mode=KnowledgeMode.NEITHER) for kc_id in _OPERATIONAL_KCS
    },
    # No named DOMAIN misconception: her failure is disengagement, not a fraction-
    # error pattern. The schema permits an empty tuple.
    misconceptions=(),
    behavior=BehavioralParameters(
        # "Submits answers in 1–2 seconds, often before reading" (§4.2 P5). Strictly
        # below ENGAGEMENT_FLOOR_MS (2_000 ms = 2.0 s) so EVERY turn is flagged
        # low-engagement by the mastery model. 1.5 s sits inside her 1–2 s window.
        response_latency_seconds=1.5,
        # She ignores hint screens (§4.2 P5): she rarely requests one.
        hint_request_probability=0.05,
        # The bottom of the engagement scale — she puts in no genuine effort.
        engagement_floor=0.05,
        # She does not lean on scaffolds; she clicks past them.
        scaffold_dependence_rate=0.05,
    ),
)
