"""Tests pinning Procedure Priya's config to PROJECT.md §4.2 Persona 2 (Slice 2.2).

These assert the DATA Priya's config encodes — knowledge state, active
misconception, behavior — matches §4.2. They do NOT assert behavior (e.g. that she
actually fails a specific error-finding item): that is the Layer-3 simulator's job,
a separate later slice (CLAUDE.md §2; PROJECT.md §4.1). What we pin here is that the
config would feed the simulator the right inputs to produce §4.2's behavior.
"""

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.misconceptions import MISCONCEPTION_REGISTRY, MisconceptionId
from app.personas.persona_config import KnowledgeMode
from app.personas.priya import PRIYA


def test_priya_carries_procedure_without_concept_misconception() -> None:
    """§4.2: 'the procedure is the math' maps to the procedure-without-concept misconception."""
    assert PRIYA.misconceptions == (MisconceptionId.PROCEDURE_WITHOUT_CONCEPT,)


def test_priya_holds_the_algorithm_kcs_in_procedure_only_mode() -> None:
    """§4.2: find-common-denom / convert / add held PROCEDURE_ONLY (right answer, no concept)."""
    for kc_id in (
        KnowledgeComponentId.COMMON_DENOMINATOR,
        KnowledgeComponentId.ADDITION_UNLIKE,
        KnowledgeComponentId.SUBTRACTION_UNLIKE,
    ):
        assert PRIYA.mode_for(kc_id) is KnowledgeMode.PROCEDURE_ONLY


def test_priya_is_never_in_concept_or_both_mode() -> None:
    """§4.2: she does not know *why* — so no KC may be CONCEPT_ONLY or BOTH.

    This is the core §4.2 distinction: procedural fluency without conceptual
    understanding. If any KC were CONCEPT_ONLY/BOTH, she would be able to explain
    why and would pass error-finding, which contradicts the persona.
    """
    modes = {state.mode for state in PRIYA.knowledge.values()}
    assert KnowledgeMode.CONCEPT_ONLY not in modes
    assert KnowledgeMode.BOTH not in modes


def test_priya_would_fail_error_finding_via_her_misconception() -> None:
    """§4.2: 'fails error-finding items'. Encoded by carrying procedure-without-concept.

    We assert the encoding, not the behavior: the misconception she carries is the
    one whose generator (misconceptions.py) yields the correct answer flagged
    ``can_justify=False`` — i.e. it is the documented basis for failing error-finding
    / 'explain why'. The Layer-3 simulator turns that into the actual failure.
    """
    assert MisconceptionId.PROCEDURE_WITHOUT_CONCEPT in PRIYA.misconceptions
    misconception = MISCONCEPTION_REGISTRY.get(MisconceptionId.PROCEDURE_WITHOUT_CONCEPT)
    # The misconception applies to the operation KCs Priya runs.
    assert KnowledgeComponentId.ADDITION_UNLIKE in misconception.applicable_kcs


def test_priya_has_low_hint_use_and_high_engagement() -> None:
    """§4.2: 'slow but correct' — she runs the procedure unaided, so low hints, high engagement."""
    assert PRIYA.behavior.hint_request_probability <= 0.2
    assert PRIYA.behavior.engagement_floor >= 0.7
    assert PRIYA.behavior.scaffold_dependence_rate <= 0.3


def test_priya_latency_is_deliberate_not_a_snap_guess() -> None:
    """§4.2: 'slow but correct' — her think-time is well above a sub-2s guesser's."""
    assert PRIYA.behavior.response_latency_seconds > 2.0


def test_priya_references_only_real_kc_and_misconception_ids() -> None:
    """Priya's config names only real Layer-1 ids (the single-source-of-truth invariant)."""
    for kc_id in PRIYA.knowledge:
        assert isinstance(kc_id, KnowledgeComponentId)
    for misconception_id in PRIYA.misconceptions:
        # Resolvable through the registry == it is a real catalog id.
        assert MISCONCEPTION_REGISTRY.get(misconception_id).id is misconception_id
