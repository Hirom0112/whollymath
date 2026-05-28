"""Tests for the HelpNeed v2 offline derivation from the event stream (Slice PL.4).

These pin the contract that the v2 pipeline:

  - derives per-PROBLEM signals FAITHFULLY from the PL.2 behavioral event vocabulary (attempts
    from submits, revisions from edits/moves, give-up from hint escalation, time-to-first-touch
    and submit latency from payloads), tolerating missing/garbled payload keys;
  - builds a windowed feature vector that RETIRES the two v1 live proxies — ``recent_attempts_mean``
    (no longer the constant 1.0) and ``recent_request_answer_rate`` (no longer the raw hint rate) —
    and adds the two new columns v1 could not express;
  - never lets an episode's own outcome enter its own features (the leakage invariant).

Pure-function tests over plain stand-in event objects — no DB, no LLM, no SymPy, no network
(CLAUDE.md §8.1/§8.2). The repository round-trip for the event-loading query is in
``tests/db/test_events_features_repository.py``.

NOTE (PROJECT.md §9): there is NO trained v2 model to test — we have no real-learner event data
yet. These tests cover the DERIVATION + SCHEMA only, which is exactly PL.4's scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.events_features import (
    FEATURE_NAMES_V2,
    GIVE_UP_HINT_THRESHOLD,
    HelpNeedV2Features,
    ProblemEpisode,
    ProblemSignals,
    build_episodes,
    derive_problem_signals,
    derive_v2_features,
    split_into_problem_episodes,
)
from app.helpneed.features import KC_ORDER, RECENT_WINDOW

KC = KnowledgeComponentId.ADDITION_UNLIKE
KC_OTHER = KnowledgeComponentId.EQUIVALENCE


@dataclass(frozen=True)
class FakeEvent:
    """A minimal stand-in satisfying the ``_EventLike`` protocol — no DB needed for derivation."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


def _presented(kc: KnowledgeComponentId = KC, problem_id: str = "p1") -> FakeEvent:
    return FakeEvent("problem_presented", {"problem_id": problem_id, "kc": kc.value})


# --------------------------------------------------------------------------------------------
# derive_problem_signals: the per-episode primitives
# --------------------------------------------------------------------------------------------


def test_attempts_counted_from_submit_events() -> None:
    """attempts == number of submit events (retires the assumed attempts≡1 — it's a REAL count)."""
    episode = [
        _presented(),
        FakeEvent("submit", {"latency_ms": 3000, "hint_used": False}),
        FakeEvent("submit", {"latency_ms": 5000, "hint_used": False}),
    ]
    signals = derive_problem_signals(episode)
    assert signals.attempts == 2


def test_revisions_counted_from_edits_and_moves() -> None:
    """answer_revisions == answer_edit + numberline_move count (a NEW v1-impossible signal)."""
    episode = [
        _presented(),
        FakeEvent("answer_edit", {"text": "1/"}),
        FakeEvent("answer_edit", {"text": "1/2"}),
        FakeEvent("numberline_move", {"tick": 3}),
        FakeEvent("submit", {"latency_ms": 4000}),
    ]
    signals = derive_problem_signals(episode)
    assert signals.answer_revisions == 3


def test_requested_answer_true_at_give_up_threshold() -> None:
    """requested_answer True once hints reach GIVE_UP_HINT_THRESHOLD (faithful give-up)."""
    episode = [_presented()] + [
        FakeEvent("hint_request", {"elapsed_ms": 1000 * i}) for i in range(GIVE_UP_HINT_THRESHOLD)
    ]
    signals = derive_problem_signals(episode)
    assert signals.hint_requests == GIVE_UP_HINT_THRESHOLD
    assert signals.requested_answer is True


def test_requested_answer_false_below_give_up_threshold() -> None:
    """Below the give-up threshold, requested_answer is False (one/two hints is not a give-up)."""
    episode = [_presented()] + [
        FakeEvent("hint_request", {"elapsed_ms": 1000 * i})
        for i in range(GIVE_UP_HINT_THRESHOLD - 1)
    ]
    signals = derive_problem_signals(episode)
    assert signals.hint_requests == GIVE_UP_HINT_THRESHOLD - 1
    assert signals.requested_answer is False


