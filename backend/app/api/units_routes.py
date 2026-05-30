"""HTTP routes for the unit/lesson shell (Slices DAT.8, DAT.9, DAT.10). Thin handlers only.

The unit-product surface sits on top of the course product (PROJECT.md §3.13): where ``/course``
returns the per-KC learning path, these endpoints return the curriculum's UNIT/LESSON shell with
the learner's progress overlaid — the structure the teacher dashboard and student flow render.

It serves BOTH kinds of learner, mirroring ``course_routes`` exactly:

  - a SIGNED-IN learner (valid Bearer token) → the unit list/detail from their persisted mastery,
    PLUS their teacher-assigned unit surfaced via ``assigned_unit_slug`` (DAT.10);
  - an ANONYMOUS demo learner (no token, just their ``session_id``) → the same shell from their
    in-memory session's progress, with no assignment;
  - neither (a brand-new visitor) → the fresh default shell (all units, root available, the rest
    locked / not-yet-started), so the screen always renders.

Auth is OPTIONAL here (``CurrentLearnerDep``, not ``require_learner``): no header is anonymous —
NOT a 401 — and only a *bad* token 401s (handled in the dependency). Like the rest of ``api/``
the handlers carry no business logic (CLAUDE.md §7): the store derives the unit shell from the
catalog + the course map + the unit-progress overlay; identity/session never reaches the turn-loop
decision (invariant 8). Off the turn loop.

Kept in its own router (mounted by ``create_app``) so "units" is one findable concern, the import
direction one-way and acyclic, mirroring ``course_routes``: ``units_routes`` → ``routes``
(``StoreDep``) and ``units_routes`` → ``dependencies`` (the auth dependency), nothing importing
back.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import CurrentLearnerDep
from app.api.routes import StoreDep
from app.api.schemas import UnitDetailView, UnitListView

# A dedicated router for the unit-product endpoints; ``create_app`` mounts it next to the
# course/turn-loop/auth routers. Tagged "units" so it groups separately in the OpenAPI docs.
units_router = APIRouter(tags=["units"])


@units_router.get("/units", response_model=UnitListView)
def units(
    store: StoreDep,
    learner: CurrentLearnerDep,
    session_id: str | None = Query(
        default=None,
        description="Anonymous demo learner's session id; ignored when a learner is signed in.",
    ),
) -> UnitListView:
    """Return the caller's unit list with per-unit progress (Slices DAT.8, DAT.10).

    A signed-in learner gets the list from their persisted mastery plus their teacher-assigned
    unit (``assigned_unit_slug`` + ``assigned=True`` on the matching unit); an anonymous demo
    learner gets it from their ``session_id``'s in-memory progress with no assignment; a brand-new
    visitor (no token, no/unknown session) gets the fresh default list. Each unit's status +
    percent-complete is derived from the catalog + the course map — reusing the engine, adding no
    new mastery logic (PROJECT.md §3.13).
    """
    now = datetime.now(UTC)
    if learner is not None:
        return store.units_for_learner(learner.learner_id, now)
    return store.units_for_session(session_id, now)


@units_router.get("/unit/{slug}", response_model=UnitDetailView)
def unit_detail(
    slug: str,
    store: StoreDep,
    learner: CurrentLearnerDep,
    session_id: str | None = Query(
        default=None,
        description="Anonymous demo learner's session id; ignored when a learner is signed in.",
    ),
) -> UnitDetailView:
    """Return one unit's detail — lessons + per-lesson progress — for the caller (Slice DAT.9).

    Resolves progress the same way as :func:`units`. A ``slug`` that is not in the curriculum
    catalog yields a 404 (the store returns ``None`` and the handler maps it).
    """
    now = datetime.now(UTC)
    if learner is not None:
        detail = store.unit_detail_for_learner(slug, learner.learner_id, now)
    else:
        detail = store.unit_detail_for_session(slug, session_id, now)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unit not found")
    return detail


__all__ = ["units_router"]
