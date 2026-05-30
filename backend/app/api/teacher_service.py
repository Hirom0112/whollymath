"""Teacher dashboard coordinator — loads a student's state and assembles the wire views (TCH.B8).

The service layer between the thin ``/teacher/*`` routes and the pure ``app.teacher`` diagnostics
(CLAUDE.md §7): it owns the DB reads (via ``repo``) and the engine reuse (course map + unit
progress, exactly what ``/me`` and the course product derive), then hands ORM-free inputs to the
pure overview / struggle / alerts / ranking functions and shapes the result into
``TeacherRosterView`` / ``TeacherStudentView``. No diagnosis logic lives here — only loading,
fan-out, and projection.

Every read is roster-scoped: a teacher only ever sees a student returned by
``get_student_if_on_roster`` (the TCH.B1 authorization primitive). Identity/role gate this surface
only; none of it reaches a turn decision (ARCHITECTURE.md §14 invariant 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.api.schemas import (
    ActivityEventView,
    AssignableUnitView,
    KcMasteryView,
    RosterStudentView,
    StruggleSummaryView,
    StudentCategory,
    TeacherAlertView,
    TeacherRosterView,
    TeacherStudentView,
)
from app.db import repositories as repo
from app.db.models import Assignment, Learner, MasteryState, Turn, Unit
from app.domain.curriculum import all_units
from app.domain.knowledge_components import KnowledgeComponentId
from app.mastery.course_map import build_course_map
from app.mastery.retention import ReviewableSkill
from app.mastery.unit_progress import build_unit_progress
from app.teacher import overview
from app.teacher.alerts import evaluate_alerts
from app.teacher.assign import assign_next_unit
from app.teacher.evidence import TurnFact
from app.teacher.ranking import classify_student
from app.teacher.struggle import build_struggle_summary

# How many recent turns appear in the drill-in activity timeline (newest first).
_ACTIVITY_LIMIT = 8


def _aware(dt: datetime) -> datetime:
    """Coerce SQLite's naive timestamps to UTC so elapsed math is like-with-like (PL.1 note)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _reviewable_skills(states: list[MasteryState], now: datetime) -> list[ReviewableSkill]:
    """Project persisted ``MasteryState`` rows into the retention model's inputs (mirrors /me)."""
    return [
        ReviewableSkill(
            kc=KnowledgeComponentId(s.kc_id),
            confirmed=s.confirmed,
            bkt_probability=s.bkt_probability,
            last_practiced=_aware(s.updated_at),
        )
        for s in states
    ]


def _turn_fact(turn: Turn) -> TurnFact:
    return TurnFact(
        correct=turn.correct,
        error_category=turn.error_type,
        hint_used=turn.hint_used,
        created_at=_aware(turn.created_at),
    )


def _relative_time(delta: timedelta) -> str:
    """Humanize an elapsed time as a short relative label ('20m ago', '2h ago', '3d ago')."""
    seconds = delta.total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{delta.days}d ago"


def _activity(turns: list[Turn], now: datetime) -> list[ActivityEventView]:
    """The most recent turns as a newest-first timeline.

    Labels are templated from the persisted ``Turn`` fields (we do not store the problem text), so
    they are honest-but-generic — correctness plus whether a hint was used. A richer replay-backed
    timeline is TCH.B9's job.
    """
    recent = turns[-_ACTIVITY_LIMIT:]
    events: list[ActivityEventView] = []
    for turn in reversed(recent):
        base = "Answered a problem correctly" if turn.correct else "Missed a problem"
        label = f"{base} (used a hint)" if turn.hint_used else base
        events.append(
            ActivityEventView(
                at=_relative_time(now - _aware(turn.created_at)),
                label=label,
                outcome="correct" if turn.correct else "incorrect",
            )
        )
    return events


def _display_name(learner: Learner) -> str:
    """A human label for a learner: the email local-part, else a stable 'Student N'."""
    if learner.email:
        return learner.email.split("@", 1)[0]
    return f"Student {learner.id}"


@dataclass(frozen=True)
class _Evidence:
    """Everything the two teacher views need for one student, computed once."""

    masteries: list[KcMasteryView]
    strengths: list[KcMasteryView]
    weaknesses: list[KcMasteryView]
    current_unit_title: str | None
    current_lesson_title: str | None
    percent_complete: float
    alerts: list[TeacherAlertView]
    struggle: StruggleSummaryView
    activity: list[ActivityEventView]
    assignable_units: list[AssignableUnitView]
    assigned_unit_id: str | None
    category: StudentCategory
    category_reason: str


def _assigned_unit_slug(db: OrmSession, assignment: Assignment | None) -> str | None:
    if assignment is None:
        return None
    unit = db.get(Unit, assignment.unit_id)
    return unit.slug if unit is not None else None


