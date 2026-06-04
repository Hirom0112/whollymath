"""Parent-auth HTTP routes: signup / login / logout / me / verify-email (Slice S3).

Thin handlers (CLAUDE.md §7): validate via Pydantic, resolve the session signing key +
persistence, delegate to ``parent_auth_service``, map named errors to HTTP codes, and
set/clear the session + CSRF cookies. The session itself rides in an HttpOnly cookie
(owner decision 2026-06-03), so these endpoints never hand a token back in the body.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.parent_auth_schemas import (
    GoogleParentRequest,
    ParentLoginRequest,
    ParentMeResponse,
    ParentSignupRequest,
)
from app.api.parent_auth_service import (
    EmailTakenError,
    GoogleNotConfiguredError,
    InvalidCredentialsError,
    google_login_parent,
    login_parent,
    signup_parent,
    verify_parent_email,
)
from app.api.parent_session import (
    SESSION_COOKIE_NAME,
    CurrentParentDep,
    RequireCsrfDep,
    clear_session_cookies,
    set_session_cookies,
)
from app.api.rate_limit import rate_limit
from app.api.routes import StoreDep
from app.auth.passwords import WeakPasswordError
from app.auth.tokens import decode_session_token, session_signing_key
from app.db import repositories as repo
from app.notifications.email_sender import EmailSender, default_email_sender

parent_auth_router = APIRouter(prefix="/parent", tags=["parent-auth"])


def get_email_sender() -> EmailSender:
    """Inject the configured email sender (SES, or the logging fallback). Overridable in tests."""
    return default_email_sender()


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]


def _now() -> datetime:
    return datetime.now(UTC)


def _signing_key_or_503() -> str:
    key = session_signing_key()
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="sessions are not configured"
        )
    return key


def _require_persistence(store: StoreDep) -> None:
    if store.session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="account persistence is unavailable",
        )


def _verify_base_url() -> str:
    """The clickable verification link base — the public API origin + the verify path."""
    base = os.environ.get("PUBLIC_API_BASE_URL", "").rstrip("/")
    return f"{base}/parent/verify-email"


@parent_auth_router.post(
    "/signup",
    response_model=ParentMeResponse,
    status_code=status.HTTP_201_CREATED,
    # Throttle account creation per-IP (anti-abuse); ALB/WAF is the authoritative backstop.
    dependencies=[Depends(rate_limit(max_hits=5, window_seconds=60.0, scope="parent-signup"))],
)
def signup(
    body: ParentSignupRequest,
    store: StoreDep,
    response: Response,
    email_sender: EmailSenderDep,
) -> ParentMeResponse:
    """Create an email/password parent, open a session (cookies), send the verify email."""
    key = _signing_key_or_503()
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            outcome = signup_parent(
                db,
                email=body.email,
                password=body.password,
                signing_key=key,
                now=_now(),
                email_sender=email_sender,
                verify_base_url=_verify_base_url(),
            )
        except WeakPasswordError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except EmailTakenError as exc:
            # Generic-ish: an account exists. (Signup necessarily reveals existence; we keep
            # the message neutral and do not confirm anything else about it.)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="account already exists"
            ) from exc
    set_session_cookies(
        response,
        token=outcome.session.token,
        csrf_token=outcome.session.csrf_token,
        max_age=outcome.session.ttl,
    )
    return outcome.me


@parent_auth_router.post(
    "/login",
    response_model=ParentMeResponse,
    # Throttle login per-IP against credential stuffing (defense-in-depth atop the generic
    # 401 + timing equalization); the WAF rate rule on the true client IP is the real cap.
    dependencies=[Depends(rate_limit(max_hits=10, window_seconds=60.0, scope="parent-login"))],
)
def login(body: ParentLoginRequest, store: StoreDep, response: Response) -> ParentMeResponse:
    """Authenticate an email/password parent and open a session (cookies)."""
    key = _signing_key_or_503()
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            outcome = login_parent(
                db, email=body.email, password=body.password, signing_key=key, now=_now()
            )
        except InvalidCredentialsError as exc:
            # ONE generic 401 for no-such-parent and wrong-password (no enumeration).
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
            ) from exc
    set_session_cookies(
        response,
        token=outcome.session.token,
        csrf_token=outcome.session.csrf_token,
        max_age=outcome.session.ttl,
    )
    return outcome.me


@parent_auth_router.post(
    "/google",
    response_model=ParentMeResponse,
    dependencies=[Depends(rate_limit(max_hits=10, window_seconds=60.0, scope="parent-google"))],
)
def google_login(
    body: GoogleParentRequest, store: StoreDep, response: Response
) -> ParentMeResponse:
    """Sign a parent in with a Google ID token and open a session (cookies)."""
    key = _signing_key_or_503()
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            outcome = google_login_parent(db, id_token=body.id_token, signing_key=key, now=_now())
        except GoogleNotConfiguredError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="google sign-in is not configured",
            ) from exc
        except InvalidCredentialsError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
            ) from exc
    set_session_cookies(
        response,
        token=outcome.session.token,
        csrf_token=outcome.session.csrf_token,
        max_age=outcome.session.ttl,
    )
    return outcome.me


@parent_auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, response: Response, store: StoreDep, request_csrf: RequireCsrfDep
) -> Response:
    """Revoke the current session server-side and clear the cookies (CSRF-protected).

    Reads the session cookie, decodes it best-effort, revokes the matching AuthSession by
    jti (so the token is dead even if it leaked), and clears both cookies. Always succeeds
    from the client's view — an already-absent/invalid session just clears the cookies.
    """
    key = session_signing_key()
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if key is not None and token and store.session_factory is not None:
        claims = decode_session_token(token, secret=key, now=_now())
        if claims is not None:
            with store.session_factory() as db:
                repo.revoke_auth_session(db, claims.jti, _now())
                db.commit()
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@parent_auth_router.get("/me", response_model=ParentMeResponse)
def me(parent: CurrentParentDep) -> ParentMeResponse:
    """Return the authenticated parent's profile (401 if no live session)."""
    return ParentMeResponse(email=parent.email, email_verified=parent.email_verified)


@parent_auth_router.get("/verify-email")
def verify_email(token: str, store: StoreDep) -> dict[str, str]:
    """Mark the parent's email verified from a clicked verification link."""
    key = _signing_key_or_503()
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        ok = verify_parent_email(db, token=token, signing_key=key, now=_now())
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired verification link"
        )
    return {"status": "verified"}
