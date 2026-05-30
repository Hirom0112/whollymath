"""Tests for the reactive-remediation flow state machine (Slice P0.3).

Mandatory-TDD (CLAUDE.md §2, §9): this is policy state-transition logic, so each rule from
CURRICULUM_STANDARD.md §11 gets a test that pins it. The machine is a SEPARATE axis from the five
visual ``SurfaceState``s — it tracks whether the grade-level (parent) lesson is running or PAUSED
while a nested prerequisite lesson runs (the "R" state), and the edge that RESUMES the parent at the
exact problem it paused on.

Pure / deterministic (no SymPy, LLM, DB): same (flow, event) → same next flow.
"""

from __future__ import annotations

import pytest
from app.domain.knowledge_components import KnowledgeComponentId
from app.policy.remediation_flow import (
    LessonFlowState,
    RemediationCleared,
    RemediationContext,
    RemediationTriggered,
    apply,
    in_lesson,
)

_PARENT = KnowledgeComponentId.ADDITION_UNLIKE
_PREREQ = KnowledgeComponentId.EQUIVALENCE
_OTHER_PREREQ = KnowledgeComponentId.COMMON_DENOMINATOR


def _ctx(paused_at: int = 3) -> RemediationContext:
    return RemediationContext(
        parent_kc=_PARENT,
        prerequisite_kc=_PREREQ,
        paused_at_index=paused_at,
        reason="Let's shore up a basic first: equivalent fractions.",
    )


def test_initial_flow_is_in_lesson() -> None:
    """A fresh lesson is IN_LESSON with no active remediation."""
    flow = in_lesson()
    assert flow.state is LessonFlowState.IN_LESSON
    assert flow.remediation is None


def test_trigger_drops_into_remediation_carrying_the_context() -> None:
    """IN_LESSON + RemediationTriggered → IN_REMEDIATION ("R"), parent paused, context carried.

    CURRICULUM_STANDARD.md §11: a struggling learner is reactively dropped to the prerequisite the
    lesson rests on; the parent PAUSES (it is not reset).
    """
    ctx = _ctx(paused_at=4)
    flow = apply(in_lesson(), RemediationTriggered(context=ctx))
    assert flow.state is LessonFlowState.IN_REMEDIATION
    assert flow.remediation == ctx
    assert flow.remediation is not None
    assert flow.remediation.prerequisite_kc is _PREREQ
    assert flow.remediation.paused_at_index == 4


def test_clear_resumes_the_parent_lesson() -> None:
    """IN_REMEDIATION + RemediationCleared → back IN_LESSON, remediation cleared (§11.4 hard gate).

    The resume point lived in the context while paused, so the caller can return the learner to the
    exact problem the parent paused on (remediation pauses, never resets, the parent — §11.4).
    """
    paused = apply(in_lesson(), RemediationTriggered(context=_ctx(paused_at=4)))
    assert paused.remediation is not None
    resume_at = paused.remediation.paused_at_index  # caller reads the resume point before clearing

    resumed = apply(paused, RemediationCleared())
    assert resumed.state is LessonFlowState.IN_LESSON
    assert resumed.remediation is None
    assert resume_at == 4  # the parent resumes where it paused


def test_one_level_only_nested_trigger_is_a_noop() -> None:
    """IN_REMEDIATION + RemediationTriggered → UNCHANGED (one level only — §11.1: foundations end).

    If the learner also struggles inside the prerequisite, they STAY and work it; no further
    auto-drop ("no rabbit holes"). The original remediation context is preserved.
    """
    paused = apply(in_lesson(), RemediationTriggered(context=_ctx()))
    nested = apply(
        paused,
        RemediationTriggered(
            context=RemediationContext(
                parent_kc=_PREREQ,
                prerequisite_kc=_OTHER_PREREQ,
                paused_at_index=1,
                reason="(should be ignored)",
            )
        ),
    )
    assert nested == paused  # no change: still in the FIRST remediation, original context intact
    assert nested.remediation is not None
    assert nested.remediation.prerequisite_kc is _PREREQ


def test_clear_while_in_lesson_is_a_noop() -> None:
    """RemediationCleared with no active remediation is a no-op (defensive; never raises)."""
    flow = in_lesson()
    assert apply(flow, RemediationCleared()) == flow


def test_flow_and_context_are_immutable() -> None:
    """The flow and its context are frozen — a routed decision is a fact, not mutable state."""
    flow = apply(in_lesson(), RemediationTriggered(context=_ctx()))
    with pytest.raises(AttributeError):
        flow.state = LessonFlowState.IN_LESSON  # type: ignore[misc]
    assert flow.remediation is not None
    with pytest.raises(AttributeError):
        flow.remediation.paused_at_index = 0  # type: ignore[misc]
