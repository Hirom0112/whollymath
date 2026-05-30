"""Ranking: bucket a student into on_track / needs_attention / struggling (Slice TCH.B6).

Pure rule, NO weighted-sum black box: the bucket is a transparent function of the alerts already
computed (B5) plus the weakness count (B3), so the one-line reason a teacher reads is exactly the
signal that drove the bucket. The locked rule (TODO TCH.B6) — ANY urgent alert forces
``struggling`` — is the spine; the rest is the obvious ladder beneath it:

  - any URGENT alert            → struggling (reason = that alert).
  - else any WARN alert         → needs_attention (reason = that alert).
  - else any weak skill         → needs_attention (reason = the gap count).
  - else                        → on_track.

The exact thresholds beneath "urgent → struggling" are taste-level and tunable (TCH.Q3 is still
open); they live here, in one place, for the decision log (CLAUDE.md §8.4).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.api.schemas import (
    AlertSeverity,
    KcMasteryView,
    StudentCategory,
    TeacherAlertView,
)


def classify_student(
    alerts: Sequence[TeacherAlertView],
    weaknesses: Sequence[KcMasteryView],
) -> tuple[StudentCategory, str]:
    """Return the student's ``(category, one-line reason)`` from their alerts + weaknesses.

    ``alerts`` is the B5 output (any order); ``weaknesses`` the B3 weakest-first list. The reason
    is the human-readable driver of the bucket, surfaced verbatim on the roster row.
    """
    urgent = [a for a in alerts if a.severity is AlertSeverity.URGENT]
    if urgent:
        return StudentCategory.STRUGGLING, urgent[0].message

    warn = [a for a in alerts if a.severity is AlertSeverity.WARN]
    if warn:
        return StudentCategory.NEEDS_ATTENTION, warn[0].message

    if weaknesses:
        n = len(weaknesses)
        return (
            StudentCategory.NEEDS_ATTENTION,
            f"{n} skill{'s' if n != 1 else ''} below target, but no urgent flags.",
        )

    return StudentCategory.ON_TRACK, "Keeping pace — no alerts."


__all__ = ["classify_student"]
