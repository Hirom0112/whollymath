"""When to offer help WHILE a learner is mid-problem (Slice HR live-loop, Beat 1).

The §3.8 refuse layer forbids reorganizing the workspace mid-problem, but it explicitly ALLOWS an
additive, non-destructive hint that preserves the learner's work. This module is that decision: a
pure rule over the live behavioral window (HR.B1) that says "this child is stuck RIGHT NOW — offer
a gentle nudge", without them asking and without waiting for a submit.

It fires only on a SUSTAINED struggle signal (a long freeze, accumulated idle, or many edits going
nowhere), never on a single twitch — and only BEFORE a submit (once they answer, the turn loop
takes over). Thresholds are named, tunable constants. The nudge text itself comes from the
pre-written bank (no LLM decides to help); the mascot only voices an already-decided nudge.
"""

from __future__ import annotations

from app.helpneed.live_signal_features import LiveSignalFeatures

# Idle pings on the current problem that read as "paused / stuck" (not a single momentary pause).
_MID_IDLE_EVENTS = 2
# Edits/manipulations on the current problem with no submit — spinning without converging.
_MID_REVISIONS = 4
# This long (ms) before the FIRST interaction reads as frozen / not knowing where to start.
_MID_TTFI_MS = 20_000


def should_offer_mid_problem_help(features: LiveSignalFeatures) -> bool:
    """Whether to proactively offer an additive nudge on the in-progress problem (Beat 1).

    True only when the learner is still ON the problem (no submit yet) and has NOT already asked
    for a hint, AND a sustained struggle signal is present: accumulated idle, many edits going
    nowhere, or a long freeze before the first interaction. Additive only — the caller renders a
    nudge, never a workspace change (refuse-rule 1).
    """
    if features.current_attempts > 0:
        return False  # they've submitted — the turn loop owns the response now.
    if features.current_hint_requests > 0:
        return False  # they already asked for help; don't pile on.

    ttfi = features.time_to_first_interaction_ms
    return (
        features.current_idle_events >= _MID_IDLE_EVENTS
        or features.current_revisions >= _MID_REVISIONS
        or (ttfi is not None and ttfi >= _MID_TTFI_MS)
    )


__all__ = ["should_offer_mid_problem_help"]
