"""FastAPI auth dependency: Google ID token → persistent learner (Slice PL.3).

This is the API-layer seam between the ``auth/`` verifier (which only decides "is this a
valid Google token, and whose?") and persistence (which maps that identity to a learner row).
It is ADDITIVE and conservative — the anonymous, session-id flow (TECH_STACK §9) is entirely
unchanged:

  - NO ``Authorization`` header  → ``current_learner`` returns ``None`` (anonymous). The v1
    turn-loop endpoints never depend on this, so they are unaffected.
  - a Bearer token + a configured ``GOOGLE_CLIENT_ID`` → verify it (``verify_google_id_token``,
    which delegates to Google's official library), then map the verified ``sub`` to a Learner
    row (idempotent ``get_or_create_learner_by_google_sub``) and return an ``AuthedLearner``.
  - a Bearer token that fails verification → HTTP 401.
  - a Bearer token but ``GOOGLE_CLIENT_ID`` UNSET → HTTP 401 ("auth not configured"); we never
    silently accept a token we cannot verify. An ABSENT token is still anonymous, so leaving
    accounts unconfigured does not break the anonymous flow.

Invariant 8 (ARCHITECTURE.md §14): the verified identity produced here is reduced to an
``AuthedLearner`` carrying only a ``learner_id`` (for persistence/continuity) plus the email
display label. It is NOT threaded into ``/turn``'s decision — the turn loop stays
identity-free; auth only affects WHICH learner row persistence/continuity uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.api.routes import StoreDep
from app.auth.google import (
    InvalidIdTokenError,
    google_client_id,
    verify_google_id_token,
)
from app.db import repositories as repo

_BEARER_PREFIX = "bearer "


@dataclass(frozen=True)
class AuthedLearner:
    """The minimal authenticated learner the API carries downstream (Slice PL.3).

    Deliberately NOT the ORM ``Learner`` (which would be detached once its session closes) and
    deliberately NOT the Google ``sub`` (an identifier we key on but never re-expose). Only the
    stable persistence handle (``learner_id``), the email display label, and the ``role`` tag
    cross this seam, so identity cannot leak into the turn decision (invariant 8). ``role`` is
    carried because it gates which API SURFACE a request may use (student tutor vs. teacher
    dashboard, Slice TCH.B2) — it is still never read by the mastery/policy/tutor/llm path."""

    learner_id: int
    email: str | None
    role: str


def _extract_bearer_token(authorization: str | None) -> str | None:
    """The bearer token from an ``Authorization`` header, or ``None`` if not a bearer credential.

    ``None`` (no header) and a non-``Bearer`` scheme both mean "no presented bearer token" →
    anonymous. The scheme match is case-insensitive per RFC 7235; an empty token after the
    prefix is treated as no credential.
    """
    if authorization is None:
        return None
    if not authorization.lower().startswith(_BEARER_PREFIX):
        return None
    token = authorization[len(_BEARER_PREFIX) :].strip()
    return token or None


def current_learner(
    store: StoreDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthedLearner | None:
    """Resolve the authenticated learner from a Bearer token, or ``None`` if anonymous.

    See the module docstring for the full behavior matrix. The verified ``sub`` is mapped to a
    Learner row via the repository (idempotent), so the same Google login always resolves to
    the same learner — the cross-device continuity property. The mapping write commits its own
    short-lived unit of work; if no ``session_factory`` is wired (the pure in-memory demo) a
    presented-and-verified token cannot be persisted to a learner row, which is a server-side
    configuration gap → 503 rather than a misleading 401 (the token WAS valid).
    """
    token = _extract_bearer_token(authorization)
    if token is None:
        return None  # anonymous: the v1 session-id flow, unchanged.

    client_id = google_client_id()
    if client_id is None:
        # A token was presented but accounts are not configured for this process. We must not
        # accept a token we cannot verify (CLAUDE.md §8.5 — fail loudly, don't invent).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication is not configured",
        )

    try:
        identity = verify_google_id_token(token, client_id=client_id)
    except InvalidIdTokenError as exc:
        # One opaque 401 for every verification failure — no detail leak (the verifier already
        # collapsed the reason; we keep the HTTP detail generic too).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        ) from exc

    if store.session_factory is None:
        # The token is valid but there is no DB to map it to a persistent learner. This is a
        # server configuration gap, not a client auth failure — surface it as 503, not 401.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="account persistence is unavailable",
        )

    with store.session_factory() as db:
        learner = repo.get_or_create_learner_by_google_sub(db, identity.sub, email=identity.email)
        db.commit()
        return AuthedLearner(learner_id=learner.id, email=learner.email, role=learner.role)


# The dependency-injected authenticated learner, as an Annotated alias so route signatures read
# cleanly (mirrors ``StoreDep`` in routes.py). ``None`` for an anonymous request.
CurrentLearnerDep = Annotated[AuthedLearner | None, Depends(current_learner)]


def require_learner(learner: CurrentLearnerDep) -> AuthedLearner:
    """Like ``current_learner`` but 401s when there is no authenticated learner.

    For endpoints that REQUIRE identity (e.g. ``/me``). Anonymous (``None``) → 401; everything
    else is already handled by ``current_learner`` (a bad/unconfigured token raised before we
    get here)."""
    if learner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    return learner


RequireLearnerDep = Annotated[AuthedLearner, Depends(require_learner)]


# The Bearer prefix that marks the password-free DEMO teacher handle (Slice TCH.B2). The
# one-click "Teacher demo" tab echoes ``demo:<demo-teacher session_id>`` back as a Bearer
# credential; it is NON-secret by design (a free demo, not an account — owner decision). The
# suffix is the demo teacher's external key (``Learner.session_id``), resolved WITHOUT Google.
_DEMO_BEARER_PREFIX = "demo:"

_TEACHER_ROLE = "teacher"


def demo_bearer_for(demo_session_id: str) -> str:
    """Build the demo teacher's Bearer credential from its external key (Slice TCH.B2).

    The single source of truth for the ``demo:`` scheme, so the route that issues the handle and
    ``current_teacher`` that consumes it can never drift on the format."""
    return f"{_DEMO_BEARER_PREFIX}{demo_session_id}"


def current_teacher(
    store: StoreDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthedLearner:
    """Resolve the authenticated TEACHER, or raise (Slice TCH.B2). Behavior matrix:

      - no Bearer credential                    → 401 (anonymous is not a teacher).
      - a ``demo:<id>`` handle for a seeded demo teacher → 200 (the one-click demo path; no
        Google verification — the handle is public by design).
      - a ``demo:<id>`` handle that resolves to no teacher row → 401 (nothing to authenticate).
      - a valid Google learner whose row is ``role="teacher"`` → 200 (the real-teacher path).
      - a valid Google learner who is a STUDENT → 403 (authenticated, not authorized).
      - an invalid/unconfigured Google token    → 401 (raised by ``current_learner`` first).

    The demo branch is handled here, BEFORE delegating, because a ``demo:`` token is not a Google
    ID token — passing it to ``current_learner`` would (correctly) 401 it as an invalid Google
    credential. Real teachers reuse the unchanged PL.3 ``current_learner`` seam (no second
    credential scheme). Role still never reaches the turn loop (invariant 8)."""
    token = _extract_bearer_token(authorization)
    if token is not None and token.startswith(_DEMO_BEARER_PREFIX):
        return _resolve_demo_teacher(store, token[len(_DEMO_BEARER_PREFIX) :])

    learner = current_learner(store, authorization)
    if learner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    if learner.role != _TEACHER_ROLE:
        # Authenticated, but not a teacher: 403 (not 401) — the credential is valid, the
        # authorization is not. The frontend uses this to keep a student off the teacher surface.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="teacher access required",
        )
    return learner


def _resolve_demo_teacher(store: StoreDep, demo_session_id: str) -> AuthedLearner:
    """Resolve a ``demo:<session_id>`` handle to its seeded demo teacher, or 401.

    No Google verification: the demo handle is a public, password-free credential (owner
    decision, TCH.B2). We require a persistence factory (the demo teacher is a real row seeded by
    ``/teacher/demo-login``) and that the resolved row actually carries ``role="teacher"`` — a
    handle that resolves to nothing, or to a non-teacher, is a 401 (there is no teacher to be)."""
    if store.session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="account persistence is unavailable",
        )
    with store.session_factory() as db:
        learner = repo.get_learner(db, demo_session_id)
        if learner is None or learner.role != _TEACHER_ROLE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid credentials",
            )
        return AuthedLearner(learner_id=learner.id, email=learner.email, role=learner.role)


CurrentTeacherDep = Annotated[AuthedLearner, Depends(current_teacher)]


__all__ = [
    "AuthedLearner",
    "CurrentLearnerDep",
    "CurrentTeacherDep",
    "RequireLearnerDep",
    "current_learner",
    "current_teacher",
    "demo_bearer_for",
    "require_learner",
]
