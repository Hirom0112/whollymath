"""Deterministic in-session learner-state classifier (Slice HR.B2 — the live loop's brain).

A PURE function over the live signal window (HR.B1) + the HelpNeed score → one of six learner
states (HYPERREACTIVE.md §2.1). Deterministic, NOT an LLM — for latency and defensibility (the
graded turn loop stays sub-100ms; this runs observe-then-act, off the critical path). Thresholds
are NAMED, tunable module constants (like the SustainedHelpNeedGate constants), expected to be
calibrated against real data — a first, defensible cut, not PRD-locked.

The classifier only NAMES the state. It does NOT decide the adaptation or fire it — HR.B3 maps a
state → a labeled transition, gated on a SUSTAINED signal (a single noisy reading must not yank the
UI, RESEARCH §7.5) and the refuse layer (never mid-problem except an additive hint, never on a
pause). Keeping naming pure and separate is what makes both halves testable.

Inputs beyond the behavioral window: the HelpNeed score (the XGBoost P(unproductive), which
generalizes past fractions) plus two cheap session facts the behavioral stream cannot carry —
the unassisted correct streak and how many DISTINCT representations the recent correct work spans.
Those distinguish fluent-ready (fast-correct, ≥2 reps) from pattern-matching (fast-correct but
stuck in one drilled representation).
"""

from __future__ import annotations

from enum import StrEnum

from app.helpneed.live_signal_features import LiveSignalFeatures

# ── Named, tunable thresholds (first cut; calibrate against real sessions) ──
# Idle/avoiding: this many idle pings on the current problem, or no first interaction at all while
# the problem has been sitting, reads as disengagement.
_IDLE_EVENTS = 2
# Guessing: a first interaction this fast (ms) is "barely looked", and with repeated submits and
# almost no answer revision it is rapid trial-and-error, not reasoning.
_GUESS_TTFI_MS = 1500
_GUESS_ATTEMPTS = 2
_GUESS_REVISIONS_MAX = 1
# Confused: the HelpNeed score at/above this, with real engagement, is genuine struggle (not idle).
_CONFUSED_HELPNEED = 0.65
# Fluent-ready: an unassisted correct streak this long across ≥2 representations, with low help
# need, is ready to fade/advance.
_FLUENT_STREAK = 3
_FLUENT_HELPNEED = 0.30
_MIN_REPRESENTATIONS_FLUENT = 2
# Pattern-matching: a correct streak this long but confined to a single drilled representation.
_PATTERN_STREAK = 3


class LearnerState(StrEnum):
    """The six in-session states the live loop reacts to (HYPERREACTIVE.md §2.1)."""

    CONFUSED = "confused"
    PRODUCTIVE_STRUGGLE = "productive_struggle"
    GUESSING = "guessing"
    PATTERN_MATCHING = "pattern_matching"
    IDLE_AVOIDING = "idle_avoiding"
    FLUENT_READY = "fluent_ready"


def _is_idle(features: LiveSignalFeatures) -> bool:
    if features.current_idle_events >= _IDLE_EVENTS:
        return True
    # A presented problem the learner has not touched at all (no first interaction) while idle pings
    # accumulate is avoidance, not thinking.
    return features.time_to_first_interaction_ms is None and features.current_idle_events >= 1


def _is_guessing(features: LiveSignalFeatures) -> bool:
    ttfi = features.time_to_first_interaction_ms
    return (
        ttfi is not None
        and ttfi <= _GUESS_TTFI_MS
        and features.current_attempts >= _GUESS_ATTEMPTS
        and features.current_revisions <= _GUESS_REVISIONS_MAX
    )


def classify_state(
    features: LiveSignalFeatures,
    *,
    helpneed_score: float,
    correct_streak_no_hint: int,
    distinct_recent_representations: int,
) -> LearnerState:
    """Classify the learner's current in-session state (HR.B2).

    Priority-ordered (first match wins), most-specific/most-urgent first. ``helpneed_score`` is the
    predictor's P(unproductive) in [0, 1]; ``correct_streak_no_hint`` and
    ``distinct_recent_representations`` are session facts (consecutive unassisted-correct answers
    and how many representations that recent correct work spanned). The default — an engaged learner
    matching no sharper signal — is PRODUCTIVE_STRUGGLE, the state the refuse layer PROTECTS.
    """
    # 1. Idle / avoiding: a pause is never struggle; it yields a nudge, not a morph (refuse-rule 3).
    if _is_idle(features):
        return LearnerState.IDLE_AVOIDING

    # 2. Guessing — fast, repeated, shallow submits: slow it down before it becomes a habit.
    if _is_guessing(features):
        return LearnerState.GUESSING

    # 3/4. A confident correct streak: fluent across representations vs. stuck in the drilled one.
    if correct_streak_no_hint >= _FLUENT_STREAK and helpneed_score <= _FLUENT_HELPNEED:
        if distinct_recent_representations >= _MIN_REPRESENTATIONS_FLUENT:
            return LearnerState.FLUENT_READY
    if (
        correct_streak_no_hint >= _PATTERN_STREAK
        and distinct_recent_representations < _MIN_REPRESENTATIONS_FLUENT
    ):
        return LearnerState.PATTERN_MATCHING

    # 5. Confused — high help need with real engagement (idle already excluded above).
    if helpneed_score >= _CONFUSED_HELPNEED:
        return LearnerState.CONFUSED

    # 6. Default: engaged, neither stuck nor cruising — protect the productive struggle.
    return LearnerState.PRODUCTIVE_STRUGGLE


__all__ = ["LearnerState", "classify_state"]
