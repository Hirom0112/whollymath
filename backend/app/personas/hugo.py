"""Hint-hunter Hugo — the over-scaffolding-dependent learner (§4.2 P3), as DATA.

A concrete Layer-2 persona config, data on top of the Slice-2.1 schema
(``persona_config.py``). No behavior lives here — the "correct only WITH a hint"
BEHAVIOR is the Layer-3 simulator's job (``simulator.py``). This module only pins
Hugo's §4.2 spec into the typed schema.

Hugo's §4.2 definition, mapped field-by-field:

  - Knowledge state: "Basic fraction recognition. Does not know most operational
    fraction skills." → he holds the operational KCs in mode ``NEITHER`` (no genuine
    grip). He does not knowingly run a wrong procedure (that would be a named
    misconception); he simply lacks the skill and leans on the scaffold.
  - Active failure: "Metacognitive — treats hints as the instruction itself." This
    is NOT one of the five named DOMAIN misconceptions (those are fraction-error
    patterns); it is a behavioral failure. So Hugo carries NO named misconception
    (``misconceptions=()``) — the schema allows this, and the failure is expressed
    entirely through his behavioral parameters + the simulator's hint-dependence path
    (CLAUDE.md §8.3: knowledge state is DATA, never LLM emergence).
  - Behavior signature: "Requests hints within seconds, before attempting; executes
    hints mechanically without generalizing; hint dependence rate stays >70% even
    after many problems; struggles when hints are unavailable." → VERY high
    ``hint_request_probability`` (> 0.70, the §4.2 number) and high
    ``scaffold_dependence_rate``. The simulator reads the high scaffold-dependence to
    model "correct only with a hint": when he requests a hint he reproduces the
    correct answer mechanically (``requested_hint=True``); without one he is wrong.

Hugo forces the §3.4 rule-3 mastery gate: mastery requires >= 1 UNSCAFFOLDED
correct attempt, and hinted-correct attempts are downweighted. Because every
correct answer Hugo produces is hinted, he can never satisfy that gate — the false
positive the rule blocks ("succeed only while the UI is doing the reasoning for
them", §4.2 P3, PRD). Nothing here computes that; it only encodes the learner the
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

HUGO_ID = "hint_hunter_hugo"

# The operational KCs Hugo "does not know" (§4.2 P3): he holds none of them in any
# usable form, so each is NEITHER. With a hint the simulator lets him mechanically
# produce the correct answer; without one he collapses to a wrong guess. Equivalence
# (basic recognition he does have) is left unconfigured → NEITHER via mode_for as
# well; we do not grant him grip the spec does not (CLAUDE.md §5).
_OPERATIONAL_KCS = (
    KnowledgeComponentId.COMMON_DENOMINATOR,
    KnowledgeComponentId.ADDITION_UNLIKE,
    KnowledgeComponentId.SUBTRACTION_UNLIKE,
)

HUGO = PersonaConfig(
    persona_id=HUGO_ID,
    name="Hint-hunter Hugo",
    knowledge={
        kc_id: KnowledgeState(kc_id=kc_id, mode=KnowledgeMode.NEITHER) for kc_id in _OPERATIONAL_KCS
    },
    # No named DOMAIN misconception: Hugo's failure is metacognitive (treats hints as
    # the instruction), not a fraction-error pattern. The schema permits an empty tuple.
    misconceptions=(),
    behavior=BehavioralParameters(
        # "Requests hints within seconds, before attempting" (§4.2 P3): he answers
        # fast because the hint does the thinking — but ABOVE Cleo's engagement floor
        # (his issue is dependence, not disengagement).
        response_latency_seconds=4.0,
        # The defining number: hint dependence > 0.70 (§4.2 P3). Set high so the
        # measured rate stays comfortably above the threshold across many problems.
        hint_request_probability=0.95,
        # He is engaged (he is working the problem, via the hint), so engagement is
        # reasonable — the failure is the scaffold-dependence, not a sub-floor click.
        engagement_floor=0.6,
        # The crux: he leans heavily on UI scaffolds / worked steps. High enough that
        # the simulator's hint-dependence path treats his correct answers as hint-driven.
        scaffold_dependence_rate=0.9,
    ),
)
