"""Contract tests for the remediation wire projection (Slice P0.3 / §11.5).

The ``RemediationView`` is what T3's expand-in-place remediation panel renders. These pin the
projection from the policy ``LessonFlow``: hidden while working the parent lesson, populated (with
resolved KC names + a resume hint) while in the "R" state.
"""

from __future__ import annotations

from app.api.remediation_view import build_remediation_view
from app.domain.knowledge_components import KnowledgeComponentId, get_kc
from app.policy.remediation_flow import (
    LessonFlow,
    RemediationContext,
    RemediationTriggered,
    apply,
    in_lesson,
)

_PARENT = KnowledgeComponentId.ADDITION_UNLIKE
_PREREQ = KnowledgeComponentId.EQUIVALENCE


def _paused_flow(paused_at: int = 3) -> LessonFlow:
    ctx = RemediationContext(
        parent_kc=_PARENT,
        prerequisite_kc=_PREREQ,
        paused_at_index=paused_at,
        reason="Let's shore up a basic first: equivalent fractions.",
    )
    return apply(in_lesson(), RemediationTriggered(context=ctx))


def test_in_lesson_flow_has_no_view() -> None:
    """Working the grade-level lesson → no panel (§11.5: hidden for a fluent learner)."""
    assert build_remediation_view(in_lesson()) is None


def test_in_remediation_projects_the_panel() -> None:
    """The "R" state projects the paused parent + the prerequisite sub-section."""
    view = build_remediation_view(_paused_flow(paused_at=4))
    assert view is not None
    assert view.prerequisite_kc == _PREREQ.value
    assert view.parent_kc == _PARENT.value
    assert view.parent_progress_done == 4  # the resume point (filled dots)
    assert view.reason == "Let's shore up a basic first: equivalent fractions."


def test_labels_are_the_registered_skill_names() -> None:
    """Display labels resolve to the KCs' registered skill names (both are content-complete KCs)."""
    view = build_remediation_view(_paused_flow())
    assert view is not None
    assert view.prerequisite_label == get_kc(_PREREQ).skill_name
    assert view.parent_label == get_kc(_PARENT).skill_name


def test_resume_hint_names_the_parent_lesson() -> None:
    """The resume hint tells the learner what finishing the prerequisite unlocks (§11.5)."""
    view = build_remediation_view(_paused_flow())
    assert view is not None
    assert get_kc(_PARENT).skill_name in view.resume_hint
    assert view.resume_hint.startswith("Finish this to keep going with")
