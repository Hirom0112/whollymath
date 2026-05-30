"""Tests for wiring the live between-problem adaptation into the turn loop (HR.B4 Beat 3).

The classifier / projection / streak helper are unit-tested elsewhere; here we pin the WIRING: the
default arm never carries an adaptation, and the streak/representation read reflects the session.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.app import create_app
from app.api.schemas import ActionType, SurfaceState, TurnRequest
from app.api.service import _streak_and_distinct_reps
from app.db.engine import create_all, create_session_factory
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_ROUTE = "combine"
_CORRECT = "7/12"  # the addition calibration (1/3 + 1/4)


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


def _answer(session_id: str, problem_id: str, answer: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.SUBMIT_ANSWER,
        submitted_answer=answer,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=4000,
        hint_used=False,
    )


def test_default_arm_never_carries_an_adaptation(app: FastAPI) -> None:
    store = app.state.session_store
    started = store.start(_ROUTE)  # proactive arm OFF
    response = store.process_turn(_answer(started.session_id, started.problem.problem_id, _CORRECT))
    assert response.adaptation is None


def test_streak_and_reps_read_the_session_history(app: FastAPI) -> None:
    store = app.state.session_store
    started = store.start(_ROUTE, proactive_enabled=True)
    sid = started.session_id

    live = store._sessions[sid]
    streak0, _ = _streak_and_distinct_reps(live.tutor)
    assert streak0 == 0  # nothing answered yet

    # One correct, unhinted answer → the streak advances by one.
    pid = started.problem.problem_id
    store.process_turn(_answer(sid, pid, _CORRECT))
    streak1, reps1 = _streak_and_distinct_reps(live.tutor)
    assert streak1 == 1
    assert reps1 >= 1
