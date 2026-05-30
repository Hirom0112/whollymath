"""Capable Cora — the competent learner (the positive-control persona), as DATA.

The five committed personas (PROJECT.md §4.2) are NEGATIVE controls: each is deficient
in exactly one way (Priya procedure-only, Sam format-tied, Nate natural-number bias,
Hugo hint-dependent, Cleo click-through), so none holds ``KnowledgeMode.BOTH`` and none
can pass the S5 transfer probe. They exist to catch a mastery model that declares
mastery too easily. But a harness of only negative controls can never show what success
looks like — every learner stalls below confirmed mastery.

Cora is the POSITIVE control the harness's §4.1 extensibility explicitly anticipates
("adding a sixth persona is editing this tuple plus a new data module"): a learner who
genuinely understands the five fraction-foundation KCs — concept AND procedure — so she
answers correctly across representations, can justify, catches error-finding items, and
therefore CONFIRMS mastery through the real turn loop. She is what proves the mastery
model also ACCEPTS real mastery (not just rejects fake mastery), and she gives the
persona-bot demo class a genuine "on-track, mastered" student instead of an all-0% roster
(student_bots.py finding #1). Added on owner direction 2026-05-30; the planning docs are
gitignored and absent from this checkout, so this commit message + module docstring are
the tracked decision-log entry (CLAUDE.md §1, §8.4).

Field-by-field:
  - Knowledge state: BOTH (concept + procedure) on every live fraction KC (``LIVE_KCS``),
    format-independent (no ``format_tied_to`` — her grip does not collapse out of one
    representation, the anti-Sam). BOTH mode makes the Layer-3 simulator answer correctly,
    justify, and correctly REJECT a wrong claimed answer on a FIND_ERROR turn — the three
    things the transfer probe checks.
  - Misconceptions: NONE — she is the clean control.
  - Behavior: a thoughtful but not slow worker; LOW hint use (she rarely needs a scaffold,
    so she accrues the UNSCAFFOLDED correct answers the §3.4 rule-3 mastery gate requires);
    high engagement; low scaffold dependence.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS
from app.personas.persona_config import (
    BehavioralParameters,
    KnowledgeMode,
    KnowledgeState,
    PersonaConfig,
)

CORA_ID = "capable_cora"

CORA = PersonaConfig(
    persona_id=CORA_ID,
    name="Capable Cora",
    # Genuine understanding of every content-complete fraction KC. BOTH (not PROCEDURE_ONLY
    # like Priya, not WITH_MISCONCEPTION like Sam) and format-independent, so she answers
    # correctly in any representation the scheduler interleaves and passes the multi-format +
    # error-finding transfer probe — the one persona who confirms mastery.
    knowledge={kc_id: KnowledgeState(kc_id=kc_id, mode=KnowledgeMode.BOTH) for kc_id in LIVE_KCS},
    misconceptions=(),
    behavior=BehavioralParameters(
        # Deliberate but fluent — she reasons rather than snap-guesses, but is not laboring
        # like procedure-bound Priya.
        response_latency_seconds=5.0,
        # She rarely needs help, so most of her correct answers are UNSCAFFOLDED — the
        # evidence the §3.4 rule-3 gate (>=1 unassisted correct) requires to declare mastery.
        hint_request_probability=0.05,
        # She genuinely does the work.
        engagement_floor=0.9,
        # Self-sufficient; she does not lean on scaffolds.
        scaffold_dependence_rate=0.05,
    ),
)
