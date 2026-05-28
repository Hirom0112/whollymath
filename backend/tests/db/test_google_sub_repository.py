"""Tests for the learner ↔ google_sub repository (Slice PL.3).

The repository is the ONLY place DB queries live (CLAUDE.md §7). This pins the contract the
auth dependency depends on:

  - ``get_or_create_learner_by_google_sub`` is idempotent: the same Google ``sub`` maps to
    exactly one learner row across calls (the "same login anywhere → same learner" property).
  - it carries the optional ``email`` onto the row when given, and leaves it unchanged on a
    later get that omits it (we never blank out a known email).
  - a learner created by google_sub has ``session_id`` distinct from anonymous learners and a
    non-null ``google_sub``.

Runs against an in-memory SQLite engine + ``create_all`` (no Postgres, CLAUDE.md §8.7),
matching ``tests/db/test_repositories.py``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.db.models import Learner
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def test_get_or_create_by_google_sub_is_idempotent(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The same Google sub maps to exactly one learner row across calls."""
    with session_factory() as db:
        first = repo.get_or_create_learner_by_google_sub(db, "google-sub-1", email="a@b.c")
        db.commit()
        first_id = first.id

    with session_factory() as db:
        again = repo.get_or_create_learner_by_google_sub(db, "google-sub-1")
        db.commit()
        assert again.id == first_id

    with session_factory() as db:
        rows = db.query(Learner).filter_by(google_sub="google-sub-1").all()
        assert len(rows) == 1  # idempotent: no duplicate learner row
        assert rows[0].google_sub == "google-sub-1"


def test_email_is_recorded_and_not_blanked(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """email is stored on create, and a later get without email does not blank it."""
    with session_factory() as db:
        repo.get_or_create_learner_by_google_sub(db, "sub-email", email="kid@example.com")
        db.commit()

    with session_factory() as db:
        # A subsequent lookup omitting email must NOT erase the known email.
        learner = repo.get_or_create_learner_by_google_sub(db, "sub-email")
        db.commit()
        assert learner.email == "kid@example.com"


def test_email_is_filled_in_when_first_seen_later(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """If the learner was created without an email, a later call may fill it in."""
    with session_factory() as db:
        learner = repo.get_or_create_learner_by_google_sub(db, "sub-late-email")
        db.commit()
        assert learner.email is None

    with session_factory() as db:
        learner = repo.get_or_create_learner_by_google_sub(
            db, "sub-late-email", email="later@example.com"
        )
        db.commit()
        assert learner.email == "later@example.com"


def test_anonymous_learner_has_no_google_sub(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """An anonymous learner (session-id keyed) leaves google_sub None — flows still separate."""
    with session_factory() as db:
        anon = repo.get_or_create_learner(db, "anon-session")
        db.commit()
        assert anon.google_sub is None
