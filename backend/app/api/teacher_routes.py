"""HTTP routes for the teacher surface (Slice TCH.B2). Thin handlers only.

Its own router (mounted by ``create_app`` alongside the turn-loop and auth routers) so the
import direction stays one-way and acyclic, exactly like ``auth_routes``: ``teacher_routes`` →
``routes`` (for ``StoreDep``) and → ``dependencies`` (for the teacher auth dependency), with
nothing importing back. The turn-loop ``routes.py`` never imports the teacher layer, so the turn
endpoints carry no identity dependency (ARCHITECTURE.md §14 invariant 8).

Auth reuses the PL.3 Google-OIDC seam plus ``Learner.role`` — no second credential scheme (owner
decision, lean scope). Two ways to be a teacher: a Google learner whose row is ``role="teacher"``,
or the one-click, password-free DEMO teacher minted by ``POST /teacher/demo-login``. As with the
rest of ``api/`` (CLAUDE.md §7), these handlers carry no business logic: ``current_teacher`` does
the authorize work and the store owns the demo-teacher seeding; the handler only shapes the typed
response.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentTeacherDep, demo_bearer_for
from app.api.routes import StoreDep
from app.api.schemas import (
    AssignUnitRequest,
    AssignUnitResult,
    CreateReminderRequest,
    DemoLoginResponse,
    TeacherAggregateTrends,
    TeacherHandle,
    TeacherReminderView,
    TeacherRosterView,
    TeacherStudentView,
    UpdateReminderRequest,
)
from app.api.teacher_service import TeacherService
from app.db.repositories import DEMO_TEACHER_SESSION_ID
from app.teacher.assign import StudentNotOnRosterError, UnknownUnitError

# Tagged "teacher" so the endpoints group separately in the OpenAPI docs; ``create_app`` mounts
# this next to the turn-loop and auth routers.
teacher_router = APIRouter(prefix="/teacher", tags=["teacher"])


@teacher_router.post("/demo-login", response_model=DemoLoginResponse)
def demo_login(store: StoreDep) -> DemoLoginResponse:
    """Seed-or-return the one-click demo teacher and its NON-secret handle (Slice TCH.B2).

    The "Teacher demo" tab POSTs here once; the response carries the ``token`` the frontend then
    echoes back as ``Authorization: Bearer <token>`` on subsequent teacher requests. The token is
    public by design — a free, password-free demo, not an account. Idempotent: clicking the demo
    button repeatedly returns the same teacher (one durable row). 503 when the app has no
    persistence channel, since the demo teacher must be a real row to authenticate later."""
    handle = store.provision_demo_teacher()
    if handle is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="account persistence is unavailable",
        )
    return DemoLoginResponse(
        learner_id=handle.learner_id,
        email=handle.email,
        role="teacher",
        token=demo_bearer_for(DEMO_TEACHER_SESSION_ID),
    )


@teacher_router.get("/me", response_model=TeacherHandle)
def teacher_me(teacher: CurrentTeacherDep) -> TeacherHandle:
    """Return the authenticated teacher's identity handle, or the auth dependency rejects first.

    ``current_teacher`` 401s an anonymous/invalid request and 403s an authenticated student, so
    reaching this body means the caller is a teacher. The frontend uses it as the teacher-route
    guard ("am I allowed on the dashboard?"). Identity stays contained to this surface — role
    never reaches the turn decision (invariant 8)."""
    return TeacherHandle(learner_id=teacher.learner_id, email=teacher.email, role=teacher.role)


@teacher_router.get("/roster", response_model=TeacherRosterView)
def teacher_roster(teacher: CurrentTeacherDep, store: StoreDep) -> TeacherRosterView:
    """The signed-in teacher's roster, ranked-summary rows for the dashboard (TCH.B8).

    ``current_teacher`` has already authorized the caller. The coordinator reads only this
    teacher's own roster (the TCH.B1 owns-guard), so a teacher never sees another's students.
    """
    service = TeacherService(store.session_factory)
    return service.roster(teacher.learner_id, datetime.now(UTC))


@teacher_router.get("/aggregate-trends", response_model=TeacherAggregateTrends)
def teacher_aggregate_trends(teacher: CurrentTeacherDep, store: StoreDep) -> TeacherAggregateTrends:
    """Class-wide trend series for the dashboard (the aggregate skill-gap area chart).

    ``current_teacher`` has already authorized the caller; the series is computed only over THIS
    teacher's roster. Declared BEFORE ``/student/{student_id}`` so the literal path is matched
    ahead of the parameterized one.
    """
    service = TeacherService(store.session_factory)
    return service.aggregate_trends(teacher.learner_id, datetime.now(UTC))


@teacher_router.get("/reminders", response_model=list[TeacherReminderView])
def teacher_list_reminders(
    teacher: CurrentTeacherDep, store: StoreDep
) -> list[TeacherReminderView]:
    """The authenticated teacher's to-do reminders, newest-first. Scoped to this teacher."""
    return TeacherService(store.session_factory).list_reminders(teacher.learner_id)


@teacher_router.post("/reminders", response_model=TeacherReminderView)
def teacher_create_reminder(
    body: CreateReminderRequest, teacher: CurrentTeacherDep, store: StoreDep
) -> TeacherReminderView:
    """Create a reminder for the authenticated teacher. 503 when persistence is unavailable."""
    view = TeacherService(store.session_factory).create_reminder(teacher.learner_id, body.text)
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="account persistence is unavailable",
        )
    return view


@teacher_router.patch("/reminders/{reminder_id}", response_model=TeacherReminderView)
def teacher_update_reminder(
    reminder_id: str,
    body: UpdateReminderRequest,
    teacher: CurrentTeacherDep,
    store: StoreDep,
) -> TeacherReminderView:
    """Toggle a reminder's done flag. 404 if it is unknown or not this teacher's."""
    view = TeacherService(store.session_factory).set_reminder_done(
        teacher.learner_id, reminder_id, body.done
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reminder not found")
    return view


@teacher_router.get("/student/{student_id}", response_model=TeacherStudentView)
def teacher_student(
    student_id: str, teacher: CurrentTeacherDep, store: StoreDep
) -> TeacherStudentView:
    """One student's full drill-in (TCH.B8). 404 if the student is not on this teacher's roster.

    ``student_id`` is the student's external key (``Learner.session_id``). A foreign or unknown
    student is an indistinguishable 404 — the teacher must not learn whether the id exists.
    """
    view = TeacherService(store.session_factory).student(
        teacher.learner_id, student_id, datetime.now(UTC)
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="student not found")
    return view


@teacher_router.post("/student/{student_id}/assign-unit", response_model=AssignUnitResult)
def teacher_assign_unit(
    student_id: str,
    body: AssignUnitRequest,
    teacher: CurrentTeacherDep,
    store: StoreDep,
) -> AssignUnitResult:
    """Assign the next unit to a student, returning the refreshed drill-in (TCH.B7/B8).

    Idempotent (re-assigning the same unit is a touch, not a duplicate). 404 when the student is
    unknown or not on this teacher's roster; 400 when the unit slug is not a real unit. A teacher
    may assign a unit whose prereqs are unmet — availability is advisory (TCH.Q5).
    """
    service = TeacherService(store.session_factory)
    try:
        view = service.assign(teacher.learner_id, student_id, body.unit_id, datetime.now(UTC))
    except StudentNotOnRosterError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="student not found"
        ) from exc
    except UnknownUnitError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unknown unit") from exc
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="student not found")
    return AssignUnitResult(student=view)


__all__ = ["teacher_router"]
