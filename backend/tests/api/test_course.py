"""Contract tests for GET /course — the course-product home (Slice CP.A.1).

``/course`` is on the authenticated path (like ``/me``): it returns the learner's learning path
— every KC as a node with a status derived from their persisted mastery + the prerequisite graph
+ retention. No real network (CLAUDE.md §9): the Google verifier seam is monkeypatched to map a
sentinel token to an identity, exactly as the /me tests do; an in-memory SQLite store holds the
mastery. These are HTTP-level contract tests through the real ASGI stack.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.app import create_app
from app.auth.google import GoogleIdentity, InvalidIdTokenError
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.domain.knowledge_components import KnowledgeComponentId as KCId
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.api.asgi_client import get

_CLIENT_ID = "test-client.apps.googleusercontent.com"
_GOOD_TOKEN = "good.id.token"
_SUB = "google-sub-course"
_AUTH = {"authorization": f"Bearer {_GOOD_TOKEN}"}


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    engine: Engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
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
    monkeypatch.setenv("GOOGLE_CLIENT_ID", _CLIENT_ID)


def _patch_verify_ok(monkeypatch: pytest.MonkeyPatch, identity: GoogleIdentity) -> None:
    def _fake(token: str, *, client_id: str) -> GoogleIdentity:
        assert client_id == _CLIENT_ID
        if token == _GOOD_TOKEN:
            return identity
        raise InvalidIdTokenError("invalid Google ID token")

    monkeypatch.setattr("app.api.dependencies.verify_google_id_token", _fake)


def _confirm_kc(app: FastAPI, kc: KCId) -> None:
    """Persist a fresh, confirmed mastery row for this test's learner."""
    store = app.state.session_store
    with store.session_factory() as db:
        learner = repo.get_or_create_learner_by_google_sub(db, _SUB, email=None)
        db.flush()
        repo.upsert_mastery_state(
            db,
            learner_id=learner.id,
            kc_id=kc.value,
            bkt_probability=0.9,
            attempt_count=4,
            hint_count=0,
            unscaffolded_correct_count=3,
            confirmed=True,
        )
        db.commit()


def test_anonymous_request_is_401(app: FastAPI) -> None:
    """No Authorization header → /course (which requires identity) returns 401."""
    status_code, _ = get(app, "/course")
    assert status_code == 401


def test_fresh_learner_gets_full_path_root_available(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A signed-in learner with no mastery yet → all 5 nodes; root available, the rest locked."""
    _patch_verify_ok(monkeypatch, GoogleIdentity(sub=_SUB, email=None))
    status_code, body = get(app, "/course", headers=_AUTH)
    assert status_code == 200, body
    nodes = {n["kc_id"]: n for n in body["nodes"]}
    # Every KC is a node, in teaching (spine) order with number-line first.
    assert [n["kc_id"] for n in body["nodes"]][0] == KCId.NUMBER_LINE_PLACEMENT.value
    assert set(nodes) == {kc.value for kc in KCId}
    assert nodes[KCId.NUMBER_LINE_PLACEMENT.value]["status"] == "available"
    assert nodes[KCId.EQUIVALENCE.value]["status"] == "locked"
    # A node carries display fields + prereq edges + a null probability when untouched.
    assert nodes[KCId.EQUIVALENCE.value]["skill_name"]
    assert nodes[KCId.EQUIVALENCE.value]["prerequisites"] == [KCId.NUMBER_LINE_PLACEMENT.value]
    assert nodes[KCId.NUMBER_LINE_PLACEMENT.value]["probability"] is None


def test_confirmed_skill_is_mastered_and_unlocks_next(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirming the root → it shows mastered (with its probability) and equivalence opens up."""
    _patch_verify_ok(monkeypatch, GoogleIdentity(sub=_SUB, email=None))
    _confirm_kc(app, KCId.NUMBER_LINE_PLACEMENT)

    status_code, body = get(app, "/course", headers=_AUTH)
    assert status_code == 200, body
    nodes = {n["kc_id"]: n for n in body["nodes"]}
    assert nodes[KCId.NUMBER_LINE_PLACEMENT.value]["status"] == "mastered"
    assert nodes[KCId.NUMBER_LINE_PLACEMENT.value]["probability"] == pytest.approx(0.9)
    assert nodes[KCId.EQUIVALENCE.value]["status"] == "available"
    assert nodes[KCId.COMMON_DENOMINATOR.value]["status"] == "locked"
