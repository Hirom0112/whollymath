"""Alembic migration environment (Slice PL.1, closes TODO 1.8.3).

Alembic is now the migration AUTHORITY for the prod schema: schema changes are
expressed as versioned migrations generated from ``app.db.base.Base.metadata``
(``--autogenerate``), not applied via ``create_all``. ``create_all`` remains the
test/bootstrap path only (it materializes the whole schema in one call against the
in-memory SQLite test engine — see ``app.db.engine.create_all``); production runs
``alembic upgrade head``.

Two deliberate wirings here:
  - ``target_metadata`` is ``Base.metadata`` AFTER importing ``app.db.models``, so
    every ORM table (Learner / Session / Turn / MasteryState) is registered and
    autogenerate sees the real schema (the single source of truth is the models,
    CLAUDE.md §7).
  - the URL is read from ``database_url_from_env()`` (the same env var the app uses)
    rather than hardcoded in ``alembic.ini`` — so dev (.env), CI, and prod (Secrets
    Manager) all migrate the database they are actually pointed at (CLAUDE.md §10),
    with no secret committed to the repo. ``alembic -x url=...`` overrides it for a
    one-off (e.g. migrating a local sqlite file to prove the migration applies).
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import the models for their side effect: registering every table on Base.metadata,
# which is what autogenerate diffs against. Base is the single declarative base.
from app.db import models as _models  # noqa: F401  (imported for table registration)
from app.db.base import Base
from app.db.engine import database_url_from_env

# The Alembic Config object, providing access to alembic.ini values.
config = context.config

# Python logging from the ini file (if present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate diffs the live DB against this metadata (all four Slice-1.8 tables).
target_metadata = Base.metadata


def _resolve_url() -> str:
    """The database URL to migrate: an ``-x url=...`` override, else ``database_url_from_env``.

    The ``-x url=`` escape hatch lets a developer point a one-off migration at, e.g., a local
    sqlite file to prove ``upgrade head`` builds the schema, without touching the environment.
    Otherwise we use the same ``DATABASE_URL`` the app reads, so we always migrate the database
    the app actually talks to (CLAUDE.md §10). No URL is ever read from ``alembic.ini``.
    """
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override
    return database_url_from_env()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL from a URL, no DBAPI needed)."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect and apply against the live DB)."""
    section = config.get_section(config.config_ini_section, {})
    # Inject the resolved URL so engine_from_config builds against it (ini has no url).
    section["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
