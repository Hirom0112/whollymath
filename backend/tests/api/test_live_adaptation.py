"""Tests for projecting a sustained live state into the wire AdaptationView (Slice HR.B4)."""

from __future__ import annotations

from app.api.live_adaptation import propose_adaptation_view
from app.domain.knowledge_components import KnowledgeComponentId
from app.policy.state_classifier import LearnerState
from app.policy.surface_states import SurfaceState

_ADD = KnowledgeComponentId.ADDITION_UNLIKE


def test_confused_projects_a_morph_view() -> None:
    view = propose_adaptation_view(LearnerState.CONFUSED, _ADD, SurfaceState.SYMBOLIC_FOCUS)
    assert view is not None
    assert view.state == "confused"
    assert view.is_morph is True
    assert view.reason.strip()


def test_idle_projects_a_nudge_only_view() -> None:
    view = propose_adaptation_view(LearnerState.IDLE_AVOIDING, _ADD, SurfaceState.SYMBOLIC_FOCUS)
    assert view is not None
    assert view.state == "idle_avoiding"
    assert view.is_morph is False  # a nudge never changes the surface (refuse-rule 3)


def test_productive_struggle_projects_no_view() -> None:
    # The policy protects a productive struggle (NoChange) → nothing surfaces.
    assert (
        propose_adaptation_view(
            LearnerState.PRODUCTIVE_STRUGGLE, _ADD, SurfaceState.FRACTION_BARS_PRIMARY
        )
        is None
    )


def test_morph_to_current_surface_projects_no_view() -> None:
    # Confused but already on the lesson's manipulative → no churn → None.
    assert (
        propose_adaptation_view(LearnerState.CONFUSED, _ADD, SurfaceState.FRACTION_BARS_PRIMARY)
        is None
    )
