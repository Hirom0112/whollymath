"""Natural-number Nate — the confident guesser (PROJECT.md §4.2 Persona 1), as DATA.

A concrete Layer-2 persona config, data on top of the Slice-2.1 schema
(``persona_config.py``). As with Priya and Sam, no behavior lives here — the
natural-number-bias number-line misplacement BEHAVIOR is the Layer-3 simulator's
job (``simulator.py``). This module only pins Nate's §4.2 spec into the typed
schema.

Nate's §4.2 definition, mapped field-by-field:

  - Knowledge state: "Knows fraction notation and basic part-whole meaning. Does
    not know that bigger denominator means smaller parts." → he reliably recognizes
    a symbolic equivalence SURFACE pattern (right answer when the pattern matches),
    but has no magnitude concept. We model the equivalence grip as tied to the
    SYMBOLIC representation (``KnowledgeState.format_tied_to``): "correct on symbolic
    equivalence where the surface pattern matches" (§4.2 P1) is exactly a
    surface-pattern, format-bound competence. His number-line-placement grip is held
    WITH_MISCONCEPTION (natural-number bias) with NO format tie — the bias fires
    wherever magnitude is asked for, not only in one format.
  - Active misconception: "Natural-number bias — treats numerator and denominator as
    independent whole numbers." → he carries ``natural-number-bias`` (the Layer-1
    ``MisconceptionId``). On number-line placement the simulator replays
    ``natural_number_bias_number_line`` and submits ``biased_position`` (the
    denominator read as a whole-number position), which the verifier classifies
    MAGNITUDE — "places fractions with bigger denominators further from zero" (§4.2 P1).
  - Behavior signature: "Answers in <3 seconds with high confidence." → very low
    latency (a snap guesser, faster than methodical Priya but NOT sub-floor like
    Cleo — his failure is conceptual, not disengagement), low hint use (he is
    confident, he does not ask), high engagement (he is genuinely trying), low
    scaffold dependence.

Nate forces the §3.4 rule-2 mastery rule: mastery cannot be declared from a single
representation. A "5 correct in a row on symbolic equivalence" threshold would
falsely pass Nate, who then fails number-line/magnitude items — so mastery must
require correctness across >= 2 representations of the same KC (PROJECT.md §3.4,
§4.2 P1). Nothing here computes that; it only encodes the learner the rule is for.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId
from app.personas.persona_config import (
    BehavioralParameters,
    KnowledgeMode,
    KnowledgeState,
    PersonaConfig,
)

NATE_ID = "natural_number_nate"

# Nate's equivalence competence is a SURFACE-pattern match tied to the symbolic
# format (§4.2 P1: "correct on symbolic equivalence where the surface pattern
# matches"). Held WITH_MISCONCEPTION + format_tied_to=SYMBOLIC: inside the symbolic
# pattern he reproduces the correct equivalent value, but the grip is the bias
# wearing a familiar surface — not magnitude understanding. (Equivalence supports
# the symbolic representation per the KC registry, so the tie is well-formed.)
_NATE_EQUIVALENCE_FORMAT = Representation.SYMBOLIC

NATE = PersonaConfig(
    persona_id=NATE_ID,
    name="Natural-number Nate",
    knowledge={
        # Symbolic-equivalence surface competence (right when the pattern matches).
        KnowledgeComponentId.EQUIVALENCE: KnowledgeState(
            kc_id=KnowledgeComponentId.EQUIVALENCE,
            mode=KnowledgeMode.WITH_MISCONCEPTION,
            format_tied_to=_NATE_EQUIVALENCE_FORMAT,
        ),
        # Number-line placement: the natural-number bias fires here regardless of
        # format (no tie), so he places by the denominator read as a position.
        KnowledgeComponentId.NUMBER_LINE_PLACEMENT: KnowledgeState(
            kc_id=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
            mode=KnowledgeMode.WITH_MISCONCEPTION,
        ),
    },
    # The active misconception, named verbatim from the Layer-1 catalog.
    # natural-number-bias applies to both EQUIVALENCE and NUMBER_LINE_PLACEMENT
    # (misconceptions.py applicable_kcs), the two KCs Nate is configured on, so the
    # schema's applicability check passes.
    misconceptions=(MisconceptionId.NATURAL_NUMBER_BIAS,),
    behavior=BehavioralParameters(
        # "Answers in <3 seconds with high confidence" (§4.2 P1): a snap guesser.
        # Above Cleo's sub-2s engagement floor — his failure is conceptual, not
        # disengagement — but well under the 3s the spec names.
        response_latency_seconds=2.5,
        # Confident; he does not reach for hints.
        hint_request_probability=0.05,
        # He genuinely engages (he is trying and confident), contrast Cleo's floor.
        engagement_floor=0.9,
        # Self-reliant on the surface pattern; he does not lean on scaffolds.
        scaffold_dependence_rate=0.1,
    ),
)
