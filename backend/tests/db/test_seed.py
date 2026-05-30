"""Tests for the idempotent curriculum seed (Slice DAT.4).

``seed_curriculum`` (``app.db.seed``) UPSERTs the in-code curriculum catalog
(``app.domain.curriculum`` — the frozen source of truth) into the ``unit`` /
``lesson`` tables, so the DB rows the teacher/learner surfaces and
``Assignment.unit_id`` reference always agree with the catalog. These tests pin the
contract DAT.5/DAT.10 and the migration depend on:

  - a first seed inserts exactly the catalog's units and lessons (9 + 54), with the
    same slugs, and returns the number of rows inserted;
  - the unit/lesson graph links correctly (each lesson's ``unit_id`` resolves to its
    catalog unit) and the per-lesson/​per-unit fields are carried, INCLUDING the
    ``None`` pass-through (a lesson with no KC / no CCSS code / no TEKS code) AND a
    whole TEKS-only unit (``uint`` / ``u8``) seeding with ``ccss_cluster`` NULL — the
    case the NOT-NULL bug used to break (Part 1 of this slice);
  - it is IDEMPOTENT: re-seeding adds 0 rows and leaves the counts unchanged (no
    duplicates), which is exactly what makes the migration safe to re-run and the
    upsert safe to call on every boot;
  - a pre-existing (stale) Unit row is UPDATED in place on re-seed (title refreshed),
    not duplicated — proving the upsert is keyed by ``slug`` and writes through.

Everything runs against an in-memory SQLite engine with ``StaticPool`` (the same
pattern as the other ``tests/db`` suites) — no new dependency, no running Postgres
(CLAUDE.md §8.7). ``seed_curriculum`` is COMMIT-free (caller owns the unit of work,
the repository contract), so each test commits explicitly.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.db.engine import create_all, create_session_factory
from app.db.models import Lesson, Unit
from app.db.seed import seed_curriculum
from app.domain.curriculum import all_units, get_unit
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# The catalog's totals, derived from the source of truth so the assertions track
# the catalog if it grows rather than hard-coding a number that could drift.
_CATALOG_UNITS = all_units()
_EXPECTED_UNIT_COUNT = len(_CATALOG_UNITS)
_EXPECTED_LESSON_COUNT = sum(len(u.lessons) for u in _CATALOG_UNITS)


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


def test_seed_inserts_full_catalog(session_factory: sessionmaker[OrmSession]) -> None:
    """A first seed inserts every catalog unit + lesson (9 + 54) and returns the count."""
    with session_factory() as db:
        inserted = seed_curriculum(db)
        db.commit()
        assert inserted == _EXPECTED_UNIT_COUNT + _EXPECTED_LESSON_COUNT

    with session_factory() as db:
        assert db.query(Unit).count() == _EXPECTED_UNIT_COUNT
        assert db.query(Lesson).count() == _EXPECTED_LESSON_COUNT
        # The exact catalog slugs are present (not just the right count).
        unit_slugs = {u.slug for u in db.query(Unit).all()}
        assert unit_slugs == {u.slug for u in _CATALOG_UNITS}
        lesson_slugs = {lesson_row.slug for lesson_row in db.query(Lesson).all()}
        assert lesson_slugs == {lesson.slug for unit in _CATALOG_UNITS for lesson in unit.lessons}


def test_seed_links_and_carries_fields(session_factory: sessionmaker[OrmSession]) -> None:
    """Each seeded lesson links to its catalog unit and carries its fields verbatim."""
    with session_factory() as db:
        seed_curriculum(db)
        db.commit()

    with session_factory() as db:
        units_by_slug = {u.slug: u for u in db.query(Unit).all()}
        lessons_by_slug = {lesson.slug: lesson for lesson in db.query(Lesson).all()}
        for cat_unit in _CATALOG_UNITS:
            unit_row = units_by_slug[cat_unit.slug]
            assert unit_row.title == cat_unit.title
            assert unit_row.order == cat_unit.order
            assert unit_row.ccss_cluster == cat_unit.ccss_cluster
            assert unit_row.teks_cluster == cat_unit.teks_cluster
            assert unit_row.description == cat_unit.description
            for cat_lesson in cat_unit.lessons:
                lesson_row = lessons_by_slug[cat_lesson.slug]
                # The lesson is linked to its OWN unit's row, by id.
                assert lesson_row.unit_id == unit_row.id
                assert lesson_row.order == cat_lesson.order
                assert lesson_row.kc_id == cat_lesson.kc_id
                assert lesson_row.ccss_code == cat_lesson.ccss_code
                assert lesson_row.teks_code == cat_lesson.teks_code
                assert lesson_row.title == cat_lesson.title
                assert lesson_row.description == cat_lesson.description


def test_seed_passes_none_through_on_lessons(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A lesson with no KC / no CCSS code / no TEKS code seeds with those columns NULL."""
    with session_factory() as db:
        seed_curriculum(db)
        db.commit()

    with session_factory() as db:
        lessons_by_slug = {lesson.slug: lesson for lesson in db.query(Lesson).all()}
        # u2_l7 is an interleave gate: kc_id is None in the catalog.
        assert lessons_by_slug["u2_l7"].kc_id is None
        # uint_l1 is TEKS-only: ccss_code is None in the catalog.
        assert lessons_by_slug["uint_l1"].ccss_code is None
        # u2_l1 is a foundations review: teks_code is None in the catalog.
        assert lessons_by_slug["u2_l1"].teks_code is None


