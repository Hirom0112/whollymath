"""Unit tests for student ranking (Slice TCH.B6).

Pins the locked rule (any urgent alert → struggling) and the ladder beneath it, plus that the
one-line reason is the driving signal.
"""

from __future__ import annotations

from app.api.schemas import (
    AlertKind,
    AlertSeverity,
    KcMasteryView,
    KcStatus,
    StudentCategory,
    TeacherAlertView,
)
from app.domain.knowledge_components import KnowledgeComponentId, get_kc
from app.teacher.ranking import classify_student

_EQ = KnowledgeComponentId.EQUIVALENCE


def _alert(kind: AlertKind, severity: AlertSeverity, message: str) -> TeacherAlertView:
    return TeacherAlertView(kind=kind, severity=severity, message=message)


def _weak() -> KcMasteryView:
    return KcMasteryView(
        kc_id=_EQ.value,
        skill_name=get_kc(_EQ).skill_name,
        probability=0.2,
        status=KcStatus.IN_PROGRESS,
    )


def test_any_urgent_alert_forces_struggling() -> None:
    alerts = [
        _alert(AlertKind.IDLE, AlertSeverity.INFO, "idle"),
        _alert(AlertKind.STUCK, AlertSeverity.URGENT, "Missed the last 3 in a row."),
    ]
    category, reason = classify_student(alerts, [])
    assert category is StudentCategory.STRUGGLING
    assert reason == "Missed the last 3 in a row."  # reason is the urgent alert


def test_warn_without_urgent_is_needs_attention() -> None:
    alerts = [_alert(AlertKind.FAILING_TREND, AlertSeverity.WARN, "Accuracy fell.")]
    category, reason = classify_student(alerts, [])
    assert category is StudentCategory.NEEDS_ATTENTION
    assert reason == "Accuracy fell."


def test_weakness_without_alerts_is_needs_attention() -> None:
    category, reason = classify_student([], [_weak()])
    assert category is StudentCategory.NEEDS_ATTENTION
    assert "below target" in reason


def test_no_alerts_no_weaknesses_is_on_track() -> None:
    category, _reason = classify_student([], [])
    assert category is StudentCategory.ON_TRACK
