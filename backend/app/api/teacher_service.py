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
    BucketTrends,
    KcMasteryView,
    RosterStudentView,
    StruggleSummaryView,
    StudentCategory,
    TeacherAggregateTrends,
    TeacherAlertView,
    TeacherReminderView,
    TeacherRosterView,
    TeacherStudentView,
)
from app.db import repositories as repo
from app.db.models import Assignment, Learner, MasteryState, TeacherReminder, Turn, Unit
from app.domain.curriculum import CatalogUnit, all_units
from app.domain.knowledge_components import KnowledgeComponentId
from app.mastery.course_map import build_course_map
from app.mastery.retention import ReviewableSkill
from app.mastery.unit_progress import build_unit_progress
from app.teacher import overview, trends
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


def _remediation_lesson_count(
    weaknesses: list[KcMasteryView], catalog: tuple[CatalogUnit, ...]
) -> int:
    """How many catalog lessons train the student's WEAKEST KC — the remediation-path size proxy.

    ``weaknesses`` is weakest-first (overview projection), so ``weaknesses[0]`` is the skill to
    remediate. We count catalog lessons whose ``kc_id`` matches that KC: the set of lessons a
    student would re-cover to get the skill back. Zero when there is no weakest KC or the catalog
    maps no lesson to it — the estimate then comes back ``None``. Pure over catalog metadata
    (CLAUDE.md §7); the minutes conversion lives in ``app.teacher.trends``.
    """
    if not weaknesses:
        return 0
    weakest_kc = weaknesses[0].kc_id
    return sum(1 for unit in catalog for lesson in unit.lessons if lesson.kc_id == weakest_kc)


def _teacher_note(struggle: StruggleSummaryView, category: StudentCategory) -> str | None:
    """A short teacher-facing note line, derived from the struggle summary (templated, NO LLM).

    Leads with the struggle headline for a student who has a diagnosed gap; for an on-track
    student with no specific struggle we return ``None`` (no note to surface) rather than inventing
    a positive line. Identity/surface only — never a turn-loop decision (CLAUDE.md §8.2)."""
    if category is StudentCategory.ON_TRACK and struggle.matched_misconception is None:
        return None
    return struggle.headline


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
    # Recent-accuracy series (0..100), deterministically derived from the struggle's recent error
    # rate — reused for both the roster-card sparkline and the drill-in accuracy history.
    accuracy_series: list[int]
    # Estimated minutes to remediate the weakest KC (lessons-to-recover × per-lesson budget), or
    # None when there is nothing to remediate.
    remediation_estimate_minutes: int | None
    # A short teacher-facing note line (from the struggle headline), or None when on-track.
    notes: str | None


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

    # Dashboard-upgrade derivations — deterministic, from already-computed evidence (no per-day
    # history persisted yet; see app.teacher.trends for the synthesis rationale).
    accuracy_series = trends.accuracy_history(struggle.recent_error_rate)
    remediation_minutes = trends.remediation_estimate_minutes(
        _remediation_lesson_count(weaknesses, catalog)
    )
    notes = _teacher_note(struggle, category)

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
        accuracy_series=accuracy_series,
        remediation_estimate_minutes=remediation_minutes,
        notes=notes,
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
        trend=ev.accuracy_series,
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
        remediation_estimate_minutes=ev.remediation_estimate_minutes,
        accuracy_history=ev.accuracy_series,
        notes=ev.notes,
    )


def _bucket_trends(rows: list[RosterStudentView]) -> BucketTrends:
    """Build the per-bucket class-count trend from the current roster rows (deterministic).

    Counts how many students are in each ranking bucket TODAY, then asks ``trends.bucket_trend``
    for a synthetic length-12 approach to that count (no per-day snapshot store yet). Pure over the
    rows we already computed."""
    counts = {
        StudentCategory.STRUGGLING: 0,
        StudentCategory.NEEDS_ATTENTION: 0,
        StudentCategory.ON_TRACK: 0,
    }
    for row in rows:
        counts[row.category] += 1
    return BucketTrends(
        struggling=trends.bucket_trend(counts[StudentCategory.STRUGGLING]),
        needs_attention=trends.bucket_trend(counts[StudentCategory.NEEDS_ATTENTION]),
        on_track=trends.bucket_trend(counts[StudentCategory.ON_TRACK]),
    )


