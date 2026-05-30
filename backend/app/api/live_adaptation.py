"""Project a sustained live state into the wire ``AdaptationView`` (Slice HR.B4).

The bridge between the policy decision (HR.B3 ``next_transition`` on an ``AdaptationProposed``
event) and the API contract: given the classified learner state (HR.B2), the lesson's KC, and the
current surface, it runs the policy and shapes the result into the ``AdaptationView`` the surface
renders — or ``None`` when the policy declines to act (a protected productive-struggle, or a morph
that targets the surface the learner is already on).

Lives in the API layer (not ``policy``) because it produces a wire schema — keeping ``policy`` free
of any ``schemas`` import (CLAUDE.md §7). Pure and deterministic; the LLM only voices an
already-decided adaptation downstream (HYPERREACTIVE §2.3). The morph TARGET is carried by the
turn's ``next_surface_state`` (the service applies the transition); this view only annotates WHY.
"""

from __future__ import annotations

from app.api.schemas import AdaptationView
from app.domain.knowledge_components import KnowledgeComponentId
from app.policy.state_classifier import LearnerState
from app.policy.surface_states import SurfaceState
from app.policy.transitions import (
    AdaptationProposed,
    NoChange,
    StateChange,
    next_transition,
)


def propose_adaptation_view(
    state: LearnerState,
    kc: KnowledgeComponentId,
    current_surface: SurfaceState,
) -> AdaptationView | None:
    """The ``AdaptationView`` for a sustained ``state`` on a lesson, or ``None`` if no action.

    Runs the HR.B3 policy mapping and projects it: a ``StateChange`` is a morph (``is_morph=True``;
    the new surface is the transition's target, surfaced separately on ``next_surface_state``), a
    ``Nudge`` is a nudge-only (``is_morph=False`` — e.g. idle, refuse-rule 3), and a ``NoChange``
    means the policy declined (protected struggle, or already on the target) → ``None``.
    """
    transition = next_transition(current_surface, AdaptationProposed(state=state, kc=kc))
    if isinstance(transition, NoChange):
        return None
    return AdaptationView(
        state=state.value,
        reason=transition.label,
        is_morph=isinstance(transition, StateChange),
    )


__all__ = ["propose_adaptation_view"]
