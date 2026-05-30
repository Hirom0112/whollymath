"""Unit tests for the live in-session signal features (Slice HR.B1).

Pure over pre-built episodes: pins the current-problem read, the windowed means/rates, the window
bound, and the empty-session default.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.events_features import ProblemEpisode, ProblemSignals
from app.helpneed.live_signal_features import compute_live_features

_KC = KnowledgeComponentId.ADDITION_UNLIKE


def _signals(
    *,
    attempts: int = 1,
    hint_requests: int = 0,
    requested_answer: bool = False,
    answer_revisions: int = 0,
    ttfi_ms: int | None = 1000,
    idle_events: int = 0,
    latency_ms: int | None = 2000,
) -> ProblemSignals:
    return ProblemSignals(
        attempts=attempts,
        hint_requests=hint_requests,
        requested_answer=requested_answer,
        answer_revisions=answer_revisions,
        time_to_first_interaction_ms=ttfi_ms,
        idle_events=idle_events,
        submit_latency_ms=latency_ms,
    )


def _ep(signals: ProblemSignals) -> ProblemEpisode:
    return ProblemEpisode(kc=_KC, signals=signals)


def test_empty_session_is_neutral_default() -> None:
    feats = compute_live_features([])
    assert feats.problems_seen == 0
    assert feats.time_to_first_interaction_ms is None
    assert feats.current_attempts == 0
    assert feats.recent_attempts_mean == 0.0
    assert feats.recent_hint_rate == 0.0


def test_current_problem_is_the_last_episode() -> None:
    feats = compute_live_features(
        [
            _ep(_signals(attempts=1)),
            _ep(
                _signals(
                    attempts=4, answer_revisions=3, idle_events=2, ttfi_ms=8000, hint_requests=1
                )
            ),
        ]
    )
    assert feats.problems_seen == 2
    assert feats.current_attempts == 4
    assert feats.current_revisions == 3
    assert feats.current_idle_events == 2
    assert feats.current_hint_requests == 1
    assert feats.time_to_first_interaction_ms == 8000


def test_windowed_means_and_rates() -> None:
    episodes = [
        _ep(_signals(attempts=2, hint_requests=1, answer_revisions=0, idle_events=0)),
        _ep(_signals(attempts=4, hint_requests=0, answer_revisions=2, idle_events=1)),
        _ep(
            _signals(
                attempts=0,
                hint_requests=0,
                answer_revisions=4,
                idle_events=3,
                requested_answer=True,
            )
        ),
    ]
    feats = compute_live_features(episodes)
    assert feats.recent_attempts_mean == (2 + 4 + 0) / 3
    assert feats.recent_revisions_mean == (0 + 2 + 4) / 3
    assert feats.recent_idle_mean == (0 + 1 + 3) / 3
    assert feats.recent_hint_rate == 1 / 3  # one of three problems had a hint
    assert feats.recent_give_up_rate == 1 / 3  # one of three requested the answer


def test_window_bounds_the_recent_means() -> None:
    # 7 episodes, window of 3 → means cover only the last 3 (all attempts=10), not the early ones.
    episodes = [_ep(_signals(attempts=0)) for _ in range(4)] + [
        _ep(_signals(attempts=10)) for _ in range(3)
    ]
    feats = compute_live_features(episodes, window=3)
    assert feats.recent_attempts_mean == 10.0
    assert feats.problems_seen == 7  # problems_seen is the whole session, not the window
