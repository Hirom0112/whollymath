"""Child-account HTTP routes: a parent manages children + a child logs in (Slice S3).

Thin handlers (CLAUDE.md §7): resolve the signing key + persistence, delegate to
``child_account_service``, map the service's typed errors to HTTP codes, and set the
session/CSRF cookies. No business logic, no SQL here — the service owns the unit of work.

Two surfaces share this router:

  - **parent-managed children** (``/parent/children...``): every route depends on
    ``CurrentParentDep`` (a live parent cookie) and every state-changing verb additionally
    depends on ``RequireCsrfDep`` (double-submit CSRF). Ownership/BOLA is enforced in the
    service via the parent-scoped repository lookup (OWASP API #1).
  - **independent child login** (``/child/login``): NO parent session — it establishes a
    child session from household email + username + PIN (school/shared device), with the
    online PIN-lockout and a single generic 401 for any credential failure (no enumeration).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.child_account_schemas import (
    ChildCredentialResponse,
    ChildLoginRequest,
    ChildSessionResponse,
    ChildSummary,
    CreateChildRequest,
    ResetPinRequest,
)
from app.api.child_account_service import (
    ChildLockedError,
    ChildNotFoundError,
    ChildSessionOutcome,
    InvalidChildCredentialsError,
    UsernameTakenError,
    child_login,
    create_child_account,
    delete_child,
    export_child_data,
    get_child_summary,
    list_children,
    open_child_session_for_parent,
    reset_child_pin,
    sign_out_child_everywhere,
)
from app.api.parent_session import (
    CurrentParentDep,
    RequireCsrfDep,
    set_session_cookies,
)
from app.api.rate_limit import rate_limit
from app.api.routes import StoreDep
from app.api.schemas import TeacherStudentView
from app.api.teacher_service import TeacherService
from app.auth.passwords import InvalidPinError
from app.auth.tokens import session_signing_key

child_account_router = APIRouter(tags=["child-accounts"])


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


def _client_ip(request: Request) -> str | None:
    """The caller's IP for the COPPA consent record, or ``None`` if the scope has no client."""
    return request.client.host if request.client is not None else None


def _apply_child_session(response: Response, outcome: ChildSessionOutcome) -> ChildSessionResponse:
    """Set the child session + CSRF cookies (switch the cookie to the child); return the body."""
    set_session_cookies(
        response,
        token=outcome.session.token,
        csrf_token=outcome.session.csrf_token,
        max_age=outcome.session.ttl,
    )
    return outcome.child


@child_account_router.post(
    "/parent/children",
    response_model=ChildCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_child(
    body: CreateChildRequest,
    parent: CurrentParentDep,
    store: StoreDep,
    request: Request,
    request_csrf: RequireCsrfDep,
) -> ChildCredentialResponse:
    """Create one child for the authenticated parent and stamp the COPPA consent."""
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            return create_child_account(
                db,
                parent_id=parent.learner_id,
                display_name=body.display_name,
                grade_level=body.grade_level,
                locale=body.locale,
                username=body.username,
                pin=body.pin,
                ip_address=_client_ip(request),
            )
        except InvalidPinError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except UsernameTakenError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="username already in use"
            ) from exc


@child_account_router.get("/parent/children", response_model=list[ChildSummary])
def list_children_route(parent: CurrentParentDep, store: StoreDep) -> list[ChildSummary]:
    """List the authenticated parent's children (no secrets)."""
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        return list_children(db, parent_id=parent.learner_id)


@child_account_router.get("/parent/children/{public_id}", response_model=ChildSummary)
def get_child(public_id: str, parent: CurrentParentDep, store: StoreDep) -> ChildSummary:
    """Return one of the parent's children. A foreign/unknown public_id is a 404 (BOLA)."""
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            return get_child_summary(db, parent_id=parent.learner_id, public_id=public_id)
        except ChildNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="child not found"
            ) from exc


@child_account_router.get(
    "/parent/children/{public_id}/progress", response_model=TeacherStudentView
)
def get_child_progress(
    public_id: str, parent: CurrentParentDep, store: StoreDep
) -> TeacherStudentView:
    """One child's full progress drill-in for the parent dashboard. 404 if not owned (BOLA).

    Reuses the teacher drill-in computation (``TeacherService.child`` → ``_student_view``) so the
    parent sees the SAME mastery evidence + named misconception, parent-scoped by ownership rather
    than roster. A child who hasn't practiced yet returns an honest just-getting-started view."""
    _require_persistence(store)
    assert store.session_factory is not None
    view = TeacherService(store.session_factory).child(parent.learner_id, public_id, _now())
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="child not found")
    return view


