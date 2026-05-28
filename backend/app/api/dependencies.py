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
    stable persistence handle (``learner_id``) and the email display label cross this seam, so
    identity cannot leak into the turn decision (invariant 8)."""

    learner_id: int
    email: str | None


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
        return AuthedLearner(learner_id=learner.id, email=learner.email)


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


__all__ = [
    "AuthedLearner",
    "CurrentLearnerDep",
    "RequireLearnerDep",
    "current_learner",
    "require_learner",
]
