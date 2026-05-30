"""Tests for the curriculum (Unit/Lesson) and teacher-layer models (Wave 1, DAT.1/DAT.2).

These pin the *contract* of the four new tables plus the ``role`` column added to
``Learner`` (CLAUDE.md §9 puts DB-model tests in the recommended-not-mandatory
tier, so they assert the shape and the constraints that the repositories and the
teacher API will depend on, rather than every column):

  - the four new tables (``unit``, ``lesson``, ``roster``, ``assignment``) create
    cleanly via ``create_all`` (same in-memory SQLite path the other model tests
    use — portable types only, so this exercises the schema prod gets on Postgres);
  - a Unit -> Lesson graph persists and reads back, with ``Unit.lessons`` ordered
    by ``Lesson.order``;
  - a teacher Learner + student Learner + Roster + Assignment graph persists and
    reads back across a fresh session (proving it round-trips from the DB, not the
    identity map);
  - ``Learner.role`` defaults to ``"student"`` and accepts ``"teacher"``;
  - every UniqueConstraint (``unit.slug``, ``lesson.slug``, the (teacher, student)
    roster pair, the (student, unit) assignment pair) actually raises IntegrityError
    on a duplicate.

Everything runs against an in-memory SQLite engine with ``StaticPool`` (the same
pattern as ``tests/db/test_models.py``) — no new dependency, no running Postgres
(CLAUDE.md §8.7).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.db.engine import create_all, create_session_factory
from app.db.models import Assignment, Learner, Lesson, Roster, Unit
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import IntegrityError
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


def _make_unit(*, slug: str, title: str, order: int) -> Unit:
    """A Unit with all NOT-NULL fields filled — for tests that don't assert on them.

    ``ccss_cluster``/``teks_cluster``/``description`` are NOT NULL on Unit (a unit
    always belongs to a dual-coverage cluster); this helper supplies placeholder
    values so a test that only cares about, say, uniqueness or cascade can build a
    valid Unit without restating the cluster columns each time.
    """
    return Unit(
        slug=slug,
        title=title,
        order=order,
        ccss_cluster="6.RP.A",
        teks_cluster="6.4",
        description="placeholder",
    )


def test_new_tables_create_cleanly(engine: Engine) -> None:
    """create_all materializes the four new curriculum/teacher tables."""
    table_names = set(inspect(engine).get_table_names())
    assert {"unit", "lesson", "roster", "assignment"} <= table_names


def test_unit_lesson_round_trip_ordered(session_factory: sessionmaker[OrmSession]) -> None:
    """A Unit -> Lesson graph persists and reads back with lessons in ``order``."""
    with session_factory() as db:
        unit = Unit(
            slug="u1-ratios",
            title="Ratios & Proportional Reasoning",
            order=1,
            ccss_cluster="6.RP.A",
            teks_cluster="6.4",
            description="Understand ratio concepts and use ratio reasoning.",
        )
        # Insert lessons out of order to prove the relationship sorts them.
        unit.lessons = [
            Lesson(
                slug="u1-l2",
                order=2,
                kc_id=None,  # not every lesson maps to a KC yet (nullable by design)
                ccss_code="6.RP.A.2",
                teks_code="6.4B",
                title="Unit rates",
                description="Understand the concept of a unit rate.",
            ),
            Lesson(
                slug="u1-l1",
                order=1,
                kc_id="KC_equivalence",
                ccss_code="6.RP.A.1",
                teks_code="6.4A",
                title="Ratio language",
                description="Describe a ratio relationship between two quantities.",
            ),
        ]
        db.add(unit)
        db.commit()
        unit_id = unit.id

    with session_factory() as db:
        loaded = db.get(Unit, unit_id)
        assert loaded is not None
        assert loaded.slug == "u1-ratios"
        assert loaded.order == 1
        assert loaded.ccss_cluster == "6.RP.A"
        assert loaded.teks_cluster == "6.4"
        # Relationship is ordered by Lesson.order regardless of insert order.
        assert [lesson.order for lesson in loaded.lessons] == [1, 2]
        assert [lesson.slug for lesson in loaded.lessons] == ["u1-l1", "u1-l2"]
        first = loaded.lessons[0]
        assert first.unit_id == unit_id
        assert first.kc_id == "KC_equivalence"
        # The second lesson exercises the nullable kc_id (a lesson with no KC yet).
        assert loaded.lessons[1].kc_id is None
        # Back-reference resolves to the owning unit.
        assert first.unit is loaded


def test_lesson_unit_cascade_delete(session_factory: sessionmaker[OrmSession]) -> None:
    """Deleting a Unit deletes its Lessons (ORM cascade over the FK)."""
    with session_factory() as db:
        unit = _make_unit(slug="u2-del", title="Throwaway", order=2)
        unit.lessons = [Lesson(slug="u2-l1", order=1, title="L1")]
        db.add(unit)
        db.commit()
        unit_id = unit.id

    with session_factory() as db:
        db.delete(db.get(Unit, unit_id))
        db.commit()

    with session_factory() as db:
        assert db.query(Lesson).count() == 0


def test_learner_role_defaults_to_student(session_factory: sessionmaker[OrmSession]) -> None:
    """A Learner created without an explicit role is a 'student'."""
    with session_factory() as db:
        learner = Learner(session_id="sess-role-default")
        db.add(learner)
        db.commit()
        learner_id = learner.id

    with session_factory() as db:
        loaded = db.get(Learner, learner_id)
        assert loaded is not None
        assert loaded.role == "student"


def test_learner_role_accepts_teacher(session_factory: sessionmaker[OrmSession]) -> None:
    """A Learner can be tagged as a 'teacher' (a plain string tag, not an enum)."""
    with session_factory() as db:
        teacher = Learner(session_id="sess-teacher", role="teacher")
        db.add(teacher)
        db.commit()
        teacher_id = teacher.id

    with session_factory() as db:
        loaded = db.get(Learner, teacher_id)
        assert loaded is not None
        assert loaded.role == "teacher"


def test_roster_and_assignment_round_trip(session_factory: sessionmaker[OrmSession]) -> None:
    """A teacher + student + Roster + Assignment graph persists and reads back."""
    with session_factory() as db:
        teacher = Learner(session_id="sess-t1", role="teacher")
        student = Learner(session_id="sess-s1", role="student")
        unit = _make_unit(slug="u3-asg", title="Assignable Unit", order=3)
        db.add_all([teacher, student, unit])
        db.flush()  # assign ids before referencing them on the join rows

        roster = Roster(teacher_id=teacher.id, student_id=student.id)
        assignment = Assignment(
            teacher_id=teacher.id,
            student_id=student.id,
            unit_id=unit.id,
            note="start here",
        )
        db.add_all([roster, assignment])
        db.commit()
        roster_id = roster.id
        assignment_id = assignment.id
        teacher_id = teacher.id
        student_id = student.id
        unit_id = unit.id

    with session_factory() as db:
        loaded_roster = db.get(Roster, roster_id)
        assert loaded_roster is not None
        assert loaded_roster.teacher_id == teacher_id
        assert loaded_roster.student_id == student_id
        assert loaded_roster.created_at is not None

        loaded_asg = db.get(Assignment, assignment_id)
        assert loaded_asg is not None
        assert loaded_asg.teacher_id == teacher_id
        assert loaded_asg.student_id == student_id
        assert loaded_asg.unit_id == unit_id
        assert loaded_asg.status == "assigned"  # the default state
        assert loaded_asg.note == "start here"
        assert loaded_asg.created_at is not None
        assert loaded_asg.updated_at is not None


def test_unit_slug_is_unique(session_factory: sessionmaker[OrmSession]) -> None:
    """Two units may not share a slug (the stable curriculum key)."""
    with session_factory() as db:
        db.add_all(
            [
                _make_unit(slug="dup-unit", title="A", order=1),
                _make_unit(slug="dup-unit", title="B", order=2),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_lesson_slug_is_unique(session_factory: sessionmaker[OrmSession]) -> None:
    """Two lessons may not share a slug (the stable lesson key)."""
    with session_factory() as db:
        unit = _make_unit(slug="u-lessonslug", title="U", order=1)
        db.add(unit)
        db.flush()
        db.add_all(
            [
                Lesson(slug="dup-lesson", unit_id=unit.id, order=1, title="A"),
                Lesson(slug="dup-lesson", unit_id=unit.id, order=2, title="B"),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_roster_pair_is_unique(session_factory: sessionmaker[OrmSession]) -> None:
    """The same (teacher, student) may be enrolled only once."""
    with session_factory() as db:
        teacher = Learner(session_id="sess-t-dup", role="teacher")
        student = Learner(session_id="sess-s-dup", role="student")
        db.add_all([teacher, student])
        db.flush()
        db.add_all(
            [
                Roster(teacher_id=teacher.id, student_id=student.id),
                Roster(teacher_id=teacher.id, student_id=student.id),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_assignment_student_unit_is_unique(session_factory: sessionmaker[OrmSession]) -> None:
    """A student has at most one assignment per unit (the idempotent-upsert target)."""
    with session_factory() as db:
        teacher = Learner(session_id="sess-t-asg", role="teacher")
        student = Learner(session_id="sess-s-asg", role="student")
        unit = _make_unit(slug="u-asg-dup", title="U", order=1)
        db.add_all([teacher, student, unit])
        db.flush()
        db.add_all(
            [
                Assignment(teacher_id=teacher.id, student_id=student.id, unit_id=unit.id),
                Assignment(teacher_id=teacher.id, student_id=student.id, unit_id=unit.id),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_same_unit_assignable_to_different_students(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The (student, unit) uniqueness is per student — many students may get one unit."""
    with session_factory() as db:
        teacher = Learner(session_id="sess-t-multi", role="teacher")
        s1 = Learner(session_id="sess-s-multi-1", role="student")
        s2 = Learner(session_id="sess-s-multi-2", role="student")
        unit = _make_unit(slug="u-multi", title="U", order=1)
        db.add_all([teacher, s1, s2, unit])
        db.flush()
        db.add_all(
            [
                Assignment(teacher_id=teacher.id, student_id=s1.id, unit_id=unit.id),
                Assignment(teacher_id=teacher.id, student_id=s2.id, unit_id=unit.id),
            ]
        )
        db.commit()  # must NOT raise
