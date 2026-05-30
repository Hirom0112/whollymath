"""Contract tests for the teacher-auth seam: current_teacher + demo-login (Slice TCH.B2).

The teacher layer reuses the PL.3 Google-OIDC seam (``current_learner``) and ``Learner.role``
rather than inventing a second credential scheme (owner decision, lean scope). Two ways to be a
teacher:

  - a real Google-signed-in learner whose row has ``role == "teacher"`` (the Bearer-Google path,
    monkeypatched here exactly as ``test_auth_dependency`` does — we never hit Google's network);
  - the one-click, password-free DEMO teacher: ``POST /teacher/demo-login`` seeds/returns a demo
    teacher and a NON-secret handle (``token = "demo:<session_id>"``) the frontend echoes back as
    ``Authorization: Bearer demo:<session_id>``. The handle is public BY DESIGN — it is a free
    demo, not an account.

The ``current_teacher`` behavior matrix this pins (proved through ``GET /teacher/me``):

  - no Authorization header        → 401 (anonymous cannot be a teacher).
  - a STUDENT (role != teacher)    → 403 (authenticated, but not authorized for the teacher API).
  - a TEACHER (Google or demo)     → 200.
  - an invalid Google token        → 401 (current_learner rejects it before role is even checked).
  - a demo token for an unknown/ non-teacher row → 401 (nothing to resolve).

Identity (including role) still never reaches the turn loop — role only gates which API surface a
request may use (ARCHITECTURE.md §14 invariant 8; Learner.role docstring).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.app import create_app
from app.auth.google import GoogleIdentity, InvalidIdTokenError
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.db.models import Learner
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.api.asgi_client import get, post_json

_CLIENT_ID = "test-client.apps.googleusercontent.com"
_GOOD_TOKEN = "good.id.token"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def app(session_factory: sessionmaker[OrmSession]) -> FastAPI:
    application = create_app()
    application.state.session_store.session_factory = session_factory
    return application


@pytest.fixture(autouse=True)
def _configure_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth is CONFIGURED by default (a real client id is set), mirroring test_auth_dependency."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", _CLIENT_ID)


def _patch_verify_ok(monkeypatch: pytest.MonkeyPatch, identity: GoogleIdentity) -> None:
    """Map the sentinel good token → ``identity``; anything else → InvalidIdTokenError."""

    def _fake(token: str, *, client_id: str) -> GoogleIdentity:
        assert client_id == _CLIENT_ID
        if token == _GOOD_TOKEN:
            return identity
        raise InvalidIdTokenError("invalid Google ID token")

    monkeypatch.setattr("app.api.dependencies.verify_google_id_token", _fake)


# ---- POST /teacher/demo-login -------------------------------------------------------------


def test_demo_login_returns_teacher_handle(app: FastAPI) -> None:
    """demo-login seeds a teacher and returns a usable handle: role=teacher + a 'demo:' token."""
    status_code, body = post_json(app, "/teacher/demo-login", {})
    assert status_code == 200, body
    assert body["role"] == "teacher"
    assert isinstance(body["learner_id"], int)
    assert body["email"]  # a display label is present
    assert body["token"].startswith("demo:")


def test_demo_login_is_idempotent(app: FastAPI) -> None:
    """Clicking the demo button twice maps to the SAME teacher row — no duplicate learners."""
    _, b1 = post_json(app, "/teacher/demo-login", {})
    _, b2 = post_json(app, "/teacher/demo-login", {})
    assert b1["learner_id"] == b2["learner_id"]

    store = app.state.session_store
    with store.session_factory() as db:
        teachers = db.query(Learner).filter_by(role="teacher").all()
        assert len(teachers) == 1


# ---- GET /teacher/me (protected by current_teacher) ---------------------------------------


def test_teacher_me_anonymous_is_401(app: FastAPI) -> None:
    """No Authorization header → 401: an anonymous request is not a teacher."""
    status_code, _ = get(app, "/teacher/me")
    assert status_code == 401


def test_teacher_me_with_demo_token_is_200(app: FastAPI) -> None:
    """The handle from demo-login authenticates the demo teacher to the teacher API."""
    _, login = post_json(app, "/teacher/demo-login", {})
    headers = {"authorization": f"Bearer {login['token']}"}
    status_code, body = get(app, "/teacher/me", headers=headers)
    assert status_code == 200, body
    assert body["role"] == "teacher"
    assert body["learner_id"] == login["learner_id"]


def test_teacher_me_student_is_403(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid Google learner who is a STUDENT (default role) → 403, not 401: authenticated but
    not authorized for the teacher surface."""
    _patch_verify_ok(monkeypatch, GoogleIdentity(sub="student-sub", email="kid@example.com"))
    status_code, _ = get(app, "/teacher/me", headers={"authorization": f"Bearer {_GOOD_TOKEN}"})
    assert status_code == 403


def test_teacher_me_google_teacher_is_200(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Google learner whose row is role=teacher → 200 (the real-teacher path, no demo token)."""
    _patch_verify_ok(monkeypatch, GoogleIdentity(sub="teacher-sub", email="ms.frizzle@example.com"))
    headers = {"authorization": f"Bearer {_GOOD_TOKEN}"}

    # First request creates the learner (default role=student); promote them to teacher, then the
    # second request should be authorized.
    get(app, "/teacher/me", headers=headers)
    store = app.state.session_store
    with store.session_factory() as db:
        learner = db.query(Learner).filter_by(google_sub="teacher-sub").one()
        learner.role = "teacher"
        db.commit()

    status_code, body = get(app, "/teacher/me", headers=headers)
    assert status_code == 200, body
    assert body["role"] == "teacher"


def test_teacher_me_invalid_google_token_is_401(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid (non-demo) Bearer token is rejected by the Google seam before role is checked."""
    _patch_verify_ok(monkeypatch, GoogleIdentity(sub="x", email=None))
    status_code, _ = get(app, "/teacher/me", headers={"authorization": "Bearer not.the.good.token"})
    assert status_code == 401


def test_teacher_me_unknown_demo_token_is_401(app: FastAPI) -> None:
    """A 'demo:' token that resolves to no seeded teacher → 401 (nothing to authenticate)."""
    status_code, _ = get(app, "/teacher/me", headers={"authorization": "Bearer demo:ghost-teacher"})
    assert status_code == 401


def test_demo_login_seeded_row_is_only_teacher_via_repo(app: FastAPI) -> None:
    """The demo teacher is reachable by the repo's teacher-keyed queries (role really persisted)."""
    _, login = post_json(app, "/teacher/demo-login", {})
    store = app.state.session_store
    with store.session_factory() as db:
        teacher = repo.get_learner(db, repo.DEMO_TEACHER_SESSION_ID)
        assert teacher is not None
        assert teacher.id == login["learner_id"]
        assert teacher.role == "teacher"
