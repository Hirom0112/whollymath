"""Surface Sam — the cross-format pattern-matcher (PROJECT.md §4.2 Persona 4), as DATA.

The other half of Slice 2.2: a concrete Layer-2 persona config, data on top of the
Slice-2.1 schema (``persona_config.py``). As with Priya, no behavior lives here —
the collapse-on-format-change BEHAVIOR is the Layer-3 simulator's job (a separate
later slice, PROJECT.md §4.1). This module only pins Sam's §4.2 spec into the typed
schema.

Sam's §4.2 definition, mapped field-by-field:

  - Knowledge state: "Knows the procedure for the most recent format he saw. Does
    not see that the underlying KC is the same across formats." → his grip on a KC
    is tied to ONE representation/format (``KnowledgeState.format_tied_to``). We tie
    his addition KC to the symbolic format: he pattern-matches symbolic
    a/b + c/d items but does not see the same KC under, e.g., the area model. The
    schema records the tie as data; the Layer-3 simulator reads it to make accuracy
    "drop to baseline the moment format changes" (§4.2).
  - Active misconception: "'Math operations are tied to problem formats'." The §4.2
    persona explicitly carries the add-across error (the brief assigns Sam
    ``add-across-error``, e.g. ¼ + ¼ = 2/8 — named verbatim in §3.5 S3 and §3.9 as
    Sam's signature). So he holds ``add-across-error`` (the Layer-1 ``MisconceptionId``
    whose generator yields (a+c)/(b+d)).
  - Behavior signature: "Accuracy climbs to near-100% within a single homogeneous
    format block; drops to baseline the moment format changes; cannot explain format
    relationships." → moderate latency, low-to-moderate hint use (he is fluent
    *inside* a block), reasonable engagement, low scaffold dependence. The within-
    block-vs-cross-format dynamics are carried by the format tie + misconception,
    enforced by the Layer-3 simulator — not by a behavioral number here.

Sam forces the mastery rule that mastery is calculated on INTERLEAVED practice, not
blocked (PROJECT.md §3.4 rule 4, §4.2 P4) — "the most defensible single design
change, directly supported by Rohrer's interleaving research." Nothing here computes
that; it only encodes the learner the rule is for.
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

SAM_ID = "surface_sam"

# Sam's grip on addition is tied to the symbolic format: he has drilled symbolic
# a/b + c/d and pattern-matches it, but the moment the SAME KC appears in another
# representation (area model, number line) his grip collapses (§4.2 P4). The
# format tie is the data that distinguishes Sam from a learner who holds the KC
# format-independently; we attach it to the addition KC because his named
# misconception (add-across) lives on addition. He is held WITH_MISCONCEPTION
# rather than PROCEDURE_ONLY because his within-block "procedure" is actually the
# add-across wrong-answer pattern, not the correct algorithm — the tell is a wrong
# number, unlike Priya's correct-but-unjustified answer.
_SAM_ADDITION_FORMAT = Representation.SYMBOLIC

SAM = PersonaConfig(
    persona_id=SAM_ID,
    name="Surface Sam",
    knowledge={
        KnowledgeComponentId.ADDITION_UNLIKE: KnowledgeState(
            kc_id=KnowledgeComponentId.ADDITION_UNLIKE,
            mode=KnowledgeMode.WITH_MISCONCEPTION,
            format_tied_to=_SAM_ADDITION_FORMAT,
        ),
    },
    # The active misconception, named verbatim from the Layer-1 catalog. add-across
    # applies only to KC_addition_unlike (misconceptions.py), which is exactly the
    # KC Sam is configured on, so the schema's applicability check passes.
    misconceptions=(MisconceptionId.ADD_ACROSS_ERROR,),
    behavior=BehavioralParameters(
        # Fluent *inside* a format block, so he answers at a moderate clip — faster
        # than methodical Priya, not a sub-2s guesser like Cleo.
        response_latency_seconds=6.0,
        # He has a (wrong) procedure he applies confidently within a block, so he
        # asks for hints only occasionally.
        hint_request_probability=0.2,
        # He engages with the problem (he is trying to apply his pattern), so
        # engagement is reasonable — his failure is conceptual, not disengagement.
        engagement_floor=0.7,
        # He leans on the format's familiarity rather than on UI scaffolds; low.
        scaffold_dependence_rate=0.2,
    ),
)
