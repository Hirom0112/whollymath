"""Tests for the core SQLAlchemy models (Slice 1.8).

DB model tests are recommended, not in the mandatory-TDD tier (CLAUDE.md §9), so
these pin the *contract* of the schema rather than every column: tables create
cleanly, a Learner -> Session -> Turn -> MasteryState round-trip persists and
reads back, the (learner, kc_id) uniqueness constraint actually holds, and a
MasteryState row accepts a real ``KnowledgeComponentId`` value (proving the KC
registry and the DB speak the same id — knowledge_components.py).

Everything runs against an in-memory SQLite engine built with ``StaticPool`` so
the one in-memory database is shared across the session's connections. This needs
NO new dependency (sqlite3 is stdlib) and NO running Postgres (CLAUDE.md §8.7,
Slice 1.8 constraints). The models use only portable column types, so this SQLite
run exercises the same schema prod will get on Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.db.engine import create_all, create_session_factory
from app.db.models import Learner, MasteryState, Session, Turn
from app.domain.knowledge_components import KnowledgeComponentId
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A fresh in-memory SQLite engine with the full schema created.

    ``StaticPool`` + ``check_same_thread=False`` keeps the single in-memory DB
    alive across every connection the session opens; without it each connection
    would get its own empty database and the schema would vanish between calls.
    We build the engine directly (not via ``create_db_engine``) precisely because
    this SQLite-in-memory pooling is test-specific; ``create_db_engine`` stays
    backend-agnostic for prod.
    """
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


def test_all_core_tables_create_cleanly(engine: Engine) -> None:
    """create_all materializes exactly the four Slice-1.8 tables."""
    table_names = set(inspect(engine).get_table_names())
    assert {"learner", "session", "turn", "mastery_state"} <= table_names


def test_learner_session_turn_mastery_round_trip(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A full Learner -> Session -> Turn -> MasteryState graph persists and reads back."""
    with session_factory() as db:
        learner = Learner(session_id="sess-abc-123")
        session = Session(learner=learner)
        turn = Turn(
            session=session,
            turn_index=0,
            problem_id="prob-eq-001",
            action="submit",
            correct=True,
            error_type=None,
            surface_state="S1",
            state_transition=None,
            latency_ms=4200,
            hint_used=False,
        )
        mastery = MasteryState(
            learner=learner,
            kc_id=KnowledgeComponentId.EQUIVALENCE.value,
            bkt_probability=0.62,
            attempt_count=1,
            hint_count=0,
            unscaffolded_correct_count=1,
        )
        db.add_all([learner, session, turn, mastery])
        db.commit()
        learner_id = learner.id

    # New session: prove it round-trips from the DB, not from the identity map.
    with session_factory() as db:
        loaded = db.get(Learner, learner_id)
        assert loaded is not None
        assert loaded.session_id == "sess-abc-123"
        assert loaded.created_at is not None

        assert len(loaded.sessions) == 1
        loaded_session = loaded.sessions[0]
        assert loaded_session.started_at is not None
        assert loaded_session.ended_at is None

        assert len(loaded_session.turns) == 1
        loaded_turn = loaded_session.turns[0]
        assert loaded_turn.problem_id == "prob-eq-001"
        assert loaded_turn.correct is True
        assert loaded_turn.error_type is None
        assert loaded_turn.state_transition is None
        assert loaded_turn.latency_ms == 4200
        assert loaded_turn.hint_used is False

        assert len(loaded.mastery_states) == 1
        loaded_mastery = loaded.mastery_states[0]
        assert loaded_mastery.kc_id == "KC_equivalence"
        assert loaded_mastery.bkt_probability == pytest.approx(0.62)
        assert loaded_mastery.unscaffolded_correct_count == 1
        assert loaded_mastery.updated_at is not None


def test_mastery_state_unique_per_learner_and_kc(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Two MasteryState rows for the same (learner, kc_id) violate the constraint."""
    with session_factory() as db:
        learner = Learner(session_id="sess-dup")
        db.add(learner)
        db.flush()
        db.add(
            MasteryState(
                learner_id=learner.id,
                kc_id=KnowledgeComponentId.ADDITION_UNLIKE.value,
                bkt_probability=0.1,
            )
        )
        db.add(
            MasteryState(
                learner_id=learner.id,
                kc_id=KnowledgeComponentId.ADDITION_UNLIKE.value,
                bkt_probability=0.2,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_same_kc_allowed_for_different_learners(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The uniqueness is per (learner, kc) — two learners may hold the same KC."""
    with session_factory() as db:
        a = Learner(session_id="sess-a")
        b = Learner(session_id="sess-b")
        db.add_all([a, b])
        db.flush()
        db.add_all(
            [
                MasteryState(learner_id=a.id, kc_id=KnowledgeComponentId.EQUIVALENCE.value),
                MasteryState(learner_id=b.id, kc_id=KnowledgeComponentId.EQUIVALENCE.value),
            ]
        )
        db.commit()  # must NOT raise


def test_mastery_state_accepts_every_registry_kc_value(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Every real KnowledgeComponentId value is storable as a kc_id (id contract holds)."""
    with session_factory() as db:
        learner = Learner(session_id="sess-all-kcs")
        db.add(learner)
        db.flush()
        for kc_id in KnowledgeComponentId:
            db.add(MasteryState(learner_id=learner.id, kc_id=kc_id.value))
        db.commit()

        rows = db.query(MasteryState).filter_by(learner_id=learner.id).all()
        stored = {row.kc_id for row in rows}
        assert stored == {member.value for member in KnowledgeComponentId}
