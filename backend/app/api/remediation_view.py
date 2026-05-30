"""Project the remediation flow into the wire ``RemediationView`` (Slice P0.3 / §11.5).

The bridge between the policy flow (``policy/remediation_flow.py``) and the API contract the surface
renders: given the learner's current ``LessonFlow``, it shapes the active remediation (if any) into
the ``RemediationView`` T3's expand-in-place panel renders — or ``None`` when the learner is working
the grade-level lesson normally (nothing to show).

Lives in the API layer (not ``policy``) because it produces a wire schema and reads KC display names
from the registry — keeping ``policy`` free of any ``schemas`` import (CLAUDE.md §7). Pure and
deterministic: same flow → same view.
"""

from __future__ import annotations

from app.api.schemas import RemediationView
from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, get_kc
from app.policy.remediation_flow import LessonFlow, LessonFlowState


def _label(kc: KnowledgeComponentId) -> str:
    """A human-readable name for a KC — its registered skill name, or the id for an unbuilt KC.

    The prerequisite is always a content-complete foundation KC, so it resolves; the parent is the
    grade-level lesson, also currently always live. The fallback keeps the projection total (never
    raises) if a not-yet-built KC ever reaches it.
    """
    if kc in LIVE_KCS:
        return get_kc(kc).skill_name
    return kc.value


def build_remediation_view(flow: LessonFlow) -> RemediationView | None:
    """The ``RemediationView`` for the current flow, or ``None`` when not in remediation.

    ``None`` while ``IN_LESSON`` (the panel is hidden — §11.5: the sub-row appears only when the
    gate fires, invisible for a fluent learner). While ``IN_REMEDIATION`` it projects the paused
    parent + the prerequisite sub-section from the flow's context, building the resume hint from the
    parent's name so the surface reads "Finish this to keep going with <parent lesson>".
    """
    if flow.state is not LessonFlowState.IN_REMEDIATION or flow.remediation is None:
        return None
    ctx = flow.remediation
    parent_label = _label(ctx.parent_kc)
    return RemediationView(
        prerequisite_kc=ctx.prerequisite_kc.value,
        prerequisite_label=_label(ctx.prerequisite_kc),
        parent_kc=ctx.parent_kc.value,
        parent_label=parent_label,
        parent_progress_done=ctx.paused_at_index,
        reason=ctx.reason,
        resume_hint=f"Finish this to keep going with {parent_label}.",
    )


__all__ = ["build_remediation_view"]
