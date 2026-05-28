"""Contract test for the on-screen three-arm comparison endpoint (Slice 5.3, dashboard).

CLAUDE.md §9: a thin contract test — the shape the dashboard consumes, and the few
guarantees that matter (it is free/deterministic, the adaptive arm denies all five, the
chat column is the pending prediction, static is N/A). The eval logic itself has its own
suite (tests/eval/test_three_arm_comparison.py); here we assert the API exposes it.
"""

from __future__ import annotations

from app.api.app import create_app
from app.api.schemas import ThreeArmComparisonView

from tests.api.asgi_client import get


def test_three_arm_comparison_endpoint_shape() -> None:
    """GET /eval/three-arm-comparison returns the five-persona comparison, no LLM call.

    The committed live-run artifact (chat_baseline_run.json) makes the chat column real:
    chat_live is True and the headline false-positive tallies are present.
    """
    app = create_app()
    status_code, body = get(app, "/eval/three-arm-comparison")
    assert status_code == 200, body

    view = ThreeArmComparisonView.model_validate(body)
    assert view.total == 5
    assert len(view.rows) == 5
    assert view.adaptive_false_positives == 0  # the §8 defense, reproduced
    assert view.chat_live is True  # the recorded live run is committed
    assert view.chat_false_positives == 2  # Hugo + Priya over-claimed (RESEARCH.md §9)


def test_each_arm_renders_with_a_tone() -> None:
    """Every row carries a verdict + tone per arm; adaptive denies all, static N/A, and the
    chat tone is the live verdict (good=denied / bad=false positive) for exactly two."""
    app = create_app()
    _, body = get(app, "/eval/three-arm-comparison")
    view = ThreeArmComparisonView.model_validate(body)

    for row in view.rows:
        assert row.adaptive.tone == "good"  # all five denied
        assert row.static.tone == "neutral"  # no mastery construct
        assert row.chat.tone in {"good", "bad"}  # live verdict, not "pending"
        assert row.problems, "each persona should list the problems it was shown"

    chat_false_positives = sum(1 for row in view.rows if row.chat.tone == "bad")
    assert chat_false_positives == 2
