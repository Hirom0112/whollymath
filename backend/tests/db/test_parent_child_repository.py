"""Tests for the parent/child account repository (Slice auth/parent-child).

The repository is the ONLY place DB queries live (CLAUDE.md §7). This pins the
contract the auth layer depends on for verifiable-parental-consent accounts:

  - a PARENT is a Learner with role="parent", created via email/password (unverified
    until they verify) or Google (verified by Google); one parent per email is
    enforced by the unique session_id.
  - a CHILD is a Learner owned by ``parent_id``; its login username is unique only
    WITHIN the parent's household; reads are ownership-scoped so one parent can never
    read another family's child (the BOLA guard, OWASP API #1).
  - consent is recorded as an auditable row at child creation (COPPA, RESEARCH.md).

Runs against an in-memory SQLite engine + ``create_all`` (no Postgres, CLAUDE.md
§8.7), matching ``tests/db/test_google_sub_repository.py``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.db.models import ConsentRecord, Learner
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import IntegrityError
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


# ── Parent accounts ──────────────────────────────────────────────────────────


def test_create_parent_with_password_is_parent_and_unverified(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Email/password parent: role="parent", email normalized, unverified, hash stored."""
    with session_factory() as db:
        parent = repo.create_parent_with_password(
            db, email="  Parent@Example.COM ", password_hash="argon2$hash"
        )
        db.commit()
        assert parent.role == "parent"
        assert parent.email == "parent@example.com"  # normalized
        assert parent.email_verified is False  # consent anchor not yet established
        assert parent.password_hash == "argon2$hash"  # only the hash is stored


