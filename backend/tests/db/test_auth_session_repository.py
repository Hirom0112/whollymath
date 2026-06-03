"""Tests for the revocable auth-session repository (Slice auth/parent-child, S2).

These pin the contract that makes session revocation REAL (a stateless JWT cannot be
un-issued, so the server-side row is what logout / a parent kill-switch act on):

  - a freshly opened session is "active" and resolvable by its jti;
  - a revoked session, or one past expires_at, is NOT active (a request must be
    refused even though the JWT signature is still valid);
  - revoking one session is idempotent; revoking ALL of a learner's sessions is the
    "sign out everywhere" kill-switch and leaves other learners untouched.

In-memory SQLite + create_all, matching the other db tests (CLAUDE.md §8.7).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.db.models import Learner
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC)


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


def _learner(db: OrmSession, session_id: str) -> Learner:
    learner = repo.get_or_create_learner(db, session_id)
    db.flush()
    return learner


def test_open_session_is_active(session_factory: sessionmaker[OrmSession]) -> None:
    with session_factory() as db:
        learner = _learner(db, "L1")
        repo.create_auth_session(
            db,
            learner_id=learner.id,
            jti="jti-1",
            kind="parent",
            expires_at=_NOW + timedelta(minutes=30),
        )
        db.commit()

    with session_factory() as db:
        active = repo.get_active_auth_session(db, "jti-1", _NOW)
        assert active is not None
        assert active.kind == "parent"


def test_revoked_session_is_not_active(session_factory: sessionmaker[OrmSession]) -> None:
    with session_factory() as db:
        learner = _learner(db, "L2")
        repo.create_auth_session(
            db,
            learner_id=learner.id,
            jti="jti-2",
            kind="child",
            expires_at=_NOW + timedelta(minutes=30),
        )
        db.commit()

    with session_factory() as db:
        assert repo.revoke_auth_session(db, "jti-2", _NOW) is True
        db.commit()

    with session_factory() as db:
        assert repo.get_active_auth_session(db, "jti-2", _NOW) is None
        # Revoking again is an idempotent no-op.
        assert repo.revoke_auth_session(db, "jti-2", _NOW) is False


def test_expired_session_is_not_active(session_factory: sessionmaker[OrmSession]) -> None:
    with session_factory() as db:
        learner = _learner(db, "L3")
        repo.create_auth_session(
            db,
            learner_id=learner.id,
            jti="jti-3",
            kind="parent",
            expires_at=_NOW + timedelta(minutes=30),
        )
        db.commit()

    with session_factory() as db:
        later = _NOW + timedelta(minutes=31)
        assert repo.get_active_auth_session(db, "jti-3", later) is None


def test_revoke_all_is_the_kill_switch(session_factory: sessionmaker[OrmSession]) -> None:
    with session_factory() as db:
        target = _learner(db, "kid")
        other = _learner(db, "other-kid")
        exp = _NOW + timedelta(minutes=30)
        repo.create_auth_session(db, learner_id=target.id, jti="k1", kind="child", expires_at=exp)
        repo.create_auth_session(db, learner_id=target.id, jti="k2", kind="child", expires_at=exp)
        repo.create_auth_session(db, learner_id=other.id, jti="o1", kind="child", expires_at=exp)
        db.commit()
        target_id = target.id

    with session_factory() as db:
        revoked = repo.revoke_all_sessions_for_learner(db, target_id, _NOW)
        db.commit()
        assert revoked == 2  # both of the target's sessions

    with session_factory() as db:
        assert repo.get_active_auth_session(db, "k1", _NOW) is None
        assert repo.get_active_auth_session(db, "k2", _NOW) is None
        # The other learner's session is untouched.
        assert repo.get_active_auth_session(db, "o1", _NOW) is not None


def test_jti_is_unique(session_factory: sessionmaker[OrmSession]) -> None:
    with session_factory() as db:
        learner = _learner(db, "L4")
        exp = _NOW + timedelta(minutes=30)
        repo.create_auth_session(
            db, learner_id=learner.id, jti="dup", kind="parent", expires_at=exp
        )
        repo.create_auth_session(
            db, learner_id=learner.id, jti="dup", kind="parent", expires_at=exp
        )
        with pytest.raises(IntegrityError):
            db.commit()
