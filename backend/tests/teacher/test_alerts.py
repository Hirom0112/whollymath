"""Unit tests for the teacher alert engine (Slice TCH.B5).

Pure rules over a ``TurnFact`` stream — pin each named rule's firing condition, the
stuck/remediation de-confliction, and the most-severe-first ordering.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.api.schemas import AlertKind, AlertSeverity
from app.teacher.alerts import evaluate_alerts
from app.teacher.evidence import TurnFact

_NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def _t(
    correct: bool,
    *,
    error: str | None = None,
    hint: bool = False,
    ago: timedelta = timedelta(minutes=1),
) -> TurnFact:
    return TurnFact(
        correct=correct,
        error_category=None if correct else error,
        hint_used=hint,
        created_at=_NOW - ago,
    )


def _kinds(alerts: Sequence[object]) -> set[AlertKind]:
    return {a.kind for a in alerts}  # type: ignore[attr-defined]


def test_no_turns_yields_no_alerts() -> None:
    assert evaluate_alerts([], _NOW) == []


def test_stuck_fires_on_trailing_wrong_run() -> None:
    turns = [_t(True), _t(False, error="operation"), _t(False, error="format"), _t(False)]
    alerts = evaluate_alerts(turns, _NOW)
    stuck = [a for a in alerts if a.kind is AlertKind.STUCK]
    assert len(stuck) == 1
    assert stuck[0].severity is AlertSeverity.URGENT


def test_repeated_misconception_fires_on_dominant_category() -> None:
    # Interleave correct answers so there is no trailing all-wrong run (isolating this rule).
    turns = [
        _t(False, error="magnitude"),
        _t(True),
        _t(False, error="magnitude"),
        _t(True),
        _t(False, error="magnitude"),
        _t(True),
    ]
    alerts = evaluate_alerts(turns, _NOW)
    rep = [a for a in alerts if a.kind is AlertKind.REPEATED_MISCONCEPTION]
    assert len(rep) == 1
    assert rep[0].severity is AlertSeverity.URGENT
    assert "3 of the last" in rep[0].message


def test_failing_trend_fires_when_accuracy_slides() -> None:
    # 8 recent: first half all correct, second half mostly wrong but not a 3-trailing-wrong run.
    turns = [
        _t(True),
        _t(True),
        _t(True),
        _t(True),
        _t(False, error="operation"),
        _t(False, error="format"),
        _t(False, error="magnitude"),
        _t(True),  # trailing correct → STUCK does not fire
    ]
    alerts = evaluate_alerts(turns, _NOW)
    assert AlertKind.FAILING_TREND in _kinds(alerts)
    assert AlertKind.STUCK not in _kinds(alerts)


def test_low_engagement_fires_on_few_attempts() -> None:
    alerts = evaluate_alerts([_t(True)], _NOW)
    low = [a for a in alerts if a.kind is AlertKind.LOW_ENGAGEMENT]
    assert len(low) == 1
    assert low[0].severity is AlertSeverity.WARN


def test_idle_fires_after_inactivity() -> None:
    # A handful of attempts so LOW_ENGAGEMENT doesn't also fire; last one 5 days ago.
    turns = [
        _t(True, ago=timedelta(days=5, minutes=4)),
        _t(True, ago=timedelta(days=5, minutes=3)),
        _t(True, ago=timedelta(days=5, minutes=2)),
        _t(True, ago=timedelta(days=5)),
    ]
    alerts = evaluate_alerts(turns, _NOW)
    idle = [a for a in alerts if a.kind is AlertKind.IDLE]
    assert len(idle) == 1
    assert idle[0].severity is AlertSeverity.INFO
    assert "5 days" in idle[0].message


def test_hint_dependent_fires_when_corrects_are_all_hinted() -> None:
    """Hint-hunter Hugo: many correct answers, but every one used a hint (0 unscaffolded).

    Finding #2 (T1_T2_COORDINATION): without this rule Hugo shows on_track because none of the
    other rules fire (he's not wrong/stuck/idle). His corrects are real but scaffold-supplied,
    so he should surface as needs_attention (WARN).
    """
    turns = [_t(True, hint=True) for _ in range(10)]
    alerts = evaluate_alerts(turns, _NOW)
    hd = [a for a in alerts if a.kind is AlertKind.HINT_DEPENDENT]
    assert len(hd) == 1
    assert hd[0].severity is AlertSeverity.WARN


def test_hint_dependent_silent_for_unscaffolded_solver() -> None:
    """Procedure Priya: mostly unscaffolded corrects → genuine fluency, no hint-dependency flag."""
    turns = [_t(True) for _ in range(8)] + [_t(True, hint=True) for _ in range(2)]
    assert AlertKind.HINT_DEPENDENT not in _kinds(evaluate_alerts(turns, _NOW))


def test_hint_dependent_needs_enough_corrects() -> None:
    """A single hinted correct isn't a pattern — don't flag on thin evidence."""
    turns = [_t(True, hint=True), _t(False, error="operation")]
    assert AlertKind.HINT_DEPENDENT not in _kinds(evaluate_alerts(turns, _NOW))


def test_remediation_stuck_replaces_stuck_when_in_remediation() -> None:
    turns = [_t(True), _t(False), _t(False), _t(False)]
    alerts = evaluate_alerts(turns, _NOW, in_remediation=True)
    kinds = _kinds(alerts)
    assert AlertKind.REMEDIATION_STUCK in kinds
    assert AlertKind.STUCK not in kinds


def test_alerts_sorted_most_severe_first() -> None:
    # Trailing wrong run (urgent STUCK) + a repeated category (urgent) + idle would need a gap;
    # build urgent + warn and assert urgent leads.
    turns = [
        _t(False, error="magnitude"),
        _t(False, error="magnitude"),
        _t(False, error="magnitude"),
    ]
    alerts = evaluate_alerts(turns, _NOW)
    severities = [a.severity for a in alerts]
    assert severities == sorted(
        severities,
        key=lambda s: {AlertSeverity.URGENT: 0, AlertSeverity.WARN: 1, AlertSeverity.INFO: 2}[s],
    )
    assert alerts[0].severity is AlertSeverity.URGENT
