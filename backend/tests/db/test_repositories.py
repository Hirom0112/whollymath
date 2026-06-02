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
from app.db.models import Assignment, Learner, Lesson, MasteryState, Roster, Turn, Unit
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


# --- Curriculum reads (DAT.5) -------------------------------------------------


def _seed_unit(
    db: OrmSession,
    *,
    slug: str,
    title: str,
    order: int,
) -> Unit:
    """Seed one minimal, well-formed Unit row (all NOT-NULL columns set)."""
    unit = Unit(
        slug=slug,
        title=title,
        order=order,
        ccss_cluster="6.RP.A",
        teks_cluster="6.4",
        description=f"desc {slug}",
    )
    db.add(unit)
    return unit


def test_list_units_orders_by_unit_order(session_factory: sessionmaker[OrmSession]) -> None:
    """list_units returns every unit sorted by Unit.order, regardless of insert order."""
    with session_factory() as db:
        # Insert out of display order on purpose so the ORDER BY is what sorts them.
        _seed_unit(db, slug="u3", title="Three", order=3)
        _seed_unit(db, slug="u1", title="One", order=1)
        _seed_unit(db, slug="u2", title="Two", order=2)
        db.commit()

    with session_factory() as db:
        units = repo.list_units(db)
        assert [u.slug for u in units] == ["u1", "u2", "u3"]


def test_get_unit_hit_and_miss(session_factory: sessionmaker[OrmSession]) -> None:
    """get_unit returns the unit for a known slug and None for an unknown one."""
    with session_factory() as db:
        _seed_unit(db, slug="u1-ratios", title="Ratios", order=1)
        db.commit()

    with session_factory() as db:
        hit = repo.get_unit(db, "u1-ratios")
        assert hit is not None
        assert hit.title == "Ratios"
        assert repo.get_unit(db, "no-such-unit") is None