def test_time_to_first_interaction_read_from_payload() -> None:
    """time_to_first_interaction_ms comes from first_interaction.elapsed_ms."""
    episode = [
        _presented(),
        FakeEvent("first_interaction", {"elapsed_ms": 2500, "kind": "fraction"}),
        FakeEvent("submit", {"latency_ms": 6000}),
    ]
    signals = derive_problem_signals(episode)
    assert signals.time_to_first_interaction_ms == 2500


def test_submit_latency_read_from_last_submit() -> None:
    """submit_latency_ms is the latest submit's latency_ms."""
    episode = [
        _presented(),
        FakeEvent("submit", {"latency_ms": 3000}),
        FakeEvent("submit", {"latency_ms": 8000}),
    ]
    signals = derive_problem_signals(episode)
    assert signals.submit_latency_ms == 8000


def test_idle_events_counted() -> None:
    """idle events on a problem are counted (a disengagement signal)."""
    episode = [
        _presented(),
        FakeEvent("idle", {"after_ms": 30000}),
        FakeEvent("idle", {"after_ms": 30000}),
        FakeEvent("submit", {"latency_ms": 70000}),
    ]
    signals = derive_problem_signals(episode)
    assert signals.idle_events == 2


def test_missing_and_garbled_payload_keys_tolerated() -> None:
    """A missing/garbled payload key yields sane defaults, never a crash (open-JSON safety)."""
    episode = [
        _presented(),
        FakeEvent("first_interaction", {}),  # no elapsed_ms
        FakeEvent("submit", {"latency_ms": "not-a-number"}),  # garbled
        FakeEvent("submit", {}),  # no latency_ms at all
    ]
    signals = derive_problem_signals(episode)
    assert signals.attempts == 2  # both submits still counted
    assert signals.time_to_first_interaction_ms is None  # missing → None, not a crash
    assert signals.submit_latency_ms is None  # garbled then missing → None


def test_garbled_string_int_is_still_parsed() -> None:
    """An integer-ish string payload value is parsed (defensive, not lossy on stringy ints)."""
    episode = [
        _presented(),
        FakeEvent("first_interaction", {"elapsed_ms": "1500"}),
        FakeEvent("submit", {"latency_ms": 4200.0}),  # float
    ]
    signals = derive_problem_signals(episode)
    assert signals.time_to_first_interaction_ms == 1500
    assert signals.submit_latency_ms == 4200


def test_bool_payload_not_treated_as_int() -> None:
    """A bool payload value (e.g. a flag) is not mistaken for an int millisecond count."""
    episode = [_presented(), FakeEvent("first_interaction", {"elapsed_ms": True})]
    signals = derive_problem_signals(episode)
    assert signals.time_to_first_interaction_ms is None


# --------------------------------------------------------------------------------------------
# split_into_problem_episodes: stream segmentation
# --------------------------------------------------------------------------------------------


def test_split_segments_on_problem_presented() -> None:
    """Each problem_presented opens a new episode; following events attach to it."""
    events = [
        _presented(KC, "p1"),
        FakeEvent("submit", {"latency_ms": 1000}),
        _presented(KC_OTHER, "p2"),
        FakeEvent("hint_request", {}),
        FakeEvent("submit", {"latency_ms": 2000}),
    ]
    episodes = split_into_problem_episodes(events)
    assert len(episodes) == 2
    assert [e.event_type for e in episodes[0]] == ["problem_presented", "submit"]
    assert [e.event_type for e in episodes[1]] == ["problem_presented", "hint_request", "submit"]


def test_split_drops_events_before_first_problem() -> None:
    """Ambient events before any problem mounted belong to no episode and are dropped."""
    events = [
        FakeEvent("focus"),
        FakeEvent("idle", {"after_ms": 30000}),
        _presented(KC, "p1"),
        FakeEvent("submit", {"latency_ms": 1000}),
    ]
    episodes = split_into_problem_episodes(events)
    assert len(episodes) == 1
    assert [e.event_type for e in episodes[0]] == ["problem_presented", "submit"]


# --------------------------------------------------------------------------------------------
# build_episodes: signals + KC resolution
# --------------------------------------------------------------------------------------------


