"""Tests for the persistence repository layer (Slice PL.1).

The repository is the ONLY place DB queries live (CLAUDE.md §7; ARCHITECTURE.md
§14 invariant 5): pure functions over a SQLAlchemy ORM ``Session``, no business
logic. These tests pin the contract a service depends on:

  - create-or-get a Learner by its opaque external ``session_id`` (idempotent).
  - open a tutoring Session row for a learner; end it (set ``ended_at``).
  - persist one Turn (the API/tutor turn fields → the Turn columns).
  - upsert a MasteryState per (learner, kc): a second write to the same
    (learner, kc) updates in place rather than inserting a duplicate.
  - load an open Session (``ended_at IS NULL``) with its turns; load a learner's
    MasteryState rows.

Everything runs against an in-memory SQLite engine with ``StaticPool`` (the same
pattern as ``tests/db/test_models.py``) — no new dependency, no running Postgres
(CLAUDE.md §8.7). The models use only portable column types, so this exercises the
same schema prod gets on Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.db.models import Learner, MasteryState, Turn
from app.domain.knowledge_components import KnowledgeComponentId
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A fresh in-memory SQLite engine with the full schema created."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[OrmSession]:
    """Session factory bound to the in-memory engine."""
    return create_session_factory(engine)


def test_get_or_create_learner_is_idempotent(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The same opaque session_id maps to exactly one learner row across calls."""
    with session_factory() as db:
        first = repo.get_or_create_learner(db, "sess-xyz")
        db.commit()
        first_id = first.id

    with session_factory() as db:
        again = repo.get_or_create_learner(db, "sess-xyz")
        db.commit()
        assert again.id == first_id

    with session_factory() as db:
        learners = db.query(Learner).filter_by(session_id="sess-xyz").all()
        assert len(learners) == 1  # idempotent: no duplicate learner row


def test_open_and_end_session(session_factory: sessionmaker[OrmSession]) -> None:
    """A session row opens with ended_at NULL and end_session stamps ended_at."""
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-end")
        db.flush()
        session = repo.create_session(db, learner_id=learner.id)
        db.commit()
        session_id = session.id
        assert session.ended_at is None

    with session_factory() as db:
        repo.end_session(db, session_id)
        db.commit()

    with session_factory() as db:
        loaded = repo.load_open_session(db, session_id)
        # Once ended, it is no longer an OPEN session.
        assert loaded is None


def test_persist_turn_maps_all_fields(session_factory: sessionmaker[OrmSession]) -> None:
    """persist_turn writes every turn column from the supplied values."""
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-turn")
        db.flush()
        session = repo.create_session(db, learner_id=learner.id)
        db.flush()
        repo.persist_turn(
            db,
            session_id=session.id,
            turn_index=0,
            problem_id="prob-add-001",
            action="submit_answer",
            correct=True,
            error_type=None,
            surface_state="S1_symbolic_focus",
            state_transition="faded to symbolic",
            latency_ms=3200,
            hint_used=False,
        )
        db.commit()
        session_id = session.id

    with session_factory() as db:
        turns = db.query(Turn).filter_by(session_id=session_id).all()
        assert len(turns) == 1
        turn = turns[0]
        assert turn.turn_index == 0
        assert turn.problem_id == "prob-add-001"
        assert turn.action == "submit_answer"
        assert turn.correct is True
        assert turn.error_type is None
        assert turn.surface_state == "S1_symbolic_focus"
        assert turn.state_transition == "faded to symbolic"
        assert turn.latency_ms == 3200
        assert turn.hint_used is False


def test_upsert_mastery_inserts_then_updates_in_place(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A second upsert for the same (learner, kc) updates the row, not inserts a new one."""
    kc = KnowledgeComponentId.EQUIVALENCE.value
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-mastery")
        db.flush()
        repo.upsert_mastery_state(
            db,
            learner_id=learner.id,
            kc_id=kc,
            bkt_probability=0.3,
            attempt_count=1,
            hint_count=0,
            unscaffolded_correct_count=1,
        )
        db.commit()
        learner_id = learner.id

    with session_factory() as db:
        repo.upsert_mastery_state(
            db,
            learner_id=learner_id,
            kc_id=kc,
            bkt_probability=0.7,
            attempt_count=3,
            hint_count=1,
            unscaffolded_correct_count=2,
        )
        db.commit()

    with session_factory() as db:
        rows = db.query(MasteryState).filter_by(learner_id=learner_id, kc_id=kc).all()
        assert len(rows) == 1  # updated in place, not duplicated
        row = rows[0]
        assert row.bkt_probability == pytest.approx(0.7)
        assert row.attempt_count == 3
        assert row.hint_count == 1
        assert row.unscaffolded_correct_count == 2


def test_load_open_session_returns_turns_in_order(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """load_open_session returns the open session with its turns in played order."""
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-load")
        db.flush()
        session = repo.create_session(db, learner_id=learner.id)
        db.flush()
        for idx in range(3):
            repo.persist_turn(
                db,
                session_id=session.id,
                turn_index=idx,
                problem_id=f"prob-{idx}",
                action="submit_answer",
                correct=True,
                error_type=None,
                surface_state="S1_symbolic_focus",
                state_transition=None,
                latency_ms=1000 + idx,
                hint_used=False,
            )
        db.commit()
        session_id = session.id

    with session_factory() as db:
        loaded = repo.load_open_session(db, session_id)
        assert loaded is not None
        assert [t.turn_index for t in loaded.turns] == [0, 1, 2]


def test_load_mastery_states_for_learner(session_factory: sessionmaker[OrmSession]) -> None:
    """load_mastery_states returns all of a learner's per-KC rows."""
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-states")
        db.flush()
        repo.upsert_mastery_state(
            db,
            learner_id=learner.id,
            kc_id=KnowledgeComponentId.EQUIVALENCE.value,
            bkt_probability=0.9,
            attempt_count=4,
            hint_count=0,
            unscaffolded_correct_count=3,
        )
        repo.upsert_mastery_state(
            db,
            learner_id=learner.id,
            kc_id=KnowledgeComponentId.ADDITION_UNLIKE.value,
            bkt_probability=0.2,
            attempt_count=1,
            hint_count=1,
            unscaffolded_correct_count=0,
        )
        db.commit()
        learner_id = learner.id

    with session_factory() as db:
        states = repo.load_mastery_states(db, learner_id)
        by_kc = {s.kc_id: s for s in states}
        assert set(by_kc) == {
            KnowledgeComponentId.EQUIVALENCE.value,
            KnowledgeComponentId.ADDITION_UNLIKE.value,
        }
        assert by_kc[KnowledgeComponentId.EQUIVALENCE.value].bkt_probability == pytest.approx(0.9)
