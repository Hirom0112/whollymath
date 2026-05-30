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

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentTeacherDep, demo_bearer_for
from app.api.routes import StoreDep
from app.api.schemas import DemoLoginResponse, TeacherHandle
from app.db.repositories import DEMO_TEACHER_SESSION_ID

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


__all__ = ["teacher_router"]
