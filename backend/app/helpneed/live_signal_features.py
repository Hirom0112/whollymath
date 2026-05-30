"""Live, in-session behavioral features for the hyperreactive state classifier (Slice HR.B1).

The §2.1 live loop needs a windowed read of HOW the learner is working RIGHT NOW — not the offline
training features (events_features.py / PL.4), but a small summary the deterministic 6-state
classifier (HR.B2) consumes alongside the HelpNeed score. This module computes that summary from
the per-problem ``ProblemSignals`` the event pipeline already derives, so there is ONE source of
truth for "what the behavioral stream says" (we reuse ``build_episodes`` /
``derive_problem_signals`` rather than re-parsing payloads).

OFF the sub-100ms turn path (CLAUDE.md §8.1): this is observe-then-act telemetry feeding the live
adaptation, computed after the deterministic response, never inside it. Pure: episodes in, a frozen
feature row out — no DB, no clock, no LLM.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.helpneed.events_features import ProblemEpisode

# How many most-recent problems the windowed means summarize. A small window keeps the live read
# responsive to a learner's CURRENT mode rather than their whole session (HYPERREACTIVE §2.1).
_RECENT_WINDOW = 5


@dataclass(frozen=True)
class LiveSignalFeatures:
    """A windowed snapshot of how the learner is working in-session (HR.B1 → HR.B2 input).

    Splits into the CURRENT problem (the live signal the classifier reacts to) and WINDOWED means
    over the recent problems (the trend that disambiguates, e.g., a slow first touch on ONE problem
    vs. a pattern of disengagement). All counts are behavioral — no correctness, no KC — so the
    classifier reasons over conduct, not outcome."""

    # The current (most-recent) problem.
    time_to_first_interaction_ms: int | None
    current_attempts: int
    current_revisions: int
    current_idle_events: int
    current_hint_requests: int
    current_requested_answer: bool
    # Windowed means/rates over the recent problems (current included).
    recent_attempts_mean: float
    recent_revisions_mean: float
    recent_idle_mean: float
    recent_hint_rate: float
    recent_give_up_rate: float
    # How many problems this session has seen (0 ⇒ a brand-new learner, all fields are defaults).
    problems_seen: int


def _empty() -> LiveSignalFeatures:
    """The neutral features for a learner with no problems yet (nothing to react to)."""
    return LiveSignalFeatures(
        time_to_first_interaction_ms=None,
        current_attempts=0,
        current_revisions=0,
        current_idle_events=0,
        current_hint_requests=0,
        current_requested_answer=False,
        recent_attempts_mean=0.0,
        recent_revisions_mean=0.0,
        recent_idle_mean=0.0,
        recent_hint_rate=0.0,
        recent_give_up_rate=0.0,
        problems_seen=0,
    )


def compute_live_features(
    episodes: Sequence[ProblemEpisode],
    *,
    window: int = _RECENT_WINDOW,
) -> LiveSignalFeatures:
    """Summarize a session's recent behavior into ``LiveSignalFeatures`` (HR.B1).

    ``episodes`` are this session's problems in order (build them once with
    ``events_features.build_episodes``); the LAST is the current, possibly in-progress, problem.
    Windowed means cover the most-recent ``window`` problems. Returns neutral defaults for an empty
    session so the classifier always has a value to read.
    """
    if not episodes:
        return _empty()

    current = episodes[-1].signals
    recent = [ep.signals for ep in episodes[-window:]]
    n = len(recent)

    return LiveSignalFeatures(
        time_to_first_interaction_ms=current.time_to_first_interaction_ms,
        current_attempts=current.attempts,
        current_revisions=current.answer_revisions,
        current_idle_events=current.idle_events,
        current_hint_requests=current.hint_requests,
        current_requested_answer=current.requested_answer,
        recent_attempts_mean=sum(s.attempts for s in recent) / n,
        recent_revisions_mean=sum(s.answer_revisions for s in recent) / n,
        recent_idle_mean=sum(s.idle_events for s in recent) / n,
        recent_hint_rate=sum(1 for s in recent if s.hint_requests > 0) / n,
        recent_give_up_rate=sum(1 for s in recent if s.requested_answer) / n,
        problems_seen=len(episodes),
    )


__all__ = ["LiveSignalFeatures", "compute_live_features"]
