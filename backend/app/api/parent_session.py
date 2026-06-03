"""Cookie-borne parent/child session: issuing, reading, and the auth dependencies (S3).

The HTTP seam between the pure auth primitives (``app.auth.tokens`` / ``csrf``) and a
request. Per the owner decision (2026-06-03) sessions ride in an HttpOnly cookie, not a
Bearer header, so the token is unreachable by JavaScript (XSS-resistant), and a readable
CSRF cookie is the double-submit partner for state-changing routes.

This module:
  - sets/clears the session cookie (HttpOnly, Secure, SameSite=Lax) + the readable CSRF
    cookie, from one place so flags cannot drift;
  - resolves ``current_parent`` / ``current_child`` from the cookie: decode the JWT, then
    confirm the matching ``AuthSession`` row is still live (revocation is real — a
    logged-out or killed session is refused even with a valid signature);
  - enforces CSRF on unsafe verbs.

Layering: it lives in ``app/api/`` (it touches FastAPI Request/Response and the DB via the
store) and reduces identity to a small handle (invariant 8 — identity gates the surface,
never the turn loop).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status

from app.api.routes import StoreDep
from app.auth import csrf
from app.auth.tokens import (
    CHILD_KIND,
    PARENT_KIND,
    decode_session_token,
    session_signing_key,
)
from app.db import repositories as repo
from app.db.models import Learner

# The HttpOnly session cookie carrying the JWT, and the session lifetimes. A parent
# session is longer-lived (a dashboard the adult comes back to); a child session is
# shorter, since a child often uses a shared/school device (owner decision 2026-06-03).
# Server-side revocation (AuthSession) means a moderate TTL is safe — a stolen cookie's
# window is bounded and a parent can kill it early.
SESSION_COOKIE_NAME = "wm_session"
PARENT_SESSION_TTL = timedelta(hours=12)
CHILD_SESSION_TTL = timedelta(hours=2)

_PARENT_ROLE = "parent"


def _now() -> datetime:
    return datetime.now(UTC)


def _cookie_secure() -> bool:
    """Whether to set the Secure flag. True by default (prod is HTTPS); a dev/test over
    plain http sets ``SESSION_COOKIE_SECURE=false`` so the browser will send it back."""
    return os.environ.get("SESSION_COOKIE_SECURE", "true").strip().lower() != "false"


def set_session_cookies(
    response: Response, *, token: str, csrf_token: str, max_age: timedelta
) -> None:
    """Set the HttpOnly session cookie + the readable CSRF cookie with aligned lifetime."""
    secure = _cookie_secure()
    max_age_s = int(max_age.total_seconds())
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=max_age_s,
        httponly=True,  # JS cannot read it → XSS cannot exfiltrate the session
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        csrf.CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age_s,
        httponly=False,  # the SPA must read this to echo it in the X-CSRF-Token header
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    """Delete both cookies (logout) — same path so the browser actually drops them."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(csrf.CSRF_COOKIE_NAME, path="/")


@dataclass(frozen=True)
class AuthedParent:
    """The minimal authenticated parent carried downstream (mirrors AuthedLearner)."""

    learner_id: int
    email: str | None
    email_verified: bool


@dataclass(frozen=True)
class AuthedChild:
    """The minimal authenticated child (a learner whose session kind is 'child')."""

    learner_id: int
    display_name: str | None


def _decode_active_session(store: StoreDep, request: Request, *, expected_kind: str) -> Learner:
    """Shared resolve: cookie → verified JWT (of the expected kind) → LIVE AuthSession → Learner.

    Raises 401 for any missing/invalid/revoked/expired session, 403 if the session is the
    wrong kind (e.g. a child cookie hitting a parent route), 503 if signing/persistence is
    not configured. Returns the attached Learner row (caller maps to its handle).
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )

    key = session_signing_key()
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="sessions are not configured"
        )

    claims = decode_session_token(token, secret=key, now=_now())
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    if claims.kind != expected_kind:
        # A valid session of the WRONG kind: authenticated, not authorized for this surface.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="wrong session type")

    if store.session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="account persistence is unavailable",
        )

    with store.session_factory() as db:
        live = repo.get_active_auth_session(db, claims.jti, _now())
        if live is None:  # revoked or expired server-side, even if the JWT still verifies
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
        learner = db.get(Learner, claims.learner_id)
        if learner is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
        # Detach the fields we need before the session closes.
        db.expunge(learner)
        return learner


def current_parent(store: StoreDep, request: Request) -> AuthedParent:
    """Resolve the authenticated PARENT from the session cookie, or raise."""
    learner = _decode_active_session(store, request, expected_kind=PARENT_KIND)
    if learner.role != _PARENT_ROLE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    return AuthedParent(
        learner_id=learner.id, email=learner.email, email_verified=learner.email_verified
    )


def current_child(store: StoreDep, request: Request) -> AuthedChild:
    """Resolve the authenticated CHILD from the session cookie, or raise."""
    learner = _decode_active_session(store, request, expected_kind=CHILD_KIND)
    return AuthedChild(learner_id=learner.id, display_name=learner.display_name)


def require_csrf(request: Request) -> None:
    """Enforce the double-submit CSRF check on a state-changing request, or 403.

    Compares the readable CSRF cookie against the ``X-CSRF-Token`` header. Used as a
    dependency on unsafe verbs (POST/PATCH/DELETE) for the cookie-authenticated surface.
    """
    cookie_token = request.cookies.get(csrf.CSRF_COOKIE_NAME)
    header_token = request.headers.get(csrf.CSRF_HEADER_NAME)
    if not csrf.verify_csrf(cookie_token=cookie_token, header_token=header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF check failed")


CurrentParentDep = Annotated[AuthedParent, Depends(current_parent)]
CurrentChildDep = Annotated[AuthedChild, Depends(current_child)]
RequireCsrfDep = Annotated[None, Depends(require_csrf)]
