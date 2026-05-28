"""HTTP route for the course map (Slice CP.A.1 — the course-product home). Thin handler only.

The course product (PROJECT.md §3.13) is an expansion BEYOND the PRD's mastery-engine thesis,
built as a LAYER ON TOP of the engine. This is its first surface: ``GET /course`` returns the
authenticated learner's learning path (every KC with a status), which the frontend renders as
the post-sign-in home.

It serves BOTH kinds of learner, because the course map is the home for everyone (CP.A.2 — the
user's decision that the "Student Demo Free" path also gets a course):

  - a SIGNED-IN learner (valid Bearer token) → the map from their persisted mastery (PL.1 rows);
  - an ANONYMOUS demo learner (no token, just their ``session_id``) → the map from their
    in-memory session's progress;
  - neither (a brand-new visitor) → the fresh default path (root available, the rest locked),
    so the home always renders.

Auth is OPTIONAL here (``current_learner``, not ``require_learner``): no header is anonymous —
NOT a 401 — and only a *bad* token 401s (handled in the dependency). Like the rest of ``api/``
the handler carries no business logic (CLAUDE.md §7): the store derives the map from mastery +
the prerequisite graph + retention; identity/session never reaches the turn-loop decision
(invariant 8). Off the turn loop.

Kept in its own router (mounted by ``create_app``) so "course" is one findable concern that the
later CP slices (lessons, assignments) can grow into; the import direction stays one-way and
acyclic, mirroring ``auth_routes``: ``course_routes`` → ``routes`` (``StoreDep``) and
``course_routes`` → ``dependencies`` (the auth dependency), with nothing importing back.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query

from app.api.dependencies import CurrentLearnerDep
from app.api.routes import StoreDep
from app.api.schemas import CourseView

# A dedicated router for the course-product endpoints; ``create_app`` mounts it next to the
# turn-loop and auth routers. Tagged "course" so it groups separately in the OpenAPI docs.
course_router = APIRouter(tags=["course"])


@course_router.get("/course", response_model=CourseView)
def course(
    store: StoreDep,
    learner: CurrentLearnerDep,
    session_id: str | None = Query(
        default=None,
        description="Anonymous demo learner's session id; ignored when a learner is signed in.",
    ),
) -> CourseView:
    """Return the caller's learning path — one status per KC (Slices CP.A.1, CP.A.2).

    A signed-in learner gets the map from their persisted mastery; an anonymous demo learner gets
    it from their ``session_id``'s in-memory progress; a brand-new visitor (no token, no/unknown
    session) gets the fresh default path. Each node's status is derived from the prerequisite
    graph, the mastery state, and the retention model — reusing the engine, adding no new mastery
    logic (PROJECT.md §3.13).
    """
    now = datetime.now(UTC)
    if learner is not None:
        return store.course_map_for_learner(learner.learner_id, now)
    return store.course_map_for_session(session_id, now)


__all__ = ["course_router"]
