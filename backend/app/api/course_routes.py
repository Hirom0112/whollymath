"""HTTP route for the course map (Slice CP.A.1 — the course-product home). Thin handler only.

The course product (PROJECT.md §3.13) is an expansion BEYOND the PRD's mastery-engine thesis,
built as a LAYER ON TOP of the engine. This is its first surface: ``GET /course`` returns the
authenticated learner's learning path (every KC with a status), which the frontend renders as
the post-sign-in home.

It is on the AUTHENTICATED path, exactly like ``/me`` — the map is per-learner progress, so it
needs identity (``require_learner`` 401s an anonymous request). Like the rest of ``api/`` it
carries no business logic (CLAUDE.md §7): the store derives the map from persisted mastery + the
prerequisite graph + retention, and the handler only shapes the typed response. Identity stays
contained to this read; it never reaches the turn-loop decision (invariant 8). Off the turn loop.

Kept in its own router (mounted by ``create_app``) so "course" is one findable concern that the
later CP slices (lessons, assignments) can grow into; the import direction stays one-way and
acyclic, mirroring ``auth_routes``: ``course_routes`` → ``routes`` (``StoreDep``) and
``course_routes`` → ``dependencies`` (the auth dependency), with nothing importing back.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.dependencies import RequireLearnerDep
from app.api.routes import StoreDep
from app.api.schemas import CourseView

# A dedicated router for the course-product endpoints; ``create_app`` mounts it next to the
# turn-loop and auth routers. Tagged "course" so it groups separately in the OpenAPI docs.
course_router = APIRouter(tags=["course"])


@course_router.get("/course", response_model=CourseView)
def course(learner: RequireLearnerDep, store: StoreDep) -> CourseView:
    """Return the authenticated learner's learning path — one status per KC (Slice CP.A.1).

    Requires a valid ``Authorization: Bearer <google-id-token>`` (``require_learner`` 401s an
    anonymous request). The status of each node is derived from the learner's persisted mastery
    (PL.1 rows), the prerequisite graph, and the retention model — reusing the engine, adding no
    new mastery logic (PROJECT.md §3.13).
    """
    return store.course_map_for_learner(learner.learner_id, datetime.now(UTC))


__all__ = ["course_router"]
