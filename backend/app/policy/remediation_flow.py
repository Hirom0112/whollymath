"""The reactive-remediation flow state machine (Slice P0.3).

A SECOND state axis next to the five visual ``SurfaceState``s (``surface_states.py``). The surface
states describe *how the current problem is shown*; this describes *which lesson the learner is in*
— the grade-level (parent) lesson, or a nested prerequisite lesson they were reactively dropped to.

The model (CURRICULUM_STANDARD.md §11, owner decision 2026-05-29): when the help-detector gate trips
inside a grade-level lesson, the learner is **dropped to the prerequisite the lesson rests on**,
**pauses** the parent (never resets it), masters the prerequisite (the §11.4 hard gate), then
**resumes the parent at the exact problem it paused on**. The prerequisite KC and the resume point
are carried in a ``RemediationContext`` while paused.

Scope of THIS slice: the pure state machine only — the ``RemediationTriggered`` event, the
``IN_REMEDIATION`` ("R") state, and the resume-parent edge. It does NOT decide *when* to trigger
(that is the HelpNeed gate, ``policy/intervention_gate.py``) or *which* prerequisite to drop to
(that is the prereq map, ``domain/prerequisites.py``) or orchestrate the pause/run/resume across
sessions (the router, Slice P0.4). It takes those as inputs and routes the flow.

Pure / deterministic (CLAUDE.md §7, §8.1/§8.2; ARCHITECTURE.md §14): no SymPy, no LLM, no DB — the
same ``(flow, event)`` always yields the same next flow. Frozen dataclasses: a routed flow is a fact
about where the learner is, not mutable state (CLAUDE.md §8.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.knowledge_components import KnowledgeComponentId


class LessonFlowState(StrEnum):
    """Which lesson the learner is in — the remediation axis (CURRICULUM_STANDARD.md §11).

    ``IN_REMEDIATION`` is the "R" state: the grade-level (parent) lesson is PAUSED while a nested
    prerequisite lesson runs. A ``StrEnum`` so it serializes as its stable string for the DB/API.
    """

    IN_LESSON = "in_lesson"  # working the grade-level (parent) lesson normally
    IN_REMEDIATION = "in_remediation"  # parent paused; working the nested prerequisite ("R")


@dataclass(frozen=True)
class RemediationContext:
    """What is captured when a learner is dropped into remediation — enough to render it and resume.

    - ``parent_kc``         the grade-level lesson that paused (the one to resume).
    - ``prerequisite_kc``   the foundation skill dropped to (chosen upstream from the prereq map).
    - ``paused_at_index``   the parent's served-problem index when it paused — the RESUME point, so
      the parent continues where it left off rather than restarting (§11.4: pauses, never resets).
    - ``reason``            the one-line on-screen label (§11.5 "Let's shore up a basic first: …"),
      so the surface always explains the drop (mirrors the §3.8 refuse-rule-4 labelling discipline).
    """

    parent_kc: KnowledgeComponentId
    prerequisite_kc: KnowledgeComponentId
    paused_at_index: int
    reason: str


@dataclass(frozen=True)
class RemediationTriggered:
    """Signal: the learner should be dropped into remediation now (the gate tripped / probe failed).

    Carries the fully-resolved ``RemediationContext`` — WHEN to fire and WHICH prerequisite to drop
    to are decided upstream (the HelpNeed gate and the prereq map); this machine only routes the
    flow on the resulting decision.
    """

    context: RemediationContext


@dataclass(frozen=True)
class RemediationCleared:
    """Signal: the nested prerequisite was mastered (the §11.4 hard gate) — resume the parent.

    No payload: the resume point lives in the active flow's ``RemediationContext`` until it clears.
    """


# A flow event is one of these signals.
RemediationEvent = RemediationTriggered | RemediationCleared


@dataclass(frozen=True)
class LessonFlow:
    """The remediation-axis state: which lesson the learner is in, plus the paused-parent context.

    ``remediation`` is non-``None`` exactly when ``state`` is ``IN_REMEDIATION`` — it holds the
    paused parent's resume point and the prerequisite being worked. Frozen (a fact, not mutable
    state); the machine returns a NEW ``LessonFlow`` per event.
    """

    state: LessonFlowState
    remediation: RemediationContext | None


def in_lesson() -> LessonFlow:
    """The initial flow: working the grade-level lesson, no remediation active."""
    return LessonFlow(state=LessonFlowState.IN_LESSON, remediation=None)


def apply(flow: LessonFlow, event: RemediationEvent) -> LessonFlow:
    """Route one flow event to the next ``LessonFlow`` (the single entry point).

    The rules (CURRICULUM_STANDARD.md §11), each pinned by a test:
      - ``IN_LESSON`` + ``RemediationTriggered`` → ``IN_REMEDIATION`` carrying the context (drop in,
        parent pauses — §11; the resume point is recorded so the parent continues, not restarts).
      - ``IN_REMEDIATION`` + ``RemediationCleared`` → ``IN_LESSON`` with the context cleared (the
        §11.4 hard gate passed; the caller resumes the parent at ``paused_at_index``).
      - ``IN_REMEDIATION`` + ``RemediationTriggered`` → **no change** (one level only — §11.1: the
        foundation layer is terminal; a learner struggling inside the prerequisite STAYS and works
        it, no rabbit-hole auto-drop). The original context is preserved.
      - ``IN_LESSON`` + ``RemediationCleared`` → no change (defensive; nothing to resume).
    """
    if isinstance(event, RemediationTriggered):
        if flow.state is LessonFlowState.IN_REMEDIATION:
            return flow  # one level only — no nested auto-drop (§11.1)
        return LessonFlow(state=LessonFlowState.IN_REMEDIATION, remediation=event.context)

    # RemediationCleared — the only other variant.
    if flow.state is LessonFlowState.IN_REMEDIATION:
        return in_lesson()
    return flow  # nothing to resume


__all__ = [
    "LessonFlow",
    "LessonFlowState",
    "RemediationCleared",
    "RemediationContext",
    "RemediationEvent",
    "RemediationTriggered",
    "apply",
    "in_lesson",
]