def test_get_parent_by_email_is_role_scoped_and_normalized(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Lookup matches the parent regardless of case, and never returns a non-parent."""
    with session_factory() as db:
        repo.create_parent_with_password(db, email="mom@example.com", password_hash="h")
        # A student that happens to carry the same email label must NOT be returned.
        db.add(Learner(session_id="s1", email="mom@example.com", role="student"))
        db.commit()

    with session_factory() as db:
        found = repo.get_parent_by_email(db, "MOM@example.com")
        assert found is not None
        assert found.role == "parent"


def test_duplicate_parent_email_collides(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A second signup with the same email collides (unique session_id), not duplicates."""
    with session_factory() as db:
        repo.create_parent_with_password(db, email="dup@example.com", password_hash="h1")
        db.commit()

    with session_factory() as db:
        repo.create_parent_with_password(db, email="dup@example.com", password_hash="h2")
        with pytest.raises(IntegrityError):
            db.commit()


def test_get_or_create_parent_by_google_sub_is_idempotent_and_verified(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Google parent: idempotent on sub, role="parent", email pre-verified by Google."""
    with session_factory() as db:
        first = repo.get_or_create_parent_by_google_sub(db, "psub-1", email="g@ex.com")
        db.commit()
        first_id = first.id
        assert first.role == "parent"
        assert first.email_verified is True  # Google asserts a verified email

    with session_factory() as db:
        again = repo.get_or_create_parent_by_google_sub(db, "psub-1")
        db.commit()
        assert again.id == first_id

    with session_factory() as db:
        rows = db.query(Learner).filter_by(google_sub="psub-1").all()
        assert len(rows) == 1  # idempotent: no duplicate parent row


# ── Child accounts + ownership ───────────────────────────────────────────────


def _make_parent(db: OrmSession, email: str) -> Learner:
    parent = repo.create_parent_with_password(db, email=email, password_hash="h")
    db.flush()  # need parent.id for the child FK
    return parent


def test_create_child_links_to_parent_and_keeps_student_role(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A child is a student Learner owned by the parent, carrying its login credential."""
    with session_factory() as db:
        parent = _make_parent(db, "p1@ex.com")
        child = repo.create_child(
            db,
            parent_id=parent.id,
            public_id="pub-aaa",
            display_name="Mia",
            grade_level=6,
            locale="es-MX",
            child_username="mathmia",
            pin_hash="argon2$pin",
        )
        db.commit()
        assert child.role == "student"  # identity gates surfaces only (invariant 8)
        assert child.parent_id == parent.id
        assert child.public_id == "pub-aaa"
        assert child.locale == "es-MX"
        assert child.pin_hash == "argon2$pin"
        assert child.failed_pin_attempts == 0  # default, no failures yet


def test_get_children_of_parent_returns_only_own_children(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A parent sees their children and only their children, oldest first."""
    with session_factory() as db:
        p1 = _make_parent(db, "a@ex.com")
        p2 = _make_parent(db, "b@ex.com")
        repo.create_child(
            db,
            parent_id=p1.id,
            public_id="c1",
            display_name="One",
            grade_level=6,
            locale="en",
            child_username="one",
            pin_hash="h",
        )
        repo.create_child(
            db,
            parent_id=p1.id,
            public_id="c2",
            display_name="Two",
            grade_level=6,
            locale="en",
            child_username="two",
            pin_hash="h",
        )
        repo.create_child(
            db,
            parent_id=p2.id,
            public_id="c3",
            display_name="Other",
            grade_level=6,
            locale="en",
            child_username="other",
            pin_hash="h",
        )
        db.commit()
        p1_id = p1.id

    with session_factory() as db:
        kids = repo.get_children_of_parent(db, p1_id)
        assert [k.display_name for k in kids] == ["One", "Two"]


def test_get_child_for_parent_enforces_ownership(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """BOLA guard: a parent cannot fetch another family's child by public_id."""
    with session_factory() as db:
        p1 = _make_parent(db, "owner@ex.com")
        p2 = _make_parent(db, "attacker@ex.com")
        repo.create_child(
            db,
            parent_id=p1.id,
            public_id="victim-pub",
            display_name="Kid",
            grade_level=6,
            locale="en",
            child_username="kid",
            pin_hash="h",
        )
        db.commit()
        p1_id, p2_id = p1.id, p2.id

    with session_factory() as db:
        # The owner can read it.
        assert repo.get_child_for_parent(db, p1_id, "victim-pub") is not None
        # Another parent asking for the same public_id gets None — authorization is
        # enforced in the query, not trusted from the request.
        assert repo.get_child_for_parent(db, p2_id, "victim-pub") is None


def test_child_username_unique_per_parent_but_reusable_across_families(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Two families may both use "mathmia"; one family cannot reuse it twice."""
    with session_factory() as db:
        p1 = _make_parent(db, "fam1@ex.com")
        p2 = _make_parent(db, "fam2@ex.com")
        repo.create_child(
            db,
            parent_id=p1.id,
            public_id="f1c1",
            display_name="A",
            grade_level=6,
            locale="en",
            child_username="mathmia",
            pin_hash="h",
        )
        # Same username under a DIFFERENT parent is allowed (per-household namespace).
        repo.create_child(
            db,
            parent_id=p2.id,
            public_id="f2c1",
            display_name="B",
            grade_level=6,
            locale="en",
            child_username="mathmia",
            pin_hash="h",
        )
        db.commit()
        p1_id = p1.id

    with session_factory() as db:
        # Same username under the SAME parent collides on the unique index.
        repo.create_child(
            db,
            parent_id=p1_id,
            public_id="f1c2",
            display_name="C",
            grade_level=6,
            locale="en",
            child_username="mathmia",
            pin_hash="h",
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_get_child_by_parent_and_username_requires_parent(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Child login is namespaced: the lookup needs the parent_id, not a bare username."""
    with session_factory() as db:
        p1 = _make_parent(db, "n1@ex.com")
        p2 = _make_parent(db, "n2@ex.com")
        repo.create_child(
            db,
            parent_id=p1.id,
            public_id="np1",
            display_name="Nam",
            grade_level=6,
            locale="en",
            child_username="sameuser",
            pin_hash="h",
        )
        db.commit()
        p1_id, p2_id = p1.id, p2.id

    with session_factory() as db:
        assert repo.get_child_by_parent_and_username(db, p1_id, "sameuser") is not None
        # The wrong parent never resolves the username.
        assert repo.get_child_by_parent_and_username(db, p2_id, "sameuser") is None


# ── Consent ──────────────────────────────────────────────────────────────────


def test_record_consent_stamps_auditable_row(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Creating a child + recording consent commit together as one auditable unit."""
    with session_factory() as db:
        parent = _make_parent(db, "consent@ex.com")
        child = repo.create_child(
            db,
            parent_id=parent.id,
            public_id="cc1",
            display_name="Kid",
            grade_level=6,
            locale="en",
            child_username="kid",
            pin_hash="h",
        )
        db.flush()
        repo.record_consent(
            db,
            parent_id=parent.id,
            child_id=child.id,
            policy_version="2026-06-03",
            ip_address="203.0.113.7",
        )
        db.commit()
        parent_id = parent.id

    with session_factory() as db:
        rows = db.query(ConsentRecord).filter_by(parent_id=parent_id).all()
        assert len(rows) == 1
        assert rows[0].policy_version == "2026-06-03"
        assert rows[0].method == "parent_account"  # default VPC method
        assert rows[0].ip_address == "203.0.113.7"


def test_deleting_parent_cascades_to_children(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """COPPA deletion right: deleting a parent removes their children (ORM cascade)."""
    with session_factory() as db:
        parent = _make_parent(db, "del@ex.com")
        repo.create_child(
            db,
            parent_id=parent.id,
            public_id="del-c1",
            display_name="Kid",
            grade_level=6,
            locale="en",
            child_username="kid",
            pin_hash="h",
        )
        db.commit()
        parent_obj = db.get(Learner, parent.id)
        assert parent_obj is not None
        db.delete(parent_obj)
        db.commit()

    with session_factory() as db:
        assert db.query(Learner).filter_by(child_username="kid").count() == 0
