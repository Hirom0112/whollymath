"""Alembic migration round-trip test for the Wave-1 curriculum/teacher migration (DAT.2).

This exercises the REAL migration chain (the ``command`` API, from the prior head
up to ``head`` and back down one step), not just the model metadata, so it proves
the hand-written migration's ``upgrade()``/``downgrade()`` actually apply. That is
the part ``create_all`` (the test/bootstrap path) never touches — Alembic is the
prod schema authority (migrations/env.py), so a broken migration is a prod break
even when the models are correct.

Hermetic by construction:

  - it migrates a TEMP on-disk SQLite file (``tmp_path``), never the dev DB at
    ``backend/data/whollymath.db`` and never a real Postgres;
  - env.py resolves the URL from ``database_url_from_env()`` (CLAUDE.md §10), so we
    set ``DATABASE_URL`` to the temp sqlite URL via ``monkeypatch`` for the duration
    of the test and let env.py read it — exactly the prod resolution path, just
    pointed at a throwaway file;
  - the ``Config`` points at the real ``backend/alembic.ini`` so the same
    ``script_location``/``version_path`` the prod migration uses is exercised.

We assert the four new tables AND the ``learner.role`` column appear after
``upgrade head`` and are gone after ``downgrade -1`` — the migration is reversible.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

# backend/ root: this file is backend/tests/db/test_migration_round_trip.py.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_ROOT / "alembic.ini"

# The schema objects this migration is responsible for adding.
_NEW_TABLES = {"unit", "lesson", "roster", "assignment"}


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


def test_migration_upgrade_then_downgrade_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """upgrade head adds the new tables + learner.role; downgrade -1 removes them."""
    db_path = tmp_path / "round_trip.sqlite"
    url = f"sqlite:///{db_path}"
    # env.py reads DATABASE_URL via database_url_from_env(); point it at the temp file.
    monkeypatch.setenv("DATABASE_URL", url)

    config = _alembic_config()

    # Apply the WHOLE chain from scratch through our new head.
    command.upgrade(config, "head")
    tables_after_upgrade = _table_names(url)
    assert _NEW_TABLES <= tables_after_upgrade
    # The prior-head tables are still present (the chain built on top of them).
    assert {"learner", "session", "turn", "mastery_state", "interaction_event"} <= (
        tables_after_upgrade
    )
    # The role column was added to the existing learner table.
    assert "role" in _learner_columns(url)

    # Step back exactly one revision (undo only this migration).
    command.downgrade(config, "-1")
    tables_after_downgrade = _table_names(url)
    assert _NEW_TABLES.isdisjoint(tables_after_downgrade)
    # The prior-head tables survive the single-step downgrade.
    assert {"learner", "session", "turn", "mastery_state", "interaction_event"} <= (
        tables_after_downgrade
    )
    # And the role column is gone again.
    assert "role" not in _learner_columns(url)
