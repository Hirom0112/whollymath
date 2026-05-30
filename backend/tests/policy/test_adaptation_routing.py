"""Tests for routing a sustained learner state to its labeled adaptation (Slice HR.B3).

Pins each state's move through next_transition(AdaptationProposed), and the refuse layer baked in:
productive-struggle is protected, idle only nudges, fluent-ready is offered not forced.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.policy.state_classifier import LearnerState
from app.policy.surface_states import SurfaceState
from app.policy.transitions import (
    AdaptationProposed,
    NoChange,
    Nudge,
    StateChange,
    Transition,
    next_transition,
)

_ADD = KnowledgeComponentId.ADDITION_UNLIKE
_NL = KnowledgeComponentId.NUMBER_LINE_PLACEMENT


def _route(
    state: LearnerState, *, current: SurfaceState, kc: KnowledgeComponentId = _ADD
) -> Transition:
    return next_transition(current, AdaptationProposed(state=state, kc=kc))


def test_productive_struggle_is_protected_no_change() -> None:
    t = _route(LearnerState.PRODUCTIVE_STRUGGLE, current=SurfaceState.FRACTION_BARS_PRIMARY)
    assert isinstance(t, NoChange)


def test_idle_avoiding_nudges_never_changes_state() -> None:
    t = _route(LearnerState.IDLE_AVOIDING, current=SurfaceState.SYMBOLIC_FOCUS)
    assert isinstance(t, Nudge)
    assert t.to_state is SurfaceState.SYMBOLIC_FOCUS


def test_fluent_ready_offers_fade_to_symbolic() -> None:
    t = _route(LearnerState.FLUENT_READY, current=SurfaceState.NUMBER_LINE_PRIMARY)
    assert isinstance(t, StateChange)
    assert t.to_state is SurfaceState.SYMBOLIC_FOCUS


def test_fluent_ready_already_symbolic_is_no_change() -> None:
    t = _route(LearnerState.FLUENT_READY, current=SurfaceState.SYMBOLIC_FOCUS)
    assert isinstance(t, NoChange)


def test_pattern_matching_brings_transfer_probe_forward() -> None:
    t = _route(LearnerState.PATTERN_MATCHING, current=SurfaceState.SYMBOLIC_FOCUS)
    assert isinstance(t, StateChange)
    assert t.to_state is SurfaceState.TRANSFER_PROBE


def test_confused_morphs_to_the_lessons_primary_manipulative() -> None:
    # Addition's primary remediation representation is the fraction bars (S3).
    t = _route(LearnerState.CONFUSED, current=SurfaceState.SYMBOLIC_FOCUS, kc=_ADD)
    assert isinstance(t, StateChange)
    assert t.to_state is SurfaceState.FRACTION_BARS_PRIMARY
    assert t.label.strip()


def test_guessing_slows_down_with_the_manipulative() -> None:
    t = _route(LearnerState.GUESSING, current=SurfaceState.SYMBOLIC_FOCUS, kc=_ADD)
    assert isinstance(t, StateChange)
    assert t.to_state is SurfaceState.FRACTION_BARS_PRIMARY
    assert "slow down" in t.label.lower()


def test_confused_when_already_on_target_is_no_change() -> None:
    # Number-line placement's manipulative is the number line; already there → no churn.
    t = _route(LearnerState.CONFUSED, current=SurfaceState.NUMBER_LINE_PRIMARY, kc=_NL)
    assert isinstance(t, NoChange)