@child_account_router.get("/parent/children/{public_id}/export")
def export_child(public_id: str, parent: CurrentParentDep, store: StoreDep) -> dict[str, Any]:
    """Export everything stored about one of the parent's children (COPPA review right).

    A GET (no CSRF — it is a read). 404 if the child is not owned (BOLA).
    """
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            return export_child_data(db, parent_id=parent.learner_id, public_id=public_id)
        except ChildNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="child not found"
            ) from exc


@child_account_router.post(
    "/parent/children/{public_id}/reset-pin", status_code=status.HTTP_204_NO_CONTENT
)
def reset_pin(
    public_id: str,
    body: ResetPinRequest,
    parent: CurrentParentDep,
    store: StoreDep,
    request_csrf: RequireCsrfDep,
) -> Response:
    """Set a new PIN for one of the parent's children and clear its lockout. 404 if not owned."""
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            reset_child_pin(db, parent_id=parent.learner_id, public_id=public_id, pin=body.pin)
        except InvalidPinError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ChildNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="child not found"
            ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@child_account_router.delete("/parent/children/{public_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_child_route(
    public_id: str,
    parent: CurrentParentDep,
    store: StoreDep,
    request_csrf: RequireCsrfDep,
) -> Response:
    """Delete one of the parent's children (COPPA deletion right). 404 if not owned."""
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            delete_child(db, parent_id=parent.learner_id, public_id=public_id)
        except ChildNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="child not found"
            ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@child_account_router.post(
    "/parent/children/{public_id}/start-session", response_model=ChildSessionResponse
)
def start_child_session(
    public_id: str,
    parent: CurrentParentDep,
    store: StoreDep,
    response: Response,
    request_csrf: RequireCsrfDep,
) -> ChildSessionResponse:
    """Profile-pick at home: open a child session for the parent's own child (Netflix-style).

    No PIN — the parent is authenticated and owns the child. Setting the child cookie here
    REPLACES the parent's cookie; that switch is intended. 404 if the child is not owned.
    """
    key = _signing_key_or_503()
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            outcome = open_child_session_for_parent(
                db, parent_id=parent.learner_id, public_id=public_id, signing_key=key, now=_now()
            )
        except ChildNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="child not found"
            ) from exc
    return _apply_child_session(response, outcome)


@child_account_router.post(
    "/parent/children/{public_id}/sign-out-everywhere",
    status_code=status.HTTP_204_NO_CONTENT,
)
def sign_out_everywhere(
    public_id: str,
    parent: CurrentParentDep,
    store: StoreDep,
    request_csrf: RequireCsrfDep,
) -> Response:
    """Revoke every live session for one of the parent's children. 404 if not owned."""
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            sign_out_child_everywhere(db, parent_id=parent.learner_id, public_id=public_id)
        except ChildNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="child not found"
            ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@child_account_router.post(
    "/child/login",
    response_model=ChildSessionResponse,
    # Per-IP throttle on the independent child-login path; combined with the per-account
    # PIN lockout (10k keyspace) this bounds online guessing. WAF is the authoritative cap.
    dependencies=[Depends(rate_limit(max_hits=10, window_seconds=60.0, scope="child-login"))],
)
def child_login_route(
    body: ChildLoginRequest, store: StoreDep, response: Response
) -> ChildSessionResponse:
    """Independent child login (school/shared device): household email + username + PIN.

    Establishes a child session — NO parent session required. One generic 401 for any
    credential failure (no enumeration); 423 when the account's PIN-lockout window is open.
    """
    key = _signing_key_or_503()
    _require_persistence(store)
    assert store.session_factory is not None
    with store.session_factory() as db:
        try:
            outcome = child_login(
                db,
                username=body.username,
                pin=body.pin,
                signing_key=key,
                now=_now(),
            )
        except ChildLockedError as exc:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="too many attempts, try again later",
            ) from exc
        except InvalidChildCredentialsError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
            ) from exc
    return _apply_child_session(response, outcome)