def test_list_lessons_for_unit_orders_and_unknown_is_empty(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Lessons come back ordered by Lesson.order; an unknown unit slug yields []."""
    with session_factory() as db:
        unit = _seed_unit(db, slug="u1", title="One", order=1)
        db.flush()
        # Insert lessons out of order to prove the ORDER BY sorts them.
        db.add(Lesson(slug="u1-l2", unit_id=unit.id, order=2, title="L2"))
        db.add(Lesson(slug="u1-l1", unit_id=unit.id, order=1, title="L1"))
        db.add(Lesson(slug="u1-l3", unit_id=unit.id, order=3, title="L3"))
        db.commit()

    with session_factory() as db:
        lessons = repo.list_lessons_for_unit(db, "u1")
        assert [lesson.slug for lesson in lessons] == ["u1-l1", "u1-l2", "u1-l3"]
        # An unknown unit slug is not an error — it simply has no lessons.
        assert repo.list_lessons_for_unit(db, "no-such-unit") == []


# --- Roster reads/writes (TCH.B1) --------------------------------------------


def _seed_learner(db: OrmSession, session_id: str, *, role: str = "student") -> Learner:
    """Seed one Learner row with an explicit role."""
    learner = Learner(session_id=session_id, role=role)
    db.add(learner)
    return learner


def test_list_students_for_teacher_isolates_by_teacher(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A teacher sees only their own rostered students, ordered by Learner.id."""
    with session_factory() as db:
        teacher_a = _seed_learner(db, "teacher-a", role="teacher")
        teacher_b = _seed_learner(db, "teacher-b", role="teacher")
        s1 = _seed_learner(db, "stu-1")
        s2 = _seed_learner(db, "stu-2")
        s3 = _seed_learner(db, "stu-3")
        db.flush()
        # Teacher A rosters s1 and s2; teacher B rosters s3.
        db.add(Roster(teacher_id=teacher_a.id, student_id=s2.id))
        db.add(Roster(teacher_id=teacher_a.id, student_id=s1.id))
        db.add(Roster(teacher_id=teacher_b.id, student_id=s3.id))
        db.commit()
        teacher_a_id, teacher_b_id = teacher_a.id, teacher_b.id
        s1_id, s2_id, s3_id = s1.id, s2.id, s3.id

    with session_factory() as db:
        a_students = repo.list_students_for_teacher(db, teacher_a_id)
        # Only A's students, and ordered by Learner.id (s1 < s2) not insert order.
        assert [s.id for s in a_students] == [s1_id, s2_id]
        assert s3_id not in {s.id for s in a_students}

        b_students = repo.list_students_for_teacher(db, teacher_b_id)
        assert [s.id for s in b_students] == [s3_id]


def test_add_student_to_roster_is_idempotent(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Enrolling the same (teacher, student) twice yields exactly one roster row."""
    with session_factory() as db:
        teacher = _seed_learner(db, "teacher", role="teacher")
        student = _seed_learner(db, "student")
        db.flush()
        teacher_id, student_id = teacher.id, student.id
        first = repo.add_student_to_roster(db, teacher_id, student_id)
        db.commit()
        first_id = first.id

    with session_factory() as db:
        again = repo.add_student_to_roster(db, teacher_id, student_id)
        db.commit()
        # Same row returned, not a new one.
        assert again.id == first_id

    with session_factory() as db:
        rows = db.query(Roster).filter_by(teacher_id=teacher_id, student_id=student_id).all()
        assert len(rows) == 1  # idempotent: no duplicate membership


def test_get_student_if_on_roster_present_absent_and_foreign(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The authz primitive returns the student only for the OWNING teacher."""
    with session_factory() as db:
        teacher = _seed_learner(db, "teacher", role="teacher")
        other_teacher = _seed_learner(db, "other-teacher", role="teacher")
        student = _seed_learner(db, "student")
        unrostered = _seed_learner(db, "unrostered")
        db.flush()
        db.add(Roster(teacher_id=teacher.id, student_id=student.id))
        db.commit()
        teacher_id, other_id = teacher.id, other_teacher.id
        student_id, unrostered_id = student.id, unrostered.id

    with session_factory() as db:
        # Present: the student is on this teacher's roster.
        got = repo.get_student_if_on_roster(db, teacher_id, student_id)
        assert got is not None
        assert got.id == student_id
        # Absent: a learner not on any roster.
        assert repo.get_student_if_on_roster(db, teacher_id, unrostered_id) is None
        # Foreign teacher: the student exists but not on THIS teacher's roster.
        assert repo.get_student_if_on_roster(db, other_id, student_id) is None


# --- Assigned-unit read (DAT.10) ---------------------------------------------


def test_get_assigned_unit_none_present_and_most_recent_wins(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """get_assigned_unit returns None, then the assignment, then the latest-updated one."""
    with session_factory() as db:
        teacher = _seed_learner(db, "teacher", role="teacher")
        student = _seed_learner(db, "student")
        u1 = _seed_unit(db, slug="u1", title="One", order=1)
        u2 = _seed_unit(db, slug="u2", title="Two", order=2)
        db.flush()
        teacher_id, student_id = teacher.id, student.id
        u1_id, u2_id = u1.id, u2.id

    # None: the student has no assignment yet.
    with session_factory() as db:
        assert repo.get_assigned_unit(db, student_id) is None

    # Present: one assignment is returned.
    with session_factory() as db:
        db.add(Assignment(teacher_id=teacher_id, student_id=student_id, unit_id=u1_id))
        db.commit()
    with session_factory() as db:
        got = repo.get_assigned_unit(db, student_id)
        assert got is not None
        assert got.unit_id == u1_id

    # Most-recent-wins: assign a second unit, then touch (update) the first so its
    # updated_at is newest — the most-recently-updated assignment wins.
    with session_factory() as db:
        db.add(Assignment(teacher_id=teacher_id, student_id=student_id, unit_id=u2_id))
        db.commit()
    with session_factory() as db:
        first = db.query(Assignment).filter_by(student_id=student_id, unit_id=u1_id).one()
        first.note = "start here"  # triggers onupdate -> updated_at = now
        db.commit()
    with session_factory() as db:
        got = repo.get_assigned_unit(db, student_id)
        assert got is not None
        assert got.unit_id == u1_id  # the just-updated one is most recent


# ── Teacher reminders (dashboard upgrade) ──


def test_create_and_list_reminders_newest_first_and_scoped(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Reminders list newest-first and a teacher only sees their own."""
    with session_factory() as db:
        t1 = _seed_learner(db, "teacher-1", role="teacher")
        t2 = _seed_learner(db, "teacher-2", role="teacher")
        db.flush()
        repo.create_reminder(db, teacher_id=t1.id, text="first")
        repo.create_reminder(db, teacher_id=t1.id, text="second")
        repo.create_reminder(db, teacher_id=t2.id, text="other-teacher")
        db.commit()
        t1_id, t2_id = t1.id, t2.id

    with session_factory() as db:
        t1_reminders = repo.list_reminders_for_teacher(db, t1_id)
        assert [r.text for r in t1_reminders] == ["second", "first"]  # newest-first
        assert all(r.teacher_id == t1_id for r in t1_reminders)
        assert [r.text for r in repo.list_reminders_for_teacher(db, t2_id)] == ["other-teacher"]


def test_set_reminder_done_is_owner_scoped(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A teacher can toggle their own reminder; another teacher's resolves to None."""
    with session_factory() as db:
        owner = _seed_learner(db, "owner", role="teacher")
        intruder = _seed_learner(db, "intruder", role="teacher")
        db.flush()
        reminder = repo.create_reminder(db, teacher_id=owner.id, text="todo")
        db.commit()
        owner_id, intruder_id, reminder_id = owner.id, intruder.id, reminder.id

    # The intruder cannot toggle it (None — indistinguishable from missing).
    with session_factory() as db:
        assert (
            repo.set_reminder_done(db, teacher_id=intruder_id, reminder_id=reminder_id, done=True)
            is None
        )
        db.commit()

    # The owner can.
    with session_factory() as db:
        updated = repo.set_reminder_done(
            db, teacher_id=owner_id, reminder_id=reminder_id, done=True
        )
        assert updated is not None and updated.done is True
        db.commit()

    with session_factory() as db:
        assert repo.list_reminders_for_teacher(db, owner_id)[0].done is True


def test_locale_defaults_to_en_and_persists(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A new learner's help-language defaults to 'en' and survives a re-read (Slice 0.3)."""
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-locale")
        db.commit()
        learner_id = learner.id
        # The Python-side default applies the moment the row is persisted.
        assert learner.locale == "en"

    # A fresh session re-reads the same default off the row.
    with session_factory() as db:
        assert repo.get_learner_locale(db, learner_id) == "en"


def test_get_learner_locale_unknown_learner_is_none(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """An unknown learner_id resolves to None (distinct from an English-help learner)."""
    with session_factory() as db:
        assert repo.get_learner_locale(db, 9999) is None


def test_set_learner_locale_round_trips_es_mx(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """set_learner_locale updates the flag and the new value re-reads (en -> es-MX)."""
    with session_factory() as db:
        learner = repo.get_or_create_learner(db, "sess-set-locale")
        db.commit()
        learner_id = learner.id

    # Flip the locked Spanish target on; the writer returns the mutated row.
    with session_factory() as db:
        updated = repo.set_learner_locale(db, learner_id, "es-MX")
        assert updated is not None and updated.locale == "es-MX"
        db.commit()

    # The change is durable across a fresh read.
    with session_factory() as db:
        assert repo.get_learner_locale(db, learner_id) == "es-MX"


def test_set_learner_locale_unknown_learner_is_none(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Setting the locale of an unknown learner_id returns None (caller 404s, no raise)."""
    with session_factory() as db:
        assert repo.set_learner_locale(db, 9999, "es-MX") is None
        db.commit()
