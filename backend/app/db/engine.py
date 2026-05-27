"""Engine and session-factory helpers for the WhollyMath database (Slice 1.8).

A thin factory layer: given a SQLAlchemy URL, build an ``Engine`` and a
``sessionmaker``. This is intentionally *not* where queries live — repositories
(a later slice) take a session and do the work (CLAUDE.md §7, ARCHITECTURE.md §14
invariant 5). Keeping construction here means tests can spin up an in-memory
SQLite engine and prod can point at RDS Postgres through the same entry points,
with no model code aware of which backend it's on.

Prod reads ``DATABASE_URL`` from the environment (``.env`` locally via
python-dotenv, Secrets Manager in prod — CLAUDE.md §10). Tests pass an explicit
SQLite URL and never touch the environment.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


def create_db_engine(url: str, *, echo: bool = False) -> Engine:
    """Build an ``Engine`` for the given SQLAlchemy URL.

    Kept trivial on purpose: pooling/timeout tuning is premature here (CLAUDE.md
    §8.6) and would differ per backend. Callers that need an in-memory SQLite
    engine usable across connections should pass a shared-cache/StaticPool URL
    themselves; the default config is fine for prod Postgres and for file/SQLite.
    """
    return create_engine(url, echo=echo)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a ``sessionmaker`` bound to ``engine``.

    ``expire_on_commit=False`` so attributes stay readable after commit without a
    re-fetch — convenient for the request/response turn loop and for tests that
    assert on a row right after committing it.
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_all(engine: Engine) -> None:
    """Create every table known to ``Base.metadata`` on ``engine``.

    Used by tests (and local bootstrap) to materialize the whole schema in one
    call. Prod schema changes go through Alembic migrations once those land
    (deferred, Slice 1.8.3) — ``create_all`` is not the prod migration path.
    """
    Base.metadata.create_all(engine)


def database_url_from_env(var: str = "DATABASE_URL") -> str:
    """Read the database URL from the environment, erroring clearly if unset.

    Failing loudly here beats a confusing connection error deep in the stack
    (CLAUDE.md §8.5). The actual ``.env`` loading is python-dotenv's job at app
    startup (CLAUDE.md §10); this only reads what's already in ``os.environ``.
    """
    url = os.environ.get(var)
    if not url:
        raise RuntimeError(
            f"{var} is not set; configure it in .env (local) or Secrets Manager (prod)."
        )
    return url