def _class_skill_gap_percent(db: OrmSession, students: list[Learner], now: datetime) -> float:
    """Today's class-wide skill gap (0..100): the mean missing-mastery across touched KCs.

    For each student we read their course-map KC probabilities and average ``(1 - p)`` over the
    KCs they have actually touched (``probability > 0``); the class gap is the mean of those
    per-student gaps. An empty class, or one with no touched KCs, has a 0 gap. Pure over loaded
    state (reuses ``_assemble_evidence`` rather than re-deriving mastery — CLAUDE.md §7)."""
    per_student_gaps: list[float] = []
    for student in students:
        masteries = _assemble_evidence(db, student, now).masteries
        touched = [m.probability for m in masteries if m.probability > 0.0]
        if not touched:
            continue
        per_student_gaps.append(sum(1.0 - p for p in touched) / len(touched))
    if not per_student_gaps:
        return 0.0
    return (sum(per_student_gaps) / len(per_student_gaps)) * 100.0


def _reminder_view(reminder: TeacherReminder) -> TeacherReminderView:
    """Project a persisted reminder row onto its wire view (id as a string)."""
    return TeacherReminderView(id=str(reminder.id), text=reminder.text, done=reminder.done)


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
        as_of = now.date().isoformat()
        if self.session_factory is None:
            return TeacherRosterView(
                teacher_name="Teacher",
                class_name="My Class",
                students=[],
                as_of=as_of,
                bucket_trends=_bucket_trends([]),
            )
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
        return TeacherRosterView(
            teacher_name=teacher_name,
            class_name=class_name,
            students=rows,
            as_of=as_of,
            bucket_trends=_bucket_trends(rows),
        )

    def aggregate_trends(self, teacher_id: int, now: datetime) -> TeacherAggregateTrends:
        """Class-wide trend series for the dashboard (``GET /teacher/aggregate-trends``).

        ``skill_gap_series`` is the class-wide skill-gap percentage over the recent window,
        deterministically derived from current class mastery (no per-day snapshot store yet). An
        empty/factory-less roster yields a zero-gap series (no gap to plot).
        """
        if self.session_factory is None:
            return TeacherAggregateTrends(skill_gap_series=trends.skill_gap_series(0.0))
        with self.session_factory() as db:
            students = repo.list_students_for_teacher(db, teacher_id)
            gap_percent = _class_skill_gap_percent(db, students, now)
        return TeacherAggregateTrends(skill_gap_series=trends.skill_gap_series(gap_percent))

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

    def list_reminders(self, teacher_id: int) -> list[TeacherReminderView]:
        """The teacher's reminders, newest-first (``GET /teacher/reminders``).

        Empty list with no persistence channel (the pure in-memory app has nowhere to store
        them) — the same graceful-empty behavior the roster has."""
        if self.session_factory is None:
            return []
        with self.session_factory() as db:
            return [_reminder_view(r) for r in repo.list_reminders_for_teacher(db, teacher_id)]

    def create_reminder(self, teacher_id: int, text: str) -> TeacherReminderView | None:
        """Create a reminder for the teacher (``POST /teacher/reminders``). ``None`` if no store.

        Scoped to the authenticated teacher (``teacher_id``). ``None`` only when there is no
        persistence channel (→ the route 503s, mirroring demo-login); otherwise the created view.
        """
        if self.session_factory is None:
            return None
        with self.session_factory() as db:
            reminder = repo.create_reminder(db, teacher_id=teacher_id, text=text)
            db.commit()
            db.refresh(reminder)
            return _reminder_view(reminder)

    def set_reminder_done(
        self, teacher_id: int, reminder_id: str, done: bool
    ) -> TeacherReminderView | None:
        """Toggle a reminder's ``done`` flag (``PATCH /teacher/reminders/{id}``).

        ``None`` when the id is non-numeric, missing, or belongs to ANOTHER teacher (the route
        404s) — a foreign reminder is indistinguishable from a missing one (the owns-surface
        isolation the rest of the teacher writes use). Scoped to ``teacher_id``."""
        if self.session_factory is None:
            return None
        try:
            numeric_id = int(reminder_id)
        except ValueError:
            return None
        with self.session_factory() as db:
            reminder = repo.set_reminder_done(
                db, teacher_id=teacher_id, reminder_id=numeric_id, done=done
            )
            if reminder is None:
                return None
            db.commit()
            db.refresh(reminder)
            return _reminder_view(reminder)


__all__ = ["TeacherService"]
