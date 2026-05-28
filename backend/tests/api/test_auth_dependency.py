"""Contract tests for the Google-OIDC auth dependency + /me endpoint (Slice PL.3).

SECURITY-SENSITIVE, so the behavior matrix is pinned precisely. We NEVER hit Google's
network (CLAUDE.md §9): ``app.auth.google.verify_google_id_token`` — the seam the dependency
calls — is monkeypatched to map a sentinel token to a ``GoogleIdentity`` (or raise). The
production verifier (Google's official library) is exercised by ``tests/auth/``.

The auth dependency behavior matrix this asserts:

  - no Authorization header        → anonymous (the v1 session-id flow is UNCHANGED; /me 401s
                                     only because /me requires identity).
  - valid Bearer token             → the learner (sub mapped to a learner row, get-or-create
                                     idempotent: same sub twice → same learner row).
  - invalid Bearer token           → 401.
  - token present, GOOGLE_CLIENT_ID unset → 401 (auth not configured), but an ABSENT token is
                                     still anonymous (the anonymous flow is unaffected).

And /me itself: a valid token returns the persistent identity handle + the carried-forward
mastery summary (reusing the PL.1 mastery rows), proving "same login anywhere → same state".

Driven through the in-process ASGI client (httpx is not installed, see asgi_client). A real
DB-backed app is built so the sub→learner mapping and the mastery summary go through the
actual repository + persistence wiring.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.app import create_app
from app.auth.google import GoogleIdentity, InvalidIdTokenError
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.domain.knowledge_components import KnowledgeComponentId
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.api.asgi_client import get

_CLIENT_ID = "test-client.apps.googleusercontent.com"
_GOOD_TOKEN = "good.id.token"
_SUB = "google-sub-pl3"


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
    """A real app whose store is DB-backed, so sub→learner + mastery go through the repo."""
    application = create_app()
    application.state.session_store.session_factory = session_factory
    return application


@pytest.fixture(autouse=True)
def _configure_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth is CONFIGURED by default in these tests (a real client id is set)."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", _CLIENT_ID)


def _patch_verify_ok(monkeypatch: pytest.MonkeyPatch, identity: GoogleIdentity) -> None:
    """Map the sentinel good token → ``identity``; anything else → InvalidIdTokenError."""

    def _fake(token: str, *, client_id: str) -> GoogleIdentity:
        assert client_id == _CLIENT_ID
        if token == _GOOD_TOKEN:
            return identity
        raise InvalidIdTokenError("invalid Google ID token")

    monkeypatch.setattr("app.api.dependencies.verify_google_id_token", _fake)


def test_no_header_is_anonymous_me_401(app: FastAPI) -> None:
    """No Authorization header → anonymous; /me (which requires identity) returns 401."""
    status_code, _ = get(app, "/me")
    assert status_code == 401


def test_valid_bearer_returns_identity_and_mastery(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid Bearer token → identity handle + carried-forward mastery summary."""
    _patch_verify_ok(monkeypatch, GoogleIdentity(sub=_SUB, email="kid@example.com"))

    # Pre-seed mastery for the learner keyed by this sub — the "carried-forward" state.
    store = app.state.session_store
    with store.session_factory() as db:
        learner = repo.get_or_create_learner_by_google_sub(db, _SUB, email="kid@example.com")
        db.flush()
        repo.upsert_mastery_state(
            db,
            learner_id=learner.id,
            kc_id=KnowledgeComponentId.EQUIVALENCE.value,
            bkt_probability=0.92,
            attempt_count=5,
            hint_count=0,
            unscaffolded_correct_count=4,
            confirmed=True,
        )
        db.commit()

    status_code, body = get(app, "/me", headers={"authorization": f"Bearer {_GOOD_TOKEN}"})
    assert status_code == 200, body
    assert body["email"] == "kid@example.com"
    assert isinstance(body["learner_id"], int)
    # The mastery summary carries the persisted KC forward, with mastered = confirmed.
    summary = {m["kc_id"]: m for m in body["mastery"]}
    assert KnowledgeComponentId.EQUIVALENCE.value in summary
    assert summary[KnowledgeComponentId.EQUIVALENCE.value]["mastered"] is True
    assert summary[KnowledgeComponentId.EQUIVALENCE.value]["probability"] == pytest.approx(0.92)


def test_valid_bearer_get_or_create_is_idempotent(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same sub on two requests maps to the SAME learner row (no duplicate)."""
    _patch_verify_ok(monkeypatch, GoogleIdentity(sub=_SUB, email=None))
    headers = {"authorization": f"Bearer {_GOOD_TOKEN}"}

    s1, b1 = get(app, "/me", headers=headers)
    s2, b2 = get(app, "/me", headers=headers)
    assert s1 == 200 and s2 == 200
    assert b1["learner_id"] == b2["learner_id"]

    store = app.state.session_store
    with store.session_factory() as db:
        from app.db.models import Learner

        rows = db.query(Learner).filter_by(google_sub=_SUB).all()
        assert len(rows) == 1


def test_invalid_bearer_is_401(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """A token that fails verification → 401."""
    _patch_verify_ok(monkeypatch, GoogleIdentity(sub=_SUB, email=None))
    status_code, _ = get(app, "/me", headers={"authorization": "Bearer not.the.good.token"})
    assert status_code == 401


def test_token_present_but_client_id_unset_is_401(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GOOGLE_CLIENT_ID unset + a token present → 401 (auth not configured)."""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    # verify must never even be reached when unconfigured; make it explode if it is.
    monkeypatch.setattr(
        "app.api.dependencies.verify_google_id_token",
        lambda *a, **k: pytest.fail("verify must not run when GOOGLE_CLIENT_ID is unset"),
    )
    status_code, _ = get(app, "/me", headers={"authorization": f"Bearer {_GOOD_TOKEN}"})
    assert status_code == 401


def test_absent_token_unaffected_when_unconfigured(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With GOOGLE_CLIENT_ID unset, an ABSENT token is still anonymous (flow unaffected)."""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    # /me requires identity, so anonymous → 401 (not a 500); the anonymous turn flow elsewhere
    # is unaffected because no header means the dependency returns None.
    status_code, _ = get(app, "/me")
    assert status_code == 401


def test_malformed_authorization_header_is_anonymous(app: FastAPI) -> None:
    """A header that is not 'Bearer <token>' is treated as no credentials (anonymous)."""
    # No 'Bearer ' scheme → not a presented bearer token → anonymous → /me 401.
    status_code, _ = get(app, "/me", headers={"authorization": "Basic abc123"})
    assert status_code == 401
