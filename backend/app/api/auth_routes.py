"""HTTP routes for Google-OIDC accounts (Slice PL.3). Thin handlers only.

Kept in its own router (mounted by ``create_app`` alongside the turn-loop ``router``) so the
import direction stays one-way and acyclic: ``auth_routes`` → ``routes`` (for ``StoreDep``) and
``auth_routes`` → ``dependencies`` (for the auth dependency), with nothing importing back. The
turn-loop ``routes.py`` therefore never imports the auth layer — the turn endpoints carry no
identity dependency at all (ARCHITECTURE.md §14 invariant 8).

Like the rest of ``api/``, these handlers carry no business logic (CLAUDE.md §7): the auth
dependency does the verify→map-to-learner work, and the store owns the mastery read. The
handler only shapes the typed response.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.dependencies import RequireLearnerDep
from app.api.routes import StoreDep
from app.api.schemas import MeResponse

# A dedicated router for the account endpoints; ``create_app`` mounts it next to the turn-loop
# router. Tagged "auth" so it groups separately in the OpenAPI docs.
auth_router = APIRouter(tags=["auth"])


@auth_router.get("/me", response_model=MeResponse)
def me(learner: RequireLearnerDep, store: StoreDep) -> MeResponse:
    """Return the authenticated learner's identity handle + carried-forward mastery (PL.3).

    Requires a valid ``Authorization: Bearer <google-id-token>`` — the ``require_learner``
    dependency 401s an anonymous request, and ``current_learner`` has already 401'd a
    bad/unconfigured token before we reach here. This is the "same login anywhere → same state"
    proof: the ``learner_id`` is the stable handle the Google ``sub`` maps to (idempotently),
    and ``mastery`` is that learner's persisted per-KC state (PL.1 rows, mastered = confirmed).

    Identity stays contained to this auth path: the handler returns only the ``learner_id`` +
    email label + mastery summary, and never touches the verify→mastery→policy→helpneed turn
    decision (invariant 8).
    """
    return MeResponse(
        learner_id=learner.learner_id,
        email=learner.email,
        mastery=store.mastery_summary_for_learner(learner.learner_id),
        study_plan=store.study_plan_for_learner(learner.learner_id, datetime.now(UTC)),
    )


__all__ = ["auth_router"]
