"""Tests for the mid-problem proactive-help decision (Beat 1)."""

from __future__ import annotations

from app.helpneed.live_signal_features import LiveSignalFeatures
from app.policy.mid_problem_help import should_offer_mid_problem_help


def _features(
    *,
    ttfi_ms: int | None = 3000,
    attempts: int = 0,
    revisions: int = 0,
    idle: int = 0,
    hints: int = 0,
) -> LiveSignalFeatures:
    return LiveSignalFeatures(
        time_to_first_interaction_ms=ttfi_ms,
        current_attempts=attempts,
        current_revisions=revisions,
        current_idle_events=idle,
        current_hint_requests=hints,
        current_requested_answer=False,
        recent_attempts_mean=0.0,
        recent_revisions_mean=0.0,
        recent_idle_mean=0.0,
        recent_hint_rate=0.0,
        recent_give_up_rate=0.0,
        problems_seen=1,
    )


def test_offers_on_sustained_idle() -> None:
    assert should_offer_mid_problem_help(_features(idle=2)) is True


def test_offers_on_many_edits_without_submit() -> None:
    assert should_offer_mid_problem_help(_features(revisions=5)) is True


def test_offers_on_long_freeze_before_first_touch() -> None:
    assert should_offer_mid_problem_help(_features(ttfi_ms=25_000)) is True


def test_quiet_when_working_normally() -> None:
    assert should_offer_mid_problem_help(_features(ttfi_ms=2000, revisions=1, idle=0)) is False


def test_silent_after_submit() -> None:
    # Once they've submitted, the turn loop owns the response — not a mid-problem nudge.
    assert should_offer_mid_problem_help(_features(attempts=1, idle=3)) is False


def test_silent_if_they_already_asked_for_a_hint() -> None:
    assert should_offer_mid_problem_help(_features(idle=3, hints=1)) is False