def test_seed_teks_only_unit_has_null_ccss_cluster(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A whole TEKS-only unit (uint, u8) seeds with ccss_cluster NULL (the Part-1 fix)."""
    # Sanity: the catalog really has these as CCSS-None single-framework units.
    assert get_unit("uint").ccss_cluster is None
    assert get_unit("u8").ccss_cluster is None

    with session_factory() as db:
        seed_curriculum(db)
        db.commit()

    with session_factory() as db:
        units_by_slug = {u.slug: u for u in db.query(Unit).all()}
        # The TEKS-only units round-trip with a NULL CCSS cluster — the case that
        # raised IntegrityError before ccss_cluster was made nullable.
        assert units_by_slug["uint"].ccss_cluster is None
        assert units_by_slug["uint"].teks_cluster == get_unit("uint").teks_cluster
        assert units_by_slug["u8"].ccss_cluster is None
        assert units_by_slug["u8"].teks_cluster == get_unit("u8").teks_cluster


def test_seed_is_idempotent(session_factory: sessionmaker[OrmSession]) -> None:
    """Re-seeding adds 0 rows and leaves the unit/lesson counts unchanged (no dupes)."""
    with session_factory() as db:
        first = seed_curriculum(db)
        db.commit()
        assert first == _EXPECTED_UNIT_COUNT + _EXPECTED_LESSON_COUNT

    with session_factory() as db:
        second = seed_curriculum(db)
        db.commit()
        assert second == 0  # nothing new inserted on the second pass

    with session_factory() as db:
        assert db.query(Unit).count() == _EXPECTED_UNIT_COUNT
        assert db.query(Lesson).count() == _EXPECTED_LESSON_COUNT


def test_seed_updates_stale_unit_in_place(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A pre-inserted Unit with a stale title is updated in place on seed (keyed by slug)."""
    target = _CATALOG_UNITS[0]
    with session_factory() as db:
        # Pre-insert a stale row for the FIRST catalog unit's slug, with a wrong title
        # (and a deliberately-wrong cluster) so the upsert has to write through.
        db.add(
            Unit(
                slug=target.slug,
                title="STALE TITLE",
                order=999,
                ccss_cluster="WRONG",
                teks_cluster="WRONG",
                description="stale",
            )
        )
        db.commit()
        stale_id = db.query(Unit).filter_by(slug=target.slug).one().id

    with session_factory() as db:
        inserted = seed_curriculum(db)
        db.commit()
        # The stale unit was UPDATED, not inserted, so only the OTHER units + all
        # lessons are new.
        assert inserted == (_EXPECTED_UNIT_COUNT - 1) + _EXPECTED_LESSON_COUNT

    with session_factory() as db:
        rows = db.query(Unit).filter_by(slug=target.slug).all()
        assert len(rows) == 1  # updated in place, not duplicated
        row = rows[0]
        assert row.id == stale_id  # same row
        assert row.title == target.title  # refreshed from the catalog
        assert row.order == target.order
        assert row.ccss_cluster == target.ccss_cluster
        assert row.teks_cluster == target.teks_cluster
        assert row.description == target.description