def test_build_episodes_resolves_kc_and_signals() -> None:
    """build_episodes attaches the KC from the payload and derives each episode's signals."""
    events = [
        _presented(KC, "p1"),
        FakeEvent("submit", {"latency_ms": 1000}),
        _presented(KC_OTHER, "p2"),
        FakeEvent("hint_request", {}),
        FakeEvent("submit", {"latency_ms": 2000}),
    ]
    episodes = build_episodes(events)
    assert [e.kc for e in episodes] == [KC, KC_OTHER]
    assert episodes[0].signals.attempts == 1
    assert episodes[1].signals.hint_requests == 1


def test_build_episodes_drops_episode_with_unresolvable_kc() -> None:
    """An episode whose problem_presented lacks a valid kc is dropped (no one-hot to set)."""
    events = [
        FakeEvent("problem_presented", {"problem_id": "p1"}),  # no kc
        FakeEvent("submit", {"latency_ms": 1000}),
        _presented(KC, "p2"),
        FakeEvent("submit", {"latency_ms": 2000}),
    ]
    episodes = build_episodes(events)
    assert [e.kc for e in episodes] == [KC]


def test_build_episodes_drops_episode_with_garbage_kc() -> None:
    """A non-catalog kc string is rejected (not coerced), so the episode is dropped."""
    events = [
        FakeEvent("problem_presented", {"problem_id": "p1", "kc": "KC_not_real"}),
        FakeEvent("submit", {"latency_ms": 1000}),
    ]
    assert build_episodes(events) == []


# --------------------------------------------------------------------------------------------
# derive_v2_features: the windowed vector that RETIRES the proxies
# --------------------------------------------------------------------------------------------


def _episode(
    *,
    kc: KnowledgeComponentId = KC,
    attempts: int = 1,
    hint_requests: int = 0,
    answer_revisions: int = 0,
    ttfi: int | None = 2000,
    submit_latency_ms: int | None = 4000,
    idle_events: int = 0,
) -> ProblemEpisode:
    return ProblemEpisode(
        kc=kc,
        signals=ProblemSignals(
            attempts=attempts,
            hint_requests=hint_requests,
            requested_answer=hint_requests >= GIVE_UP_HINT_THRESHOLD,
            answer_revisions=answer_revisions,
            time_to_first_interaction_ms=ttfi,
            idle_events=idle_events,
            submit_latency_ms=submit_latency_ms,
        ),
    )


def test_empty_episodes_yields_no_rows() -> None:
    """No episodes ⇒ no feature rows."""
    assert derive_v2_features([]) == []


def test_first_episode_is_all_neutral_cold_start() -> None:
    """The first episode has no prior history ⇒ all-neutral window features (cold start)."""
    rows = derive_v2_features([_episode(attempts=3, hint_requests=4)])
    assert len(rows) == 1
    row = rows[0]
    assert row.recent_attempts_mean == 0.0
    assert row.recent_request_answer_rate == 0.0
    assert row.recent_revisions_mean == 0.0
    assert row.recent_time_to_first_interaction_ms_mean == 0.0
    assert row.session_position == 0.0
    assert row.kc is KC
    # full model width
    assert len(row.to_vector()) == len(FEATURE_NAMES_V2)


def test_attempts_mean_reflects_real_multi_submit_not_the_proxy_constant() -> None:
    """RETIRES the attempts≡1.0 proxy: with multiple real submits the mean is NOT 1.0."""
    episodes = [
        _episode(attempts=2),
        _episode(attempts=4),
        _episode(attempts=3),  # current; its own attempts must not enter its row
    ]
    rows = derive_v2_features(episodes)
    # the last row's window is the two PRIOR episodes (attempts 2 and 4) → mean 3.0, not 1.0
    assert rows[2].recent_attempts_mean == 3.0
    assert rows[2].recent_attempts_mean != 1.0


def test_request_answer_rate_reflects_real_give_ups_not_the_hint_rate() -> None:
    """RETIRES the hint-rate proxy: request_answer_rate tracks real give-ups, not raw hint rate."""
    # Two prior episodes: one a real give-up (>= threshold hints), one with a single non-give-up
    # hint. The hint RATE over the window is 2/2 (both had >=1 hint), but the give-up RATE is 1/2.
    episodes = [
        _episode(hint_requests=GIVE_UP_HINT_THRESHOLD),  # a give-up
        _episode(hint_requests=1),  # one hint, NOT a give-up
        _episode(),  # current
    ]
    rows = derive_v2_features(episodes)
    current = rows[2]
    assert current.recent_hint_rate == 1.0  # both prior episodes had a hint
    assert current.recent_request_answer_rate == 0.5  # only one was a give-up
    # the whole point: the two columns now DIFFER (in v1's live proxy they were identical)
    assert current.recent_request_answer_rate != current.recent_hint_rate


