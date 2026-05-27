"""Tests pinning Surface Sam's config to PROJECT.md §4.2 Persona 4 (Slice 2.2).

These assert the DATA Sam's config encodes — format-tied knowledge, active
misconception, behavior — matches §4.2. They do NOT assert behavior (e.g. that his
accuracy actually collapses when the format changes): that is the Layer-3
simulator's job, a separate later slice (CLAUDE.md §2; PROJECT.md §4.1).
"""

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import MISCONCEPTION_REGISTRY, MisconceptionId
from app.personas.persona_config import KnowledgeMode
from app.personas.sam import SAM


def test_sam_carries_add_across_misconception() -> None:
    """§4.2: Sam carries the add-across error (¼ + ¼ = 2/8, his signature in §3.5/§3.9)."""
    assert SAM.misconceptions == (MisconceptionId.ADD_ACROSS_ERROR,)


def test_sam_addition_knowledge_is_format_tied() -> None:
    """§4.2: 'knows the procedure for the most recent format he saw' — KC tied to one format.

    The format tie is the structural fingerprint distinguishing Sam from a learner
    who holds the KC format-independently. The Layer-3 simulator reads it to make
    accuracy 'drop to baseline the moment format changes'.
    """
    addition_state = SAM.knowledge[KnowledgeComponentId.ADDITION_UNLIKE]
    assert addition_state.format_tied_to is not None
    assert isinstance(addition_state.format_tied_to, Representation)


def test_sam_holds_addition_with_misconception_not_genuine_mastery() -> None:
    """§4.2: his within-block 'procedure' is the add-across wrong pattern, not the algorithm."""
    assert SAM.mode_for(KnowledgeComponentId.ADDITION_UNLIKE) is KnowledgeMode.WITH_MISCONCEPTION
    modes = {state.mode for state in SAM.knowledge.values()}
    assert KnowledgeMode.BOTH not in modes


def test_sam_add_across_lives_on_the_addition_kc() -> None:
    """The add-across misconception is defined on KC_addition_unlike, the KC Sam holds it on."""
    misconception = MISCONCEPTION_REGISTRY.get(MisconceptionId.ADD_ACROSS_ERROR)
    assert misconception.applicable_kcs == (KnowledgeComponentId.ADDITION_UNLIKE,)
    assert KnowledgeComponentId.ADDITION_UNLIKE in SAM.knowledge


def test_sam_engages_within_a_block() -> None:
    """§4.2: 'near-100% within a block' — he engages; his failure is conceptual."""
    assert SAM.behavior.engagement_floor >= 0.5
    assert SAM.behavior.scaffold_dependence_rate <= 0.3


def test_sam_references_only_real_kc_and_misconception_ids() -> None:
    """Sam's config names only real Layer-1 ids (the single-source-of-truth invariant)."""
    for kc_id in SAM.knowledge:
        assert isinstance(kc_id, KnowledgeComponentId)
    for misconception_id in SAM.misconceptions:
        assert MISCONCEPTION_REGISTRY.get(misconception_id).id is misconception_id
