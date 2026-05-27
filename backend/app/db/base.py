"""The shared SQLAlchemy declarative base for every WhollyMath table.

Slice 1.8 (ARCHITECTURE.md §13 ``db/``; TECH_STACK §4). Every ORM model in the
project inherits from the single ``Base`` defined here so that one
``Base.metadata`` knows about all tables — that is what lets a test create the
whole schema in one ``Base.metadata.create_all(engine)`` call, and what a future
Alembic ``--autogenerate`` will read from (Alembic migrations are deferred,
1.8.3).

There is exactly one declarative base, and it lives here, so "where is the base?"
has one answer (CLAUDE.md §7 navigability). Models live in ``models.py``; the
engine/session factory lives in ``engine.py``. Nothing here issues a query —
queries belong in repositories (CLAUDE.md §7, ARCHITECTURE.md §14 invariant 5).
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by all WhollyMath ORM models.

    SQLAlchemy 2.0 typed declarative style: subclasses use ``Mapped`` /
    ``mapped_column`` so mypy --strict sees real attribute types instead of
    ``Any`` (CLAUDE.md §6 type strictness).
    """
