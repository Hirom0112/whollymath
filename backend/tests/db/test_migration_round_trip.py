"""Alembic migration tests for the Wave-1 curriculum/teacher chain (DAT.2 + DAT.4).

This exercises the REAL migration chain (the ``command`` API), not just the model
metadata, so it proves the hand-written migrations' ``upgrade()``/``downgrade()``
actually apply. That is the part ``create_all`` (the test/bootstrap path) never
touches — Alembic is the prod schema authority (migrations/env.py), so a broken
migration is a prod break even when the models are correct.

Two migrations are in scope:

  - ``c1a7b2f4d9e0`` (DAT.2) adds ``unit`` / ``lesson`` / ``roster`` / ``assignment``
    and the ``learner.role`` column. It is fully REVERSIBLE, so it is tested with an
    upgrade-then-downgrade round trip (the four tables + ``role`` appear, then are
    gone).
  - ``b4f7c9a2e1d8`` (DAT.4) makes ``unit.ccss_cluster``/``teks_cluster`` nullable and
    SEEDS the curriculum catalog (9 units, 54 lessons), including TEKS-only units that
    carry ``ccss_cluster=None``. Its ``downgrade`` is DELIBERATELY a column-only revert
    that does NOT un-seed and would fail to restore NOT NULL while a TEKS-only row
    exists (documented as acceptable in the migration; forward is the supported path —
    the spec for this slice). So this migration is tested FORWARD-ONLY: upgrading to
    head seeds exactly the catalog onto a fresh DB.

Hermetic by construction:

  - it migrates a TEMP on-disk SQLite file (``tmp_path``), never the dev DB at
    ``backend/data/whollymath.db`` and never a real Postgres;
  - env.py resolves the URL from ``database_url_from_env()`` (CLAUDE.md §10), so we
    set ``DATABASE_URL`` to the temp sqlite URL via ``monkeypatch`` for the duration
    of the test and let env.py read it — exactly the prod resolution path, just
    pointed at a throwaway file;
  - the ``Config`` points at the real ``backend/alembic.ini`` so the same
    ``script_location``/``version_path`` the prod migration uses is exercised.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.domain.curriculum import all_units
from sqlalchemy import create_engine, inspect, text

# backend/ root: this file is backend/tests/db/test_migration_round_trip.py.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_ROOT / "alembic.ini"

# The schema objects the DAT.2 curriculum/teacher migration is responsible for adding.
_NEW_TABLES = {"unit", "lesson", "roster", "assignment"}

# The DAT.2 curriculum/teacher migration (reversible) and the revision just before it
# (the interaction_event/google_sub head from before the curriculum tables existed).
_CURRICULUM_REVISION = "c1a7b2f4d9e0"
_PRE_CURRICULUM_REVISION = "1d435502e4db"

# The catalog totals (source of truth) the DAT.4 seed must materialize.
_CATALOG_UNITS = all_units()
_EXPECTED_UNIT_COUNT = len(_CATALOG_UNITS)
_EXPECTED_LESSON_COUNT = sum(len(u.lessons) for u in _CATALOG_UNITS)


def _alembic_config() -> Config:
    """An Alembic ``Config`` pointed at the real backend alembic.ini.

    ``script_location`` in the ini is the relative ``migrations``; we set the main
    option to the absolute path so the test does not depend on the process cwd.
    """
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    return config


def _table_names(url: str) -> set[str]:
    """The set of table names currently present in the database at ``url``."""
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _learner_columns(url: str) -> set[str]:
    """The column names of the ``learner`` table at ``url``."""
    engine = create_engine(url)
    try:
        return {col["name"] for col in inspect(engine).get_columns("learner")}
    finally:
        engine.dispose()


def _scalar(url: str, sql: str) -> int:
    """Run a one-value query against the database at ``url`` (a COUNT)."""
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(sql)).scalar_one())
    finally:
        engine.dispose()


def test_curriculum_migration_upgrade_then_downgrade_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DAT.2: upgrade to the curriculum revision adds tables + role; downgrade removes them."""
    db_path = tmp_path / "round_trip.sqlite"
    url = f"sqlite:///{db_path}"
    # env.py reads DATABASE_URL via database_url_from_env(); point it at the temp file.
    monkeypatch.setenv("DATABASE_URL", url)

    config = _alembic_config()

    # Apply the chain from scratch UP TO (and including) the reversible curriculum
    # migration — but NOT the DAT.4 seed migration, whose downgrade is forward-only.
    command.upgrade(config, _CURRICULUM_REVISION)
    tables_after_upgrade = _table_names(url)
    assert _NEW_TABLES <= tables_after_upgrade
    # The prior-head tables are still present (the chain built on top of them).
    assert {"learner", "session", "turn", "mastery_state", "interaction_event"} <= (
        tables_after_upgrade
    )
    # The role column was added to the existing learner table.
    assert "role" in _learner_columns(url)

    # Step back to the revision just before the curriculum migration (undo only it).
    command.downgrade(config, _PRE_CURRICULUM_REVISION)
    tables_after_downgrade = _table_names(url)
    assert _NEW_TABLES.isdisjoint(tables_after_downgrade)
    # The prior-head tables survive the downgrade.
    assert {"learner", "session", "turn", "mastery_state", "interaction_event"} <= (
        tables_after_downgrade
    )
    # And the role column is gone again.
    assert "role" not in _learner_columns(url)


def test_seed_migration_upgrade_head_seeds_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DAT.4: upgrading the whole chain to head seeds exactly the catalog (9 units, 54 lessons)."""
    db_path = tmp_path / "seed_head.sqlite"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)

    config = _alembic_config()

    # The full chain, including the DAT.4 nullable-cluster + seed migration.
    command.upgrade(config, "head")

    # The catalog was seeded in full.
    assert _scalar(url, "SELECT COUNT(*) FROM unit") == _EXPECTED_UNIT_COUNT
    assert _scalar(url, "SELECT COUNT(*) FROM lesson") == _EXPECTED_LESSON_COUNT
    # The TEKS-only units (uint, u8) seeded with a NULL ccss_cluster — the case the
    # nullability fix (Part 1) enables and the NOT-NULL schema used to reject.
    teks_only = [u.slug for u in _CATALOG_UNITS if u.ccss_cluster is None]
    assert teks_only  # the catalog really has single-framework units
    assert _scalar(url, "SELECT COUNT(*) FROM unit WHERE ccss_cluster IS NULL") == len(teks_only)
