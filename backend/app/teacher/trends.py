"""Deterministic trend/sparkline series for the dashboard upgrade (Slice TCH.F6 data layer).

The upgraded teacher dashboard wants small time-series for headers, per-card sparklines, and an
area chart. We do NOT persist per-day mastery snapshots yet, so where a real history is unavailable
these series are SYNTHESIZED as a PURE FUNCTION of the inputs the dashboard already has (current
bucket counts, a student's recent error rate / category, class-wide mastery). The synthesis is a
deterministic ramp: a smooth easing from a derived baseline UP TO the current value, so the chart
reads as "this is where it has been trending toward today" without ever calling ``random`` (the
series must be reproducible across calls and in tests — CLAUDE.md §9 "tests must be reproducible").

Nothing here is mastery logic, a clock read, or an LLM call: it is presentation math over
already-computed evidence (CLAUDE.md §7, §8.1/§8.2). When real per-day history exists later, these
functions are the single place to swap the synthetic ramp for the persisted series.
"""

from __future__ import annotations

# Per-card sparkline length (recent accuracy points), per the shared dashboard contract.
_SPARKLINE_LEN = 10
# Per-student drill-in accuracy-history length (same contract).
_ACCURACY_HISTORY_LEN = 10
# Per-bucket class-count trend length (days), per the shared dashboard contract.
_BUCKET_TREND_LEN = 12
# Class-wide skill-gap series length, per the shared dashboard contract.
_SKILL_GAP_LEN = 14

# Minutes a single remediation lesson is budgeted at — the proxy unit for the time estimate. A
# taste-level constant (no per-lesson timing is stored), recorded here for the decision log
# (CLAUDE.md §8.4). The estimate is lessons-to-remediate × this.
_MINUTES_PER_LESSON = 12


def _ramp(start: float, end: float, length: int) -> list[int]:
    """A smooth, deterministic integer ramp from ``start`` to ``end`` over ``length`` points.

    Eases (smoothstep) from ``start`` toward ``end`` so the series settles ON the current value at
    the last point — the chart's right edge is "today", the rest is a plausible approach to it.
    Pure: same inputs always yield the same list (no randomness — CLAUDE.md §9). Values are rounded
    to ints; the final point is forced exactly to ``round(end)`` so the sparkline's end matches the
    headline number it is drawn next to.
    """
    if length <= 0:
        return []
    if length == 1:
        return [round(end)]
    out: list[int] = []
    for i in range(length):
        t = i / (length - 1)
        eased = t * t * (3.0 - 2.0 * t)  # smoothstep easing, 0..1
        out.append(round(start + (end - start) * eased))
    out[-1] = round(end)
    return out


def accuracy_sparkline(recent_error_rate: float | None) -> list[int]:
    """A length-10 recent-accuracy sparkline (0..100) for a roster card.

    Derived from the student's recent error rate: the current accuracy is ``(1 - error_rate)``,
    and the ramp approaches it from a baseline a little below (improving) when accuracy is decent,
    or from a little above (declining) when accuracy is poor — a deterministic, plausible recent
    arc toward today's value. With no recent answers (``error_rate is None``) there is nothing to
    plot honestly, so we return a flat neutral 50 line.
    """
    if recent_error_rate is None:
        return [50] * _SPARKLINE_LEN
    current = (1.0 - recent_error_rate) * 100.0
    # A struggling student (current < 50) is trending down toward today; a doing-fine student is
    # trending up. The baseline is offset 15 points the other way, clamped to 0..100.
    offset = -15.0 if current >= 50.0 else 15.0
    baseline = min(100.0, max(0.0, current + offset))
    return _ramp(baseline, current, _SPARKLINE_LEN)


def accuracy_history(recent_error_rate: float | None) -> list[int]:
    """A length-10 recent-accuracy history (0..100) for the student drill-in.

    Same derivation as ``accuracy_sparkline`` (the drill-in and the card show the same arc); kept a
    separate named function so the two contract fields stay independently documented and the
    lengths can diverge if the contract ever does.
    """
    return accuracy_sparkline(recent_error_rate)[:_ACCURACY_HISTORY_LEN]


def bucket_trend(current_count: int) -> list[int]:
    """A length-12 per-day class-count trend for ONE ranking bucket.

    Ramps from a baseline toward ``current_count`` (the bucket's count today) so the small
    multiples in the dashboard header read as "how this bucket's size approached today". The
    baseline is ``ceil(current/2)`` for a non-empty bucket (a gentle rise into the current size)
    and 0 for an empty one. Deterministic — no randomness.
    """
    if current_count <= 0:
        return [0] * _BUCKET_TREND_LEN
    baseline = (current_count + 1) // 2
    return _ramp(float(baseline), float(current_count), _BUCKET_TREND_LEN)


def skill_gap_series(class_gap_percent: float) -> list[int]:
    """A length-14 class-wide skill-gap series (0..100) for the aggregate area chart.

    ``class_gap_percent`` is today's class-wide skill gap (the share of class KC-mastery that is
    still missing, 0..100). The ramp approaches it from a baseline a little ABOVE (the gap was
    wider before, narrowing toward today) so the area chart reads as improvement, clamped to
    0..100. Deterministic.
    """
    current = min(100.0, max(0.0, class_gap_percent))
    baseline = min(100.0, current + 12.0)
    return _ramp(baseline, current, _SKILL_GAP_LEN)


def remediation_estimate_minutes(remediation_lesson_count: int) -> int | None:
    """Estimated remediation minutes from the number of lessons to re-cover, or ``None``.

    A proxy: we do not store per-lesson timing, so the estimate is
    ``remediation_lesson_count × _MINUTES_PER_LESSON``. ``remediation_lesson_count`` is the number
    of catalog lessons that train the student's weakest KC (the remediation path back through that
    skill); the service computes it from catalog metadata. ``None`` when there is no weakest KC /
    no lessons to remediate (nothing to estimate). Recorded as a heuristic for the decision log
    (CLAUDE.md §8.4).
    """
    if remediation_lesson_count <= 0:
        return None
    return remediation_lesson_count * _MINUTES_PER_LESSON


__all__ = [
    "accuracy_history",
    "accuracy_sparkline",
    "bucket_trend",
    "remediation_estimate_minutes",
    "skill_gap_series",
]
