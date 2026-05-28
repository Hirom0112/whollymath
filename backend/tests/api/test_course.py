"""Contract tests for GET /course — the course-product home (Slices CP.A.1, CP.A.2).

``/course`` serves the learning path — every KC as a node with a status derived from mastery +
the prerequisite graph + retention — for BOTH kinds of learner:

  - a SIGNED-IN learner (valid Bearer token) → from their persisted mastery;
  - an ANONYMOUS demo learner (just a ``session_id``) → from their in-memory session;
  - a brand-new visitor (neither) → the fresh default path (NOT a 401).

No real network (CLAUDE.md §9): the Google verifier seam is monkeypatched to map a sentinel
token to an identity, exactly as the /me tests do; an in-memory SQLite store holds the persisted
mastery, and the demo path uses the in-memory session store. HTTP-level tests through the real
ASGI stack.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from app.api.app import create_app
from app.api.schemas import ActionType, StartSessionResponse, SurfaceState
from app.auth.google import GoogleIdentity, InvalidIdTokenError
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.domain.knowledge_components import KnowledgeComponentId as KCId
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.api.asgi_client import get, post_json

# The addition ("combine") route's Turn-1 calibration is "1/3 + 1/4 = ?", SymPy-correct 7/12.
_ADDITION_ROUTE_KEY = "combine"
_ADDITION_CORRECT_ANSWER = "7/12"

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


def test_anonymous_no_session_gets_fresh_default_map(app: FastAPI) -> None:
    """A brand-new visitor (no token, no session) gets the fresh default path — NOT a 401."""
    status_code, body = get(app, "/course")
    assert status_code == 200, body
    nodes = {n["kc_id"]: n for n in body["nodes"]}
    assert set(nodes) == {kc.value for kc in KCId}
    assert nodes[KCId.NUMBER_LINE_PLACEMENT.value]["status"] == "available"
    assert nodes[KCId.EQUIVALENCE.value]["status"] == "locked"


def test_demo_session_map_reflects_in_session_progress(app: FastAPI) -> None:
    """An anonymous demo learner's map is built from their session: a touched KC shows in_progress.

    Start an addition session and answer its calibration correctly, then read /course with that
    session_id — the addition KC, untouched it would be 'locked', now shows 'in_progress' (the
    rollup of the live session's history, not persisted rows).
    """
    _, started_body = post_json(app, "/session", {"route_key": _ADDITION_ROUTE_KEY})
    started = StartSessionResponse.model_validate(started_body)
    turn: dict[str, Any] = {
        "session_id": started.session_id,
        "problem_id": started.problem.problem_id,
        "action": ActionType.SUBMIT_ANSWER.value,
        "submitted_answer": _ADDITION_CORRECT_ANSWER,
        "surface_state": SurfaceState.SYMBOLIC_FOCUS.value,
        "latency_ms": 4200,
        "hint_used": False,
    }
    turn_status, _ = post_json(app, "/turn", turn)
    assert turn_status == 200

    status_code, body = get(app, f"/course?session_id={started.session_id}")
    assert status_code == 200, body
    statuses = [n["status"] for n in body["nodes"]]
    assert "in_progress" in statuses


def test_unknown_session_id_falls_back_to_default_map(app: FastAPI) -> None:
    """An unknown session_id is not an error — it yields the fresh default path."""
    status_code, body = get(app, "/course?session_id=never-started")
    assert status_code == 200, body
    nodes = {n["kc_id"]: n for n in body["nodes"]}
    assert nodes[KCId.NUMBER_LINE_PLACEMENT.value]["status"] == "available"


def test_bad_token_still_401(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """A *bad* Bearer token is still rejected (optional auth only excuses an ABSENT token)."""
    _patch_verify_ok(monkeypatch, GoogleIdentity(sub=_SUB, email=None))
    status_code, _ = get(app, "/course", headers={"authorization": "Bearer not.the.good.token"})
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
