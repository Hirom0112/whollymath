"""Tests for the PL.4 event-loading repository queries (Slice PL.4).

``load_events_for_session`` / ``load_events_for_learner`` are the read the offline v2 derivation
pipeline consumes. They are pure queries (CLAUDE.md §7; ARCHITECTURE.md §14 invariant 5) that
return a learner's / session's ``InteractionEvent`` rows in chronological order, the order the
episode segmentation depends on. These tests pin:

  - per-session loading returns only that session's events, ordered by (server_ts, id);
  - per-learner loading spans the learner's sessions, ordered the same way;
  - the round-trip preserves the open-JSON payload (dict in, dict out) so the derivation reads
    real payload keys (elapsed_ms, latency_ms, kc) back intact;
  - an end-to-end persist → load → derive_v2_features over real-vocabulary events produces a
    proxy-free feature row (the offline pipeline runs against persisted rows).

Runs against an in-memory SQLite engine (the same pattern as the other ``tests/db/`` modules).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.helpneed.events_features import build_episodes, derive_v2_features
from app.helpneed.features import KC_ORDER
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

KC_VALUE = KC_ORDER[0].value  # any catalog KC; derivation only needs a recognized string


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


def _ts(seconds: int) -> datetime:
    """A deterministic server timestamp offset, so ordering is unambiguous in the test."""
    return datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=seconds)


def test_load_events_for_session_returns_only_that_session_in_order(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The per-session query returns that session's events, chronologically, and no others."""
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-load")
        db.flush()
        s1 = repo.create_session(db, learner_id=learner.id)
        s2 = repo.create_session(db, learner_id=learner.id)
        db.flush()
        # Persist out of order; the query must re-order by server_ts.
        e_late = repo.persist_event(
            db,
            session_row_id=s1.id,
            learner_id=learner.id,
            event_type="submit",
            payload={"latency_ms": 3000},
            client_ts=None,
        )
        e_early = repo.persist_event(
            db,
            session_row_id=s1.id,
            learner_id=learner.id,
            event_type="problem_presented",
            payload={"kc": KC_VALUE},
            client_ts=None,
        )
        # An event on a DIFFERENT session must not leak in.
        repo.persist_event(
            db,
            session_row_id=s2.id,
            learner_id=learner.id,
            event_type="hint_request",
            payload={},
            client_ts=None,
        )
        db.flush()
        # Force the intended chronological order (persist order was reversed).
        e_early.server_ts = _ts(0)
        e_late.server_ts = _ts(1)
        db.commit()
        s1_id = s1.id

    with session_factory() as db:
        events = repo.load_events_for_session(db, s1_id)
        assert [e.event_type for e in events] == ["problem_presented", "submit"]
        # open-JSON payload round-trips intact
        assert events[0].payload == {"kc": KC_VALUE}
        assert events[1].payload == {"latency_ms": 3000}


def test_load_events_for_learner_spans_sessions_in_order(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The per-learner query spans all the learner's sessions, ordered by (server_ts, id)."""
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-learner")
        other = repo.get_or_create_learner(db, "sess-other")
        db.flush()
        s1 = repo.create_session(db, learner_id=learner.id)
        s2 = repo.create_session(db, learner_id=learner.id)
        db.flush()
        a = repo.persist_event(
            db,
            session_row_id=s1.id,
            learner_id=learner.id,
            event_type="problem_presented",
            payload={"kc": KC_VALUE},
            client_ts=None,
        )
        b = repo.persist_event(
            db,
            session_row_id=s2.id,
            learner_id=learner.id,
            event_type="submit",
            payload={"latency_ms": 1000},
            client_ts=None,
        )
        # A different learner's event must not appear.
        repo.persist_event(
            db,
            session_row_id=None,
            learner_id=other.id,
            event_type="focus",
            payload={},
            client_ts=None,
        )
        db.flush()
        a.server_ts = _ts(0)
        b.server_ts = _ts(5)
        db.commit()
        learner_id = learner.id

    with session_factory() as db:
        events = repo.load_events_for_learner(db, learner_id)
        assert [e.event_type for e in events] == ["problem_presented", "submit"]


def test_persist_then_load_then_derive_v2_features_end_to_end(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A real-vocabulary stream persisted, loaded, and derived yields a proxy-free feature row.

    Two problem episodes: the first a give-up (3 hint requests) with two answer edits; the second
    a clean single submit. The derived row for the SECOND episode must reflect the first's REAL
    signals — attempts mean from real submit counts, give-up rate from the real escalation — not
    the v1 live proxies. This proves the offline pipeline runs against persisted PL.2 rows.
    """
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-e2e")
        db.flush()
        session = repo.create_session(db, learner_id=learner.id)
        db.flush()
        # Episode 1: a give-up — 2 edits, 3 hint requests, 1 submit.
        stream: list[tuple[str, dict[str, object]]] = [
            ("problem_presented", {"kc": KC_VALUE, "problem_id": "p1"}),
            ("first_interaction", {"elapsed_ms": 1500, "kind": "fraction"}),
            ("answer_edit", {"text": "1/"}),
            ("answer_edit", {"text": "1/3"}),
            ("hint_request", {"elapsed_ms": 4000}),
            ("hint_request", {"elapsed_ms": 8000}),
            ("hint_request", {"elapsed_ms": 12000}),
            ("submit", {"latency_ms": 15000, "hint_used": True}),
            # Episode 2: clean single submit.
            ("problem_presented", {"kc": KC_VALUE, "problem_id": "p2"}),
            ("first_interaction", {"elapsed_ms": 900, "kind": "fraction"}),
            ("submit", {"latency_ms": 3000, "hint_used": False}),
        ]
        for i, (etype, payload) in enumerate(stream):
            ev = repo.persist_event(
                db,
                session_row_id=session.id,
                learner_id=learner.id,
                event_type=etype,
                payload=payload,
                client_ts=None,
            )
            db.flush()
            ev.server_ts = _ts(i)  # strict chronological order
        db.commit()
        session_id = session.id

    with session_factory() as db:
        events = repo.load_events_for_session(db, session_id)
        episodes = build_episodes(events)
        assert len(episodes) == 2
        # Episode 1's derived signals are REAL, not proxied.
        assert episodes[0].signals.attempts == 1
        assert episodes[0].signals.answer_revisions == 2
        assert episodes[0].signals.hint_requests == 3
        assert episodes[0].signals.requested_answer is True
        assert episodes[0].signals.time_to_first_interaction_ms == 1500

        rows = derive_v2_features(episodes)
        second = rows[1]
        # The second row's window is episode 1: a real give-up → request_answer_rate 1.0, which
        # is the FAITHFUL give-up signal (episode 1 had exactly 1 submit, so attempts mean 1.0
        # here is a REAL count that happens to equal 1, not the assumed proxy constant).
        assert second.recent_request_answer_rate == 1.0
        assert second.recent_attempts_mean == 1.0
        assert second.recent_revisions_mean == 2.0
        assert second.recent_time_to_first_interaction_ms_mean == 1500.0
