"""Procedure Priya — the memorizer (PROJECT.md §4.2 Persona 2), as DATA.

This is half of Slice 2.2: a concrete Layer-2 persona config, expressed purely as
data on top of the Slice-2.1 schema (``persona_config.py``). No behavior lives
here — the Layer-3 simulator that turns this config into actions is a separate
later slice (PROJECT.md §4.1). This module just pins Priya's §4.2 spec into the
typed schema.

Priya's §4.2 definition, mapped field-by-field:

  - Knowledge state: "Knows standard algorithms (find common denominator, convert,
    add). Does not know why finding a common denominator is necessary or what
    'common denominator' geometrically means." → every operation KC she runs is
    held in mode ``PROCEDURE_ONLY`` (correct procedure, no concept). She is NOT in
    ``CONCEPT_ONLY`` or ``BOTH`` on those KCs — that is the whole point, and the
    tests pin it.
  - Active misconception: "'The procedure is the math'." → she carries
    ``procedure-without-concept`` (the Layer-1 ``MisconceptionId`` whose generator,
    in ``misconceptions.py``, produces the CORRECT answer with ``can_justify=False``
    — Priya gets routine items right but cannot justify them and fails error-
    finding).
  - Behavior signature: "Slow but correct on standard-form problems; cannot explain
    *why*; fails error-finding items." → normal-to-slow latency, LOW hint use (she
    can run the procedure unaided), high engagement (she does the work), low
    scaffold dependence. The "fails error-finding / can't explain why" behavior is
    carried by the procedure-without-concept mode/misconception, to be enforced by
    the Layer-3 simulator — not by a behavioral number.

Priya forces the mastery rule that there must be an "explain why / find the error"
item per KC and that the transfer probe includes error-finding (PROJECT.md §3.4,
§3.9). Nothing here computes that; it only encodes the learner the rule is for.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId
from app.personas.persona_config import (
    BehavioralParameters,
    KnowledgeMode,
    KnowledgeState,
    PersonaConfig,
)

PRIYA_ID = "procedure_priya"

# The KCs Priya runs as a memorized algorithm. §4.2 names "find common denominator,
# convert, add" explicitly; common-denominator finding and the two unlike-denominator
# operations are the routine-algorithm KCs she has drilled. Each is PROCEDURE_ONLY:
# she executes correctly but holds no concept, so she cannot justify or error-find.
# Equivalence and number-line placement are intentionally left unconfigured (→
# NEITHER via PersonaConfig.mode_for): §4.2 scopes Priya to the operational
# algorithms, not magnitude/equivalence reasoning, and we do not invent grip the
# spec does not grant her (CLAUDE.md §5: don't over-confidently fill gaps).
_PROCEDURE_KCS = (
    KnowledgeComponentId.COMMON_DENOMINATOR,
    KnowledgeComponentId.ADDITION_UNLIKE,
    KnowledgeComponentId.SUBTRACTION_UNLIKE,
)

PRIYA = PersonaConfig(
    persona_id=PRIYA_ID,
    name="Procedure Priya",
    knowledge={
        kc_id: KnowledgeState(kc_id=kc_id, mode=KnowledgeMode.PROCEDURE_ONLY)
        for kc_id in _PROCEDURE_KCS
    },
    # The active misconception, named verbatim from the Layer-1 catalog. Its
    # generator returns the CORRECT answer flagged unjustifiable, which is exactly
    # Priya's "right answer, no reasoning" signature (§4.2 P2; misconceptions.py
    # ProcedureWithoutConceptResult).
    misconceptions=(MisconceptionId.PROCEDURE_WITHOUT_CONCEPT,),
    behavior=BehavioralParameters(
        # "Slow but correct on standard-form problems" (§4.2): a deliberate,
        # methodical worker, slower than a snap-guesser like Nate.
        response_latency_seconds=12.0,
        # She can run the procedure unaided, so she rarely asks for hints — the
        # opposite of Hugo. Low, not zero (occasional check).
        hint_request_probability=0.1,
        # She genuinely does the work; engagement is high (contrast Cleo's floor).
        engagement_floor=0.85,
        # Self-sufficient on routine items; she does not lean on scaffolds.
        scaffold_dependence_rate=0.15,
    ),
)
