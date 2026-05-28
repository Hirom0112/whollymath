"""Tests for the interaction-event repository functions (Slice PL.2).

The repository is the ONLY place DB queries live (CLAUDE.md §7; ARCHITECTURE.md §14
invariant 5): pure functions over a SQLAlchemy ORM ``Session``, no business logic, no
commit (the caller owns the unit of work). These tests pin the contract the event-ingest
service depends on:

  - ``persist_event`` writes one row, mapping every field (type, payload, both timestamps,
    the optional session/learner ids) onto the InteractionEvent columns.
  - nullable linkage: an event with no known session/learner still persists.
  - the portable JSON ``payload`` round-trips structured data (dict in, dict out) — proving
    the generic ``JSON`` column works on SQLite (and so on Postgres).
  - ``persist_events`` writes a batch and returns the count added.

Runs against an in-memory SQLite engine + ``create_all`` (the same pattern as the other
``tests/db/`` modules) — no Postgres, no new dependency (CLAUDE.md §8.7).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.db.models import InteractionEvent
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


def test_persist_event_maps_all_fields(session_factory: sessionmaker[OrmSession]) -> None:
    """persist_event writes every event column from the supplied values, including the FKs."""
    client_ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-ev")
        db.flush()
        session = repo.create_session(db, learner_id=learner.id)
        db.flush()
        repo.persist_event(
            db,
            session_row_id=session.id,
            learner_id=learner.id,
            event_type="numberline_drag",
            payload={"value": "3/4", "tick": 9},
            client_ts=client_ts,
        )
        db.commit()
        session_id = session.id
        learner_id = learner.id

    with session_factory() as db:
        events = db.query(InteractionEvent).all()
        assert len(events) == 1
        event = events[0]
        assert event.session_id == session_id
        assert event.learner_id == learner_id
        assert event.event_type == "numberline_drag"
        # The portable JSON column round-trips a structured dict (proving JSON, not a string).
        assert event.payload == {"value": "3/4", "tick": 9}
        # SQLite stores DateTime as naive text, so the tz is dropped on read-back (a test-engine
        # artifact the other DateTime columns share); compare the wall-clock fields, which prove
        # the value was persisted and re-read intact.
        assert event.client_ts is not None
        assert event.client_ts.replace(tzinfo=UTC) == client_ts
        # server_ts is always stamped by the Python-side default.
        assert event.server_ts is not None


def test_persist_event_allows_unknown_session_and_learner(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A lenient telemetry write with no known session/learner still records the event."""
    with session_factory() as db:
        repo.persist_event(
            db,
            session_row_id=None,
            learner_id=None,
            event_type="focus",
            payload={},
            client_ts=None,
        )
        db.commit()

    with session_factory() as db:
        events = db.query(InteractionEvent).all()
        assert len(events) == 1
        assert events[0].session_id is None
        assert events[0].learner_id is None
        assert events[0].event_type == "focus"
        assert events[0].payload == {}
        assert events[0].client_ts is None


def test_persist_events_batch_returns_count(session_factory: sessionmaker[OrmSession]) -> None:
    """persist_events writes the whole batch and returns the number of rows added."""
    batch = [
        repo.EventRow(event_type="problem_presented", payload={"problem_id": "p1"}, client_ts=None),
        repo.EventRow(event_type="answer_edit", payload={"text": "1/"}, client_ts=None),
        repo.EventRow(event_type="submit", payload={"text": "1/2"}, client_ts=None),
    ]
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-batch")
        db.flush()
        session = repo.create_session(db, learner_id=learner.id)
        db.flush()
        count = repo.persist_events(
            db, session_row_id=session.id, learner_id=learner.id, events=batch
        )
        db.commit()
        assert count == 3

    with session_factory() as db:
        events = db.query(InteractionEvent).order_by(InteractionEvent.id).all()
        assert [e.event_type for e in events] == ["problem_presented", "answer_edit", "submit"]
        assert all(e.session_id == session.id for e in events)


def test_persist_events_empty_batch_is_zero(session_factory: sessionmaker[OrmSession]) -> None:
    """An empty batch persists nothing and returns 0."""
    with session_factory() as db:
        count = repo.persist_events(db, session_row_id=None, learner_id=None, events=[])
        db.commit()
        assert count == 0
        assert db.query(InteractionEvent).count() == 0
