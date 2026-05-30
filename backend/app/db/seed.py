"""Seed the curriculum catalog into the ``unit`` / ``lesson`` tables (Slice DAT.4).

WHY this exists. ``app.domain.curriculum`` is the frozen, in-code SOURCE OF TRUTH
for the Grade-6 scope and sequence (9 units → 54 lessons, each dual-tagged or
honestly single-framework). But the teacher/learner surfaces read DB rows, and
``Assignment.unit_id`` is a foreign key that needs a real ``unit.id`` to point at.
This module is the bridge: it materializes the catalog into rows so the database
and the catalog can never disagree about *what the curriculum is* (the same
single-source discipline the KC registry uses, ARCHITECTURE.md §4). The catalog is
authority; these rows are its projection.

CONTRACT (matches the repositories in ``app.db.repositories``):

  - **UPSERT keyed by ``slug``.** A unit/lesson is looked up by its stable external
    ``slug`` and UPDATED in place when present, INSERTED only on first sight. So a
    re-seed refreshes drifted rows to the catalog rather than spawning duplicates.
  - **IDEMPOTENT.** Running it twice yields no new rows and no duplicates — which is
    exactly what lets the migration (and any boot-time call) run it safely more than
    once.
  - **COMMIT-free.** Like every writer in ``repositories.py``, this ``add``-s/updates
    but does NOT commit, flush-on-demand only: the CALLER owns the unit-of-work
    boundary (the migration commits; a test commits explicitly). We DO ``flush`` the
    units before linking lessons, because a lesson's ``unit_id`` FK needs the unit's
    generated ``id`` — a flush assigns ids without ending the caller's transaction.
  - **``None`` passes through.** A TEKS-only unit carries ``ccss_cluster=None`` (and a
    CCSS-only unit would carry ``teks_cluster=None``); a lesson may carry ``kc_id`` /
    ``ccss_code`` / ``teks_code`` as ``None``. These are written as NULL verbatim — the
    columns are nullable for exactly this dual-coverage reason (models.py,
    TEKS_CCSS_COMPARISON.md / CURRICULUM_STANDARD.md).

No SymPy, no LLM (CLAUDE.md §8.1/§8.2). ORM writes only (CLAUDE.md §7 — DB writes
live in the db layer). SQLAlchemy 2.0 typed style (``select`` + typed ``Mapped``
columns), matching ``models.py`` and ``repositories.py``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.db.models import Lesson, Unit
from app.domain.curriculum import CatalogLesson, CatalogUnit, all_units


def _upsert_unit(db: OrmSession, cat_unit: CatalogUnit) -> tuple[Unit, bool]:
    """Insert or update the ``Unit`` row for a catalog unit; return (row, inserted).

    Looked up by the stable ``slug`` (the reseed-stable external key, models.py).
    The catalog fields — title, order, both framework clusters (``None`` passed
    through verbatim), and description — are written through on every call, so a
    drifted row is reconciled to the catalog on re-seed. ``add``-ed but NOT
    committed (caller's boundary); the second element of the tuple reports whether a
    NEW row was added so the caller can count insertions (idempotency proof).
    """
    row = db.scalars(select(Unit).where(Unit.slug == cat_unit.slug)).first()
    inserted = row is None
    if row is None:
        row = Unit(slug=cat_unit.slug)
        db.add(row)
    row.title = cat_unit.title
    row.order = cat_unit.order
    row.ccss_cluster = cat_unit.ccss_cluster  # None for a TEKS-only unit (uint, u8)
    row.teks_cluster = cat_unit.teks_cluster  # None for a CCSS-only unit (none today)
    row.description = cat_unit.description
    return row, inserted


def _upsert_lesson(db: OrmSession, unit_id: int, cat_lesson: CatalogLesson) -> bool:
    """Insert or update the ``Lesson`` row for a catalog lesson; return whether inserted.

    Looked up by the stable ``slug`` and linked to its owning unit via ``unit_id``
    (the FK target the caller flushed into existence first). Order, ``kc_id``,
    ``ccss_code``, ``teks_code`` (any of which may be ``None`` — passed through
    verbatim), title, and description are written through on every call. ``add``-ed
    but NOT committed (caller's boundary).
    """
    row = db.scalars(select(Lesson).where(Lesson.slug == cat_lesson.slug)).first()
    inserted = row is None
    if row is None:
        row = Lesson(slug=cat_lesson.slug)
        db.add(row)
    row.unit_id = unit_id
    row.order = cat_lesson.order
    row.kc_id = cat_lesson.kc_id  # None where the lesson maps to no single KC yet
    row.ccss_code = cat_lesson.ccss_code  # None for a TEKS-only lesson
    row.teks_code = cat_lesson.teks_code  # None for a CCSS-only / foundations lesson
    row.title = cat_lesson.title
    row.description = cat_lesson.description
    return inserted


def seed_curriculum(db: OrmSession) -> int:
    """Upsert the whole curriculum catalog into the DB; return the rows INSERTED.

    Walks ``app.domain.curriculum.all_units()`` (the frozen source of truth) and
    UPSERTs a ``Unit`` row per ``CatalogUnit`` and a ``Lesson`` row per
    ``CatalogLesson``, each keyed by its stable ``slug``. Existing rows are updated
    in place (so a re-seed reconciles drift); absent rows are inserted. The return
    value is the number of NEWLY INSERTED rows (units + lessons) — 0 on a re-seed of
    an already-current DB, which is the idempotency contract callers (and the
    migration) rely on.

    IDEMPOTENT and COMMIT-free: the caller owns the unit of work. We ``flush`` after
    upserting each unit so the lesson rows can reference the unit's generated ``id``
    (the ``Lesson.unit_id`` FK), but we never commit — the migration / test / boot
    caller decides when the transaction closes (matches the ``repositories.py``
    contract: add, don't commit). See the module docstring for the full rationale.
    """
    inserted = 0
    for cat_unit in all_units():
        unit_row, unit_inserted = _upsert_unit(db, cat_unit)
        if unit_inserted:
            inserted += 1
        # Flush so a freshly-inserted unit has its autoincrement id before we link
        # its lessons (the FK target). Flush, not commit — the caller owns the tx.
        db.flush()
        for cat_lesson in cat_unit.lessons:
            if _upsert_lesson(db, unit_row.id, cat_lesson):
                inserted += 1
    return inserted


__all__ = ["seed_curriculum"]
