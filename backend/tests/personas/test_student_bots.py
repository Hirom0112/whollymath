"""Tests for the persona-bot DATA runner (``app.personas.student_bots``).

What is under test: driving the FIVE fraction personas (Layer-3 simulator) through the
REAL ``SessionStore`` turn loop with persistence ON produces GENUINE
Learner/Session/Turn/MasteryState rows + a roster, so the teacher dashboard reads real
students instead of hand-set demo rows. The bots are deterministic code (CLAUDE.md §8.3):
no LLM, no invention — wrong answers come from the SymPy misconception generators via the
simulator. So these tests are deterministic too (same input ⇒ same rows).

The load-bearing properties pinned here:
  - run_student_bot drives turns and PERSISTS them (Turn + MasteryState rows), and
    ROSTERS the resulting learner to the teacher (so the dashboard can read it).
  - it is IDEMPOTENT on the stable per-bot session id: re-running maps to the same
    learner and does NOT duplicate the turn history (the demo class is stable across
    reboots, handoff §1c).
  - seed_demo_class runs every profile, creates+rosters them to the demo teacher, and is
    idempotent (same learner ids on re-run, roster size unchanged).
  - the data is REAL and VARIED: a mastery persona accrues correct turns; a no-grip
    persona accrues wrong turns — not a uniform fill.

Run against an in-memory SQLite engine + ``create_all`` + ``seed_curriculum`` (no
Postgres, CLAUDE.md §8.7), mirroring ``tests/api/test_persistence_wiring.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from app.db.engine import create_all, create_session_factory
from app.db.models import Assignment, Learner, Roster, Session, Turn
from app.db.repositories import get_or_create_demo_teacher
from app.db.seed import seed_curriculum
from app.personas.registry import get_persona
from app.personas.student_bots import (
    DEMO_BOT_PROFILES,
    StudentBotProfile,
    run_student_bot,
    seed_demo_class,
)
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_NOW = datetime(2026, 5, 30, tzinfo=UTC)


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    """A shared in-memory SQLite engine + schema + seeded curriculum, as a factory."""
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    factory = create_session_factory(engine)
    with factory() as db:
        seed_curriculum(db)
        db.commit()
    yield factory
    engine.dispose()


def _demo_teacher_id(session_factory: sessionmaker[OrmSession]) -> int:
    with session_factory() as db:
        teacher = get_or_create_demo_teacher(db)
        db.commit()
        return teacher.id


def test_run_student_bot_persists_turns_and_rosters(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """One bot run writes real Turn + MasteryState rows and rosters the learner."""
    teacher_id = _demo_teacher_id(session_factory)
    profile = StudentBotProfile(
        persona=get_persona("procedure_priya"),
        display_name="Procedure Priya",
        session_id="bot-priya-test",
        route_key="combine",
        intended_category="on_track",
    )

    learner_id = run_student_bot(profile, session_factory, teacher_id=teacher_id, now=_NOW)

    with session_factory() as db:
        learner = db.get(Learner, learner_id)
        assert learner is not None
        assert learner.session_id == "bot-priya-test"
        # Real turns were persisted for this bot's session.
        sessions = db.query(Session).filter(Session.learner_id == learner_id).all()
        assert len(sessions) == 1
        turns = db.query(Turn).filter(Turn.session_id == sessions[0].id).all()
        assert turns, "the bot must persist real turns"
        assert [t.turn_index for t in turns] == list(range(len(turns)))
        # The learner is on the teacher's roster (so the dashboard reads it as a student).
        roster = (
            db.query(Roster)
            .filter(Roster.teacher_id == teacher_id, Roster.student_id == learner_id)
            .all()
        )
        assert len(roster) == 1


def test_run_student_bot_is_idempotent(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Re-running a bot maps to the SAME learner and does not duplicate turns/sessions."""
    teacher_id = _demo_teacher_id(session_factory)
    profile = StudentBotProfile(
        persona=get_persona("surface_sam"),
        display_name="Surface Sam",
        session_id="bot-sam-test",
        route_key="combine",
        intended_category="struggling",
    )

    first = run_student_bot(profile, session_factory, teacher_id=teacher_id, now=_NOW)
    with session_factory() as db:
        first_turns = db.query(Turn).count()
        first_sessions = db.query(Session).count()

    second = run_student_bot(profile, session_factory, teacher_id=teacher_id, now=_NOW)
    with session_factory() as db:
        assert db.query(Turn).count() == first_turns, "re-run must not duplicate turns"
        assert db.query(Session).count() == first_sessions, "re-run must not duplicate sessions"
        assert db.query(Learner).filter(Learner.role == "student").count() == 1

    assert first == second


def test_run_student_bot_assigns_a_unit_when_present(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The bot is assigned the unit that teaches its goal KC (best-effort steering)."""
    teacher_id = _demo_teacher_id(session_factory)
    profile = StudentBotProfile(
        persona=get_persona("procedure_priya"),
        display_name="Procedure Priya",
        session_id="bot-priya-assign",
        route_key="combine",  # ADDITION_UNLIKE lives in unit u2
        intended_category="on_track",
    )

    learner_id = run_student_bot(profile, session_factory, teacher_id=teacher_id, now=_NOW)

    with session_factory() as db:
        assignment = db.query(Assignment).filter(Assignment.student_id == learner_id).one_or_none()
        assert assignment is not None
        assert assignment.teacher_id == teacher_id


def test_seed_demo_class_seeds_every_profile_idempotently(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """seed_demo_class rosters all profiles to the demo teacher; re-run is stable."""
    first_ids = seed_demo_class(session_factory, now=_NOW)
    assert len(first_ids) == len(DEMO_BOT_PROFILES)
    assert len(set(first_ids)) == len(first_ids), "each bot is a distinct learner"

    with session_factory() as db:
        teacher = get_or_create_demo_teacher(db)
        roster_count = db.query(Roster).filter(Roster.teacher_id == teacher.id).count()
    assert roster_count == len(DEMO_BOT_PROFILES)

    # Re-run: same learner ids, roster unchanged (idempotent).
    second_ids = seed_demo_class(session_factory, now=_NOW)
    assert second_ids == first_ids
    with session_factory() as db:
        teacher = get_or_create_demo_teacher(db)
        assert db.query(Roster).filter(Roster.teacher_id == teacher.id).count() == len(
            DEMO_BOT_PROFILES
        )


def test_seed_demo_class_produces_real_and_varied_data(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The persona bots produce GENUINE, varied turn outcomes — not a uniform fill."""
    seed_demo_class(session_factory, now=_NOW)
    with session_factory() as db:
        outcomes = [t.correct for t in db.query(Turn).all()]
    assert outcomes, "the demo class must produce turns"
    # A mastery persona (Priya) answers correctly; a no-grip persona (Cleo) answers
    # wrong — so the class spans both, proving the data comes from the real engine.
    assert any(outcomes), "at least one correct turn (the mastery personas)"
    assert not all(outcomes), "at least one wrong turn (the no-grip / misconception personas)"