def test_new_columns_revisions_and_time_to_first_interaction() -> None:
    """The two NEW columns aggregate the v1-impossible signals over the window."""
    episodes = [
        _episode(answer_revisions=2, ttfi=1000),
        _episode(answer_revisions=4, ttfi=3000),
        _episode(),  # current
    ]
    rows = derive_v2_features(episodes)
    current = rows[2]
    assert current.recent_revisions_mean == 3.0  # (2 + 4) / 2
    assert current.recent_time_to_first_interaction_ms_mean == 2000.0  # (1000 + 3000) / 2


def test_time_to_first_interaction_mean_ignores_missing_reports() -> None:
    """Episodes that reported no first-touch are excluded from the mean (not counted as zero)."""
    episodes = [
        _episode(ttfi=2000),
        _episode(ttfi=None),  # never touched / not reported
        _episode(),  # current
    ]
    rows = derive_v2_features(episodes)
    # only the one reporting episode contributes → mean 2000, not 1000
    assert rows[2].recent_time_to_first_interaction_ms_mean == 2000.0


def test_window_bounds_recent_features() -> None:
    """recent_* use the last RECENT_WINDOW prior episodes; unproductive rate uses all prior."""
    # RECENT_WINDOW give-up episodes, then one clean, then the current.
    episodes = (
        [_episode(hint_requests=GIVE_UP_HINT_THRESHOLD) for _ in range(RECENT_WINDOW)]
        + [_episode(hint_requests=0)]
        + [_episode()]
    )
    rows = derive_v2_features(episodes)
    current = rows[-1]
    # window = last RECENT_WINDOW prior episodes: trailing clean one + (RECENT_WINDOW-1) give-ups
    assert current.recent_request_answer_rate == (RECENT_WINDOW - 1) / RECENT_WINDOW
    # prior = ALL prior episodes: RECENT_WINDOW give-ups out of RECENT_WINDOW+1
    assert current.prior_unproductive_rate == RECENT_WINDOW / (RECENT_WINDOW + 1)
    assert current.session_position == float(RECENT_WINDOW + 1)


def test_leakage_guard_current_outcome_never_enters_its_own_row() -> None:
    """The current episode's OWN signals must not change its feature row (leakage invariant).

    Build identical histories that differ ONLY in the CURRENT (last) episode's signals; the last
    row's features must be byte-identical, because a row is computed from PRIOR episodes only.
    """
    prior = [_episode(attempts=1, hint_requests=0, answer_revisions=1)]
    benign_current = _episode(attempts=1, hint_requests=0, answer_revisions=0)
    extreme_current = _episode(
        attempts=9, hint_requests=GIVE_UP_HINT_THRESHOLD + 2, answer_revisions=20
    )
    row_benign = derive_v2_features([*prior, benign_current])[-1]
    row_extreme = derive_v2_features([*prior, extreme_current])[-1]
    assert row_benign == row_extreme


def test_to_vector_one_hot_matches_kc_order() -> None:
    """to_vector appends the KC one-hot in KC_ORDER, with exactly the current KC set."""
    row = derive_v2_features([_episode(kc=KC_OTHER)])[0]
    vector = row.to_vector()
    numeric_width = len(FEATURE_NAMES_V2) - len(KC_ORDER)
    one_hot = vector[numeric_width:]
    expected = tuple(1.0 if kc is KC_OTHER else 0.0 for kc in KC_ORDER)
    assert one_hot == expected
    assert sum(one_hot) == 1.0


def test_feature_names_v2_align_with_vector_width() -> None:
    """FEATURE_NAMES_V2 labels every column the vector produces (SHAP-by-index integrity)."""
    row = derive_v2_features([_episode()])[0]
    assert len(row.to_vector()) == len(FEATURE_NAMES_V2)


def test_v2_features_is_a_dataclass_instance() -> None:
    """derive_v2_features yields HelpNeedV2Features rows (the v2 schema, not v1's)."""
    rows = derive_v2_features([_episode()])
    assert isinstance(rows[0], HelpNeedV2Features)
