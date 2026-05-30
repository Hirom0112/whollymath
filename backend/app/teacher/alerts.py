"""Alert engine: named, tunable rules over a student's behavioral evidence (Slice TCH.B5).

Pure and NO LLM (CLAUDE.md §8.1): each rule reads the ``TurnFact`` stream (and the clock for
idle) and either fires a ``TeacherAlertView`` with a plain-language, templated message or stays
silent. The engine runs every rule, de-conflicts the two stuck variants, and returns the alerts
most-severe-first so the dashboard banner leads with what matters.

The thresholds are deliberately named module constants, not magic numbers, so they are tunable in
one place and visible to the decision log (CLAUDE.md §8.4). They are taste-level defaults, not
PRD-locked. The six rules mirror the kinds lane T2 built its alert visual system around:

  STUCK                  — a trailing run of all-wrong answers (urgent).
  REPEATED_MISCONCEPTION — the same error category dominating recent misses (urgent).
  FAILING_TREND          — accuracy sliding across the recent window (warn).
  LOW_ENGAGEMENT         — barely any attempts yet (warn).
  IDLE                   — no activity for a while (info).
  REMEDIATION_STUCK      — stuck WHILE dropped to a prerequisite (urgent). Wired but DORMANT:
                           remediation routing is not built yet, so the coordinator passes
                           ``in_remediation=False`` and this never fires in production until that
                           signal exists (CURRICULUM_STANDARD.md §11). Tested directly.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timedelta

from app.api.schemas import AlertKind, AlertSeverity, TeacherAlertView
from app.teacher.evidence import TurnFact

# How many trailing answers count as "recent" for the dominant-error and trend rules.
_RECENT_N = 8
# A trailing run of this many all-wrong answers fires STUCK.
_STUCK_RUN = 3
# The dominant recent error category must appear at least this many times to fire the repeat rule.
_REPEAT_MIN = 3
# Need at least this many recent answers before judging a trend (else it's noise).
_TREND_MIN = 6
# Accuracy must fall by at least this much (earlier half → later half) AND the later half must be
# below ``_TREND_LATE_MAX`` to fire FAILING_TREND.
_TREND_DROP = 0.25
_TREND_LATE_MAX = 0.6
# At most this many total attempts reads as barely-engaged.
_LOW_ENGAGEMENT_MAX = 2
# Hint-dependency (Finding #2): need at least this many CORRECT answers before judging whether the
# learner can solve unscaffolded — fewer is too thin to call a pattern.
_HINT_DEP_MIN_CORRECT = 4
# …and if at most this fraction of those corrects were unscaffolded (no hint), the learner is
# leaning on scaffolds (Hint-hunter Hugo: ~0 unscaffolded; PROJECT.md §4.2 P3).
_HINT_DEP_MAX_UNSCAFFOLDED_RATE = 0.15
# No activity for at least this long fires IDLE.
_IDLE_AFTER = timedelta(days=3)

# Plain-language names for the verifier's coarse error categories (Turn.error_type values).
_ERROR_LABELS = {
    "magnitude": "size / magnitude",
    "operation": "operation",
    "format": "formatting",
    "other": "",
}

# Output ordering: most severe first, then a stable kind order within a severity.
_SEVERITY_RANK = {AlertSeverity.URGENT: 0, AlertSeverity.WARN: 1, AlertSeverity.INFO: 2}


def _accuracy(turns: Sequence[TurnFact]) -> float:
    return sum(1 for t in turns if t.correct) / len(turns) if turns else 0.0


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _is_stuck(turns: Sequence[TurnFact]) -> bool:
    tail = turns[-_STUCK_RUN:]
    return len(tail) >= _STUCK_RUN and all(not t.correct for t in tail)


def _repeated_misconception(turns: Sequence[TurnFact]) -> TeacherAlertView | None:
    recent = turns[-_RECENT_N:]
    wrong = [t.error_category for t in recent if not t.correct and t.error_category]
    if not wrong:
        return None
    category, count = Counter(wrong).most_common(1)[0]
    if count < _REPEAT_MIN:
        return None
    label = _ERROR_LABELS.get(category, "")
    descriptor = f"{label} error" if label else "mistake"
    return TeacherAlertView(
        kind=AlertKind.REPEATED_MISCONCEPTION,
        severity=AlertSeverity.URGENT,
        message=f"The same {descriptor} on {count} of the last {len(recent)} attempts.",
    )


def _failing_trend(turns: Sequence[TurnFact]) -> TeacherAlertView | None:
    recent = turns[-_RECENT_N:]
    if len(recent) < _TREND_MIN:
        return None
    half = len(recent) // 2
    earlier, later = _accuracy(recent[:half]), _accuracy(recent[half:])
    if earlier - later >= _TREND_DROP and later < _TREND_LATE_MAX:
        return TeacherAlertView(
            kind=AlertKind.FAILING_TREND,
            severity=AlertSeverity.WARN,
            message=f"Accuracy fell from {_pct(earlier)} to {_pct(later)} over recent work.",
        )
    return None


def _hint_dependent(turns: Sequence[TurnFact]) -> TeacherAlertView | None:
    """Correct answers that almost always used a hint — the hint-hunter signature (Finding #2).

    A learner can look fine on the other rules (not wrong, not stuck, not idle) while never solving
    unscaffolded: every correct answer leaned on a hint. That is real but fragile, so it should
    surface as needs_attention (WARN). Computed over CORRECT turns only — wrong answers say nothing
    about scaffold-dependence — and gated on a minimum count so one hinted correct is not a pattern.
    """
    corrects = [t for t in turns if t.correct]
    if len(corrects) < _HINT_DEP_MIN_CORRECT:
        return None
    unscaffolded_rate = sum(1 for t in corrects if not t.hint_used) / len(corrects)
    if unscaffolded_rate > _HINT_DEP_MAX_UNSCAFFOLDED_RATE:
        return None
    return TeacherAlertView(
        kind=AlertKind.HINT_DEPENDENT,
        severity=AlertSeverity.WARN,
        message=(
            f"Gets answers right but only {_pct(unscaffolded_rate)} were unscaffolded; "
            "leaning on hints rather than solving independently."
        ),
    )


def _low_engagement(turns: Sequence[TurnFact]) -> TeacherAlertView | None:
    if 0 < len(turns) <= _LOW_ENGAGEMENT_MAX:
        return TeacherAlertView(
            kind=AlertKind.LOW_ENGAGEMENT,
            severity=AlertSeverity.WARN,
            message=f"Only {len(turns)} problem{'s' if len(turns) != 1 else ''} attempted so far.",
        )
    return None


def _idle(turns: Sequence[TurnFact], now: datetime) -> TeacherAlertView | None:
    if not turns:
        return None
    gap = now - turns[-1].created_at
    if gap >= _IDLE_AFTER:
        return TeacherAlertView(
            kind=AlertKind.IDLE,
            severity=AlertSeverity.INFO,
            message=f"No activity for {gap.days} day{'s' if gap.days != 1 else ''}.",
        )
    return None


def evaluate_alerts(
    turns: Sequence[TurnFact],
    now: datetime,
    *,
    in_remediation: bool = False,
) -> list[TeacherAlertView]:
    """Run every alert rule over a student's evidence; return them most-severe-first.

    ``turns`` is the student's whole answer history in chronological order. ``in_remediation`` is
    DORMANT today (remediation routing is unbuilt) — when it is eventually wired and the student
    is both in remediation and stuck, REMEDIATION_STUCK fires INSTEAD of the generic STUCK (the
    more specific signal). Returns ``[]`` for a student with no telling signal.
    """
    alerts: list[TeacherAlertView] = []

    if _is_stuck(turns):
        if in_remediation:
            alerts.append(
                TeacherAlertView(
                    kind=AlertKind.REMEDIATION_STUCK,
                    severity=AlertSeverity.URGENT,
                    message=f"Stuck on prerequisite review: missed the last {_STUCK_RUN} in a row.",
                )
            )
        else:
            alerts.append(
                TeacherAlertView(
                    kind=AlertKind.STUCK,
                    severity=AlertSeverity.URGENT,
                    message=f"Missed the last {_STUCK_RUN} problems in a row.",
                )
            )

    for rule in (_repeated_misconception, _failing_trend, _low_engagement, _hint_dependent):
        alert = rule(turns)
        if alert is not None:
            alerts.append(alert)

    idle = _idle(turns, now)
    if idle is not None:
        alerts.append(idle)

    alerts.sort(key=lambda a: _SEVERITY_RANK[a.severity])
    return alerts


__all__ = ["evaluate_alerts"]
