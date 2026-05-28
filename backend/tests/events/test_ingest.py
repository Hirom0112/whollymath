"""Tests for the behavioral-event ingest layer (Slice PL.2).

``app.events.ingest.ingest_events`` is the OFF-the-turn-loop persistence path (ARCHITECTURE.md
§14 invariant 7): it opens a DB session from a factory, writes the batch via the repository,
commits, and is BEST-EFFORT — any failure is swallowed and the function returns gracefully so
telemetry can never break the request that triggered it. These tests pin exactly that:

  - round-trip: a batch is persisted to ``interaction_event`` with the right type/payload.
  - returns the count attempted-persisted; an empty batch is fine (returns 0).
  - ``session_factory=None`` is a no-op returning 0 (the in-memory demo with no DB).
  - LENIENCY/tolerance: a factory whose commit raises is swallowed — the function returns
    gracefully (it never re-raises to the caller).

Runs against an in-memory SQLite engine + ``create_all`` (the ``tests/db`` pattern) — no
Postgres, no new dependency (CLAUDE.md §8.7).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.db.models import InteractionEvent
from app.db.repositories import EventRow
from app.events.ingest import ingest_events
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    """A fresh in-memory SQLite engine with the full schema, as a session factory."""
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def test_ingest_persists_batch_and_returns_count(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A batch is committed to interaction_event and the attempted count is returned."""
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-ingest")
        db.flush()
        session = repo.create_session(db, learner_id=learner.id)
        db.commit()
        session_row_id = session.id
        learner_id = learner.id

    events = [
        EventRow(event_type="problem_presented", payload={"problem_id": "p1"}),
        EventRow(event_type="numberline_drag", payload={"value": "3/4"}),
    ]
    count = ingest_events(
        session_factory,
        session_id="sess-ingest",
        events=events,
        session_row_id=session_row_id,
        learner_id=learner_id,
    )
    assert count == 2

    with session_factory() as db:
        rows = db.query(InteractionEvent).order_by(InteractionEvent.id).all()
        assert [r.event_type for r in rows] == ["problem_presented", "numberline_drag"]
        assert rows[0].payload == {"problem_id": "p1"}
        assert all(r.session_id == session_row_id for r in rows)


def test_ingest_empty_batch_returns_zero(session_factory: sessionmaker[OrmSession]) -> None:
    """An empty batch persists nothing and returns 0."""
    count = ingest_events(
        session_factory,
        session_id="sess-empty",
        events=[],
        session_row_id=None,
        learner_id=None,
    )
    assert count == 0
    with session_factory() as db:
        assert db.query(InteractionEvent).count() == 0


def test_ingest_no_factory_is_noop() -> None:
    """With session_factory=None the ingest is a no-op returning 0 (the no-DB demo)."""
    count = ingest_events(
        None,
        session_id="sess-x",
        events=[EventRow(event_type="focus")],
        session_row_id=None,
        learner_id=None,
    )
    assert count == 0


def test_ingest_swallows_commit_failure(session_factory: sessionmaker[OrmSession]) -> None:
    """A factory whose commit raises is swallowed — ingest returns gracefully, never re-raises."""

    class _BoomSession:
        """A stand-in ORM session that explodes on commit but is otherwise inert."""

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

    # Must NOT raise — the whole point of invariant 7 is that telemetry never errors the caller.
    count = ingest_events(
        boom_factory,  # type: ignore[arg-type]
        session_id="sess-boom",
        events=[EventRow(event_type="submit", payload={"text": "1/2"})],
        session_row_id=None,
        learner_id=None,
    )
    assert count == 0

    # And nothing was committed (the failed transaction left no rows).
    with session_factory() as db:
        assert db.query(InteractionEvent).count() == 0
