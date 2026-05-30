"""Contract tests for the mid-problem proactive nudge on /events (live loop Beat 1).

A DB-backed app: start a session (proactive arm on), stream events showing the learner stuck on the
in-progress problem, and assert /events returns an additive nudge — and that the default arm,
normal work, and a second batch on the same problem stay quiet.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.app import create_app
from app.db.engine import create_all, create_session_factory
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.api.asgi_client import post_json

_ROUTE = "combine"  # the addition route — its KC has a nudge bank entry
_KC = "KC_addition_unlike"


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


def _struggle_events(problem_id: str) -> list[dict[str, object]]:
    return [
        {"event_type": "problem_presented", "payload": {"problem_id": problem_id, "kc": _KC}},
        {"event_type": "idle", "payload": {"after_ms": 30000}},
        {"event_type": "idle", "payload": {"after_ms": 30000}},
    ]


def test_mid_problem_nudge_fires_on_sustained_struggle(app: FastAPI) -> None:
    store = app.state.session_store
    started = store.start(_ROUTE, proactive_enabled=True)
    code, body = post_json(
        app,
        "/events",
        {"session_id": started.session_id, "events": _struggle_events(started.problem.problem_id)},
    )
    assert code == 202, body
    assert body["nudge"] is not None
    assert body["nudge"]["text"].strip()


def test_default_arm_never_nudges(app: FastAPI) -> None:
    store = app.state.session_store
    started = store.start(_ROUTE)  # arm defaults OFF
    _, body = post_json(
        app,
        "/events",
        {"session_id": started.session_id, "events": _struggle_events(started.problem.problem_id)},
    )
    assert body["nudge"] is None


def test_normal_work_is_quiet(app: FastAPI) -> None:
    store = app.state.session_store
    started = store.start(_ROUTE, proactive_enabled=True)
    pid = started.problem.problem_id
    events = [
        {"event_type": "problem_presented", "payload": {"problem_id": pid, "kc": _KC}},
        {"event_type": "first_interaction", "payload": {"problem_id": pid, "elapsed_ms": 1500}},
        {"event_type": "answer_edit", "payload": {"problem_id": pid, "text": "1/"}},
    ]
    _, body = post_json(app, "/events", {"session_id": started.session_id, "events": events})
    assert body["nudge"] is None


def test_nudges_at_most_once_per_problem(app: FastAPI) -> None:
    store = app.state.session_store
    started = store.start(_ROUTE, proactive_enabled=True)
    payload = {
        "session_id": started.session_id,
        "events": _struggle_events(started.problem.problem_id),
    }
    first = post_json(app, "/events", payload)[1]
    second = post_json(app, "/events", payload)[1]
    assert first["nudge"] is not None
    assert second["nudge"] is None  # same problem → quiet on the second batch
