"""Tests for the ``POST /events`` behavioral-capture endpoint (Slice PL.2).

The hard invariant (ARCHITECTURE.md §14 invariant 7): telemetry never blocks a turn — event
capture is OFF the turn loop, the endpoint returns immediately (202), an unknown session is not
a 404, and a persistence failure never errors the client. These tests pin exactly that:

  - round-trip: a posted batch lands in ``interaction_event`` with the right type/payload/ts.
  - 202 + accepted count; an empty batch is fine (202, accepted=0).
  - LENIENCY: an unknown session_id still returns 202 (no 404); a factory whose commit raises
    still returns 202 (the failure is swallowed) — telemetry never errors the client.
  - INDEPENDENCE: posting events does not change a turn outcome; and structurally,
    ``app/events/ingest.py`` imports neither the turn-loop service nor the verifier/mastery
    (the chat-baseline-style import guard).
  - schema: a malformed event (missing event_type) → 422; an over-long batch → 422.

Runs against an in-memory SQLite engine (no Postgres, CLAUDE.md §8.7) and FastAPI's TestClient.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.routes import router
from app.api.service import SessionStore
from app.db.engine import create_all, create_session_factory
from app.db.models import InteractionEvent
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_ADDITION_ROUTE_KEY = "combine"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    """A shared in-memory SQLite engine + schema, as a session factory."""
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def _app(store: SessionStore) -> FastAPI:
    """A FastAPI app with the router mounted over the supplied store (no DB lifespan)."""
    app = FastAPI()
    app.state.session_store = store
    app.include_router(router)
    return app


def test_events_round_trip_persists_rows(session_factory: sessionmaker[OrmSession]) -> None:
    """A posted batch lands in interaction_event linked to the live session."""
    store = SessionStore(session_factory=session_factory)
    started = store.start(_ADDITION_ROUTE_KEY)
    client = TestClient(_app(store))

    resp = client.post(
        "/events",
        json={
            "session_id": started.session_id,
            "events": [
                {"event_type": "problem_presented", "payload": {"problem_id": "p1"}},
                {"event_type": "numberline_drag", "payload": {"value": "3/4"}},
            ],
        },
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 2}

    with session_factory() as db:
        rows = db.query(InteractionEvent).order_by(InteractionEvent.id).all()
        assert [r.event_type for r in rows] == ["problem_presented", "numberline_drag"]
        assert rows[0].payload == {"problem_id": "p1"}
        # Linked to the persisted session + learner (the live session knows its db row).
        assert all(r.session_id is not None for r in rows)
        assert all(r.learner_id is not None for r in rows)


def test_empty_batch_is_accepted(session_factory: sessionmaker[OrmSession]) -> None:
    """An empty batch returns 202 with accepted=0 and writes nothing."""
    store = SessionStore(session_factory=session_factory)
    started = store.start(_ADDITION_ROUTE_KEY)
    client = TestClient(_app(store))

    resp = client.post("/events", json={"session_id": started.session_id, "events": []})
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 0}
    with session_factory() as db:
        assert db.query(InteractionEvent).count() == 0


def test_unknown_session_id_still_202_not_404(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """LENIENCY: an unknown session_id is accepted (no 404) — telemetry is lenient."""
    store = SessionStore(session_factory=session_factory)
    client = TestClient(_app(store))

    resp = client.post(
        "/events",
        json={"session_id": "never-started", "events": [{"event_type": "focus"}]},
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 1}
    # Persisted with NULL session/learner FKs (we record what we can).
    with session_factory() as db:
        rows = db.query(InteractionEvent).all()
        assert len(rows) == 1
        assert rows[0].session_id is None
        assert rows[0].learner_id is None


def test_no_factory_returns_accepted_zero() -> None:
    """With no DB wired the endpoint still 202s, accepted=0 (the in-memory demo)."""
    store = SessionStore()  # no session_factory
    started = store.start(_ADDITION_ROUTE_KEY)
    client = TestClient(_app(store))

    resp = client.post(
        "/events",
        json={"session_id": started.session_id, "events": [{"event_type": "submit"}]},
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 0}


def test_commit_failure_still_returns_202(session_factory: sessionmaker[OrmSession]) -> None:
    """LENIENCY: a factory whose commit raises is swallowed — the client still gets 202."""

    class _BoomSession:
        def __init__(self, real: OrmSession) -> None:
            self._real = real

        def __getattr__(self, name: str) -> object:
            return getattr(self._real, name)

        def commit(self) -> None:
            raise RuntimeError("boom: simulated DB failure")

        def __enter__(self) -> _BoomSession:
            return self

        def __exit__(self, *exc: object) -> None:
            self._real.close()

    def boom_factory() -> _BoomSession:
        return _BoomSession(session_factory())

    store = SessionStore(session_factory=boom_factory)  # type: ignore[arg-type]
    started = store.start(_ADDITION_ROUTE_KEY)
    client = TestClient(_app(store))

    resp = client.post(
        "/events",
        json={"session_id": started.session_id, "events": [{"event_type": "submit"}]},
    )
    # The write failed and was swallowed, but the client is never told (invariant 7).
    assert resp.status_code == 202
    # accepted=0 because the swallowed failure means nothing was durably attempted.
    assert resp.json() == {"accepted": 0}


def test_malformed_event_missing_type_is_422(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """SCHEMA: an event missing the required event_type is rejected with 422."""
    store = SessionStore(session_factory=session_factory)
    started = store.start(_ADDITION_ROUTE_KEY)
    client = TestClient(_app(store))

    resp = client.post(
        "/events",
        json={"session_id": started.session_id, "events": [{"payload": {"x": 1}}]},
    )
    assert resp.status_code == 422


def test_over_long_batch_is_422(session_factory: sessionmaker[OrmSession]) -> None:
    """SCHEMA: a batch over the cap is rejected with 422 (abuse guard)."""
    store = SessionStore(session_factory=session_factory)
    started = store.start(_ADDITION_ROUTE_KEY)
    client = TestClient(_app(store))

    too_many = [{"event_type": "idle"} for _ in range(201)]
    resp = client.post("/events", json={"session_id": started.session_id, "events": too_many})
    assert resp.status_code == 422


def test_posting_events_does_not_change_turn_outcome(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """INDEPENDENCE: events between turns leave the turn outcome byte-identical."""
    from app.api.schemas import ActionType, SurfaceState, TurnRequest

    def turn(session_id: str, problem_id: str) -> TurnRequest:
        return TurnRequest(
            session_id=session_id,
            problem_id=problem_id,
            action=ActionType.SUBMIT_ANSWER,
            submitted_answer="7/12",
            surface_state=SurfaceState.SYMBOLIC_FOCUS,
            latency_ms=3000,
            hint_used=False,
        )

    # Pin the SAME session id in both walks: the problem seed is derived from the id (Fix A),
    # so an equivalence test must hold identity fixed to isolate the variable under test (the
    # interleaved /events POSTs), not the per-session problem variety.
    fixed_id = "equivsession00000000000000events"

    # Baseline: a plain in-memory walk with no events posted.
    plain = SessionStore()
    started_p = plain.start(_ADDITION_ROUTE_KEY, session_id=fixed_id)
    pid_p = started_p.problem.problem_id
    plain_responses = []
    for _ in range(3):
        r = plain.process_turn(turn(started_p.session_id, pid_p))
        plain_responses.append(r)
        assert r.next_problem is not None
        pid_p = r.next_problem.problem_id

    # Same walk, but interleave /events POSTs between turns.
    store = SessionStore(session_factory=session_factory)
    started = store.start(_ADDITION_ROUTE_KEY, session_id=fixed_id)
    client = TestClient(_app(store))
    pid = started.problem.problem_id
    interleaved_responses = []
    for _ in range(3):
        client.post(
            "/events",
            json={"session_id": started.session_id, "events": [{"event_type": "answer_edit"}]},
        )
        r = store.process_turn(turn(started.session_id, pid))
        interleaved_responses.append(r)
        assert r.next_problem is not None
        pid = r.next_problem.problem_id

    assert plain_responses == interleaved_responses


def test_ingest_module_imports_no_turn_loop_or_verifier() -> None:
    """STRUCTURAL guard: app/events/ingest.py never imports the turn loop, verifier, or mastery.

    Mirrors the chat-baseline import guard (tests/eval/test_chat_baseline.py): the capture path is
    defined by what it does NOT touch. It only records; it must not reach into process_turn, the
    SymPy verifier, the mastery model, or the policy (ARCHITECTURE.md §14 inv 7 + §8.1/§8.2)."""
    source = Path("app/events/ingest.py").read_text()
    assert "app.api.service" not in source
    assert "process_turn" not in source
    assert "app.domain.verifier" not in source
    assert "app.mastery" not in source
    assert "app.policy" not in source
