"""Unit tests for the in-session 6-state classifier (Slice HR.B2).

Pins each of the six states' firing conditions, the priority ordering (idle/guessing win over a
streak; idle wins over confused), and the productive-struggle default.
"""

from __future__ import annotations

from app.helpneed.live_signal_features import LiveSignalFeatures
from app.policy.state_classifier import LearnerState, classify_state


def _features(
    *,
    ttfi_ms: int | None = 4000,
    attempts: int = 1,
    revisions: int = 1,
    idle: int = 0,
    hints: int = 0,
    requested_answer: bool = False,
) -> LiveSignalFeatures:
    """A neutral, engaged learner by default; tests override the fields a state keys on."""
    return LiveSignalFeatures(
        time_to_first_interaction_ms=ttfi_ms,
        current_attempts=attempts,
        current_revisions=revisions,
        current_idle_events=idle,
        current_hint_requests=hints,
        current_requested_answer=requested_answer,
        recent_attempts_mean=float(attempts),
        recent_revisions_mean=float(revisions),
        recent_idle_mean=float(idle),
        recent_hint_rate=0.0,
        recent_give_up_rate=0.0,
        problems_seen=4,
    )


def _classify(features: LiveSignalFeatures, **ctx: object) -> LearnerState:
    defaults: dict[str, object] = {
        "helpneed_score": 0.4,
        "correct_streak_no_hint": 0,
        "distinct_recent_representations": 1,
    }
    defaults.update(ctx)
    return classify_state(features, **defaults)  # type: ignore[arg-type]


def test_idle_avoiding_on_idle_pings() -> None:
    assert _classify(_features(idle=2)) is LearnerState.IDLE_AVOIDING


def test_idle_avoiding_when_never_touched_and_idle() -> None:
    assert _classify(_features(ttfi_ms=None, idle=1)) is LearnerState.IDLE_AVOIDING


def test_guessing_on_fast_shallow_repeated_submits() -> None:
    feats = _features(ttfi_ms=800, attempts=3, revisions=0)
    assert _classify(feats) is LearnerState.GUESSING


def test_fluent_ready_on_unassisted_streak_across_reps() -> None:
    state = _classify(
        _features(),
        helpneed_score=0.2,
        correct_streak_no_hint=3,
        distinct_recent_representations=2,
    )
    assert state is LearnerState.FLUENT_READY


def test_pattern_matching_streak_in_one_representation() -> None:
    state = _classify(
        _features(),
        helpneed_score=0.2,
        correct_streak_no_hint=3,
        distinct_recent_representations=1,
    )
    assert state is LearnerState.PATTERN_MATCHING


def test_confused_on_high_helpneed_with_engagement() -> None:
    assert _classify(_features(attempts=3), helpneed_score=0.8) is LearnerState.CONFUSED


def test_productive_struggle_is_the_default() -> None:
    # Engaged, moderate help need, no streak, not fast/shallow, not idle → protect the struggle.
    assert _classify(_features(attempts=2, revisions=2), helpneed_score=0.45) is (
        LearnerState.PRODUCTIVE_STRUGGLE
    )


def test_idle_wins_over_confused() -> None:
    # A high help-need score does NOT override idle — a pause is never struggle (refuse-rule 3).
    assert _classify(_features(idle=3), helpneed_score=0.9) is LearnerState.IDLE_AVOIDING


def test_guessing_wins_over_a_streak() -> None:
    # Fast, shallow, repeated submits read as guessing even with a nominal correct streak.
    feats = _features(ttfi_ms=500, attempts=3, revisions=0)
    state = _classify(
        feats, correct_streak_no_hint=3, distinct_recent_representations=2, helpneed_score=0.2
    )
    assert state is LearnerState.GUESSING


def test_fluent_requires_low_helpneed() -> None:
    # A streak across reps but with elevated help need is NOT fluent-ready; falls through.
    state = _classify(
        _features(),
        helpneed_score=0.5,
        correct_streak_no_hint=3,
        distinct_recent_representations=2,
    )
    assert state is LearnerState.PRODUCTIVE_STRUGGLE