def _assemble_evidence(db: OrmSession, student: Learner, now: datetime) -> _Evidence:
    """Load a student's state and run the full diagnostic fan-out (B3–B6) once."""
    catalog = all_units()
    states = repo.load_mastery_states(db, student.id)
    skills = _reviewable_skills(states, now)
    confirmed = frozenset(KnowledgeComponentId(s.kc_id) for s in states if s.confirmed)

    nodes = build_course_map(skills, now)
    unit_progress = build_unit_progress(catalog, nodes, confirmed)

    masteries = overview.kc_masteries(nodes)
    strengths, weaknesses = overview.split_strengths_weaknesses(masteries)
    unit_title, lesson_title, percent = overview.current_unit_and_lesson(unit_progress, catalog)
    assignable = overview.assignable_units(unit_progress, catalog)

    turns = repo.load_turns_for_learner(db, student.id)
    facts = [_turn_fact(t) for t in turns]
    alerts = evaluate_alerts(facts, now)
    struggle = build_struggle_summary(facts, weaknesses)
    activity = _activity(turns, now)

    assigned_slug = _assigned_unit_slug(db, repo.get_assigned_unit(db, student.id))
    category, reason = classify_student(alerts, weaknesses)

    return _Evidence(
        masteries=masteries,
        strengths=strengths,
        weaknesses=weaknesses,
        current_unit_title=unit_title,
        current_lesson_title=lesson_title,
        percent_complete=percent,
        alerts=alerts,
        struggle=struggle,
        activity=activity,
        assignable_units=assignable,
        assigned_unit_id=assigned_slug,
        category=category,
        category_reason=reason,
    )


def _roster_row(db: OrmSession, student: Learner, now: datetime) -> RosterStudentView:
    ev = _assemble_evidence(db, student, now)
    return RosterStudentView(
        student_id=student.session_id,
        name=_display_name(student),
        category=ev.category,
        category_reason=ev.category_reason,
        current_unit_title=ev.current_unit_title,
        current_lesson_title=ev.current_lesson_title,
        percent_complete=ev.percent_complete,
        alerts=ev.alerts,
    )


def _student_view(db: OrmSession, student: Learner, now: datetime) -> TeacherStudentView:
    ev = _assemble_evidence(db, student, now)
    return TeacherStudentView(
        student_id=student.session_id,
        name=_display_name(student),
        category=ev.category,
        category_reason=ev.category_reason,
        alerts=ev.alerts,
        struggle=ev.struggle,
        current_unit_title=ev.current_unit_title,
        current_lesson_title=ev.current_lesson_title,
        percent_complete=ev.percent_complete,
        strengths=ev.strengths,
        weaknesses=ev.weaknesses,
        activity=ev.activity,
        assignable_units=ev.assignable_units,
        assigned_unit_id=ev.assigned_unit_id,
    )


@dataclass
class TeacherService:
    """Assembles the teacher dashboard views from persisted state (Slice TCH.B8).

    Holds the optional ``session_factory`` (the same persistence channel ``SessionStore`` uses).
    With no factory — a pure in-memory app — there is no roster to read, so the roster comes back
    empty and student/assign reads return ``None`` (the route 404s). Read methods are roster-scoped
    via ``get_student_if_on_roster``.
    """

    session_factory: sessionmaker[OrmSession] | None = None

    def roster(self, teacher_id: int, now: datetime) -> TeacherRosterView:
        """The teacher's whole roster as ranked summary rows (``GET /teacher/roster``)."""
        if self.session_factory is None:
            return TeacherRosterView(teacher_name="Teacher", class_name="My Class", students=[])
        with self.session_factory() as db:
            teacher = db.get(Learner, teacher_id)
            teacher_name = _display_name(teacher) if teacher is not None else "Teacher"
            class_name = (
                "Demo Class"
                if teacher is not None and teacher.session_id == repo.DEMO_TEACHER_SESSION_ID
                else "My Class"
            )
            students = repo.list_students_for_teacher(db, teacher_id)
            rows = [_roster_row(db, s, now) for s in students]
        return TeacherRosterView(teacher_name=teacher_name, class_name=class_name, students=rows)

    def student(
        self, teacher_id: int, student_session_id: str, now: datetime
    ) -> TeacherStudentView | None:
        """One student's full drill-in, or ``None`` if not on this teacher's roster (→ 404)."""
        if self.session_factory is None:
            return None
        with self.session_factory() as db:
            student = repo.get_learner(db, student_session_id)
            if student is None:
                return None
            if repo.get_student_if_on_roster(db, teacher_id, student.id) is None:
                return None
            return _student_view(db, student, now)

    def assign(
        self, teacher_id: int, student_session_id: str, unit_slug: str, now: datetime
    ) -> TeacherStudentView | None:
        """Assign a unit, then return the refreshed drill-in. ``None`` if the student is unknown.

        Delegates the roster/unit guards to ``app.teacher.assign.assign_next_unit`` (which raises
        ``StudentNotOnRosterError`` → 404, ``UnknownUnitError`` → 400 for the route to map);
        ``None`` here means the session id matched no learner at all (also a 404).
        """
        if self.session_factory is None:
            return None
        with self.session_factory() as db:
            student = repo.get_learner(db, student_session_id)
            if student is None:
                return None
            assign_next_unit(
                db,
                teacher_id=teacher_id,
                student_id=student.id,
                unit_slug=unit_slug,
                now=now,
            )
            db.commit()
            return _student_view(db, student, now)


__all__ = ["TeacherService"]
