"""Tests for the study-plan wiring on the persistence layer (Slice 6.x — spaced repetition).

``SessionStore.study_plan_for_learner`` reads a learner's persisted MasteryState rows and runs
the planner: a confirmed skill whose retention has decayed (an OLD ``updated_at``) surfaces as a
DUE REVIEW; the next prerequisite-unlocked skill is suggested. This is the cross-session call
site where spacing actually has effect (a single live session has no time gap). SQLite test DB,
no Postgres (CLAUDE.md §9).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from app.api.service import SessionStore
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.domain.knowledge_components import KnowledgeComponentId as KCId
from app.mastery.retention import DEFAULT_HALF_LIFE
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    engine: Engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def _seed(
    factory: sessionmaker[OrmSession],
    *,
    kc: KCId,
    confirmed: bool,
    last_practiced: datetime,
) -> int:
    """Persist one MasteryState row for a fresh learner; return the learner id."""
    with factory() as db:
        learner = repo.get_or_create_learner(db, "sess-study-plan")
        db.flush()
        repo.upsert_mastery_state(
            db,
            learner_id=learner.id,
            kc_id=kc.value,
            bkt_probability=0.9,
            attempt_count=3,
            hint_count=0,
            unscaffolded_correct_count=2,
        )
        # The planner's "due" decision keys on updated_at; set it explicitly to simulate a gap.
        from app.db.models import MasteryState

        row = db.query(MasteryState).filter_by(learner_id=learner.id, kc_id=kc.value).one()
        row.confirmed = confirmed
        row.updated_at = last_practiced
        db.commit()
        return learner.id


def test_no_factory_returns_empty_plan() -> None:
    """Without persistence there is no cross-session state → an empty plan, never an error."""
    plan = SessionStore().study_plan_for_learner(1, _NOW)
    assert plan.due_reviews == []
    assert plan.unlocked_next == []
    assert plan.recommended is None


def test_fresh_confirmed_root_unlocks_the_next_skill(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A just-confirmed number-line → no review due, and equivalence is the unlocked next skill."""
    learner_id = _seed(
        session_factory, kc=KCId.NUMBER_LINE_PLACEMENT, confirmed=True, last_practiced=_NOW
    )
    store = SessionStore(session_factory=session_factory)
    plan = store.study_plan_for_learner(learner_id, _NOW)
    assert plan.due_reviews == []  # fresh
    assert KCId.EQUIVALENCE.value in plan.unlocked_next
    assert plan.recommended == KCId.EQUIVALENCE.value


def test_decayed_confirmed_skill_surfaces_as_a_due_review(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A confirmed skill last practiced long ago decays below the bar → recommended for review."""
    learner_id = _seed(
        session_factory,
        kc=KCId.NUMBER_LINE_PLACEMENT,
        confirmed=True,
        last_practiced=_NOW - 4 * DEFAULT_HALF_LIFE,
    )
    store = SessionStore(session_factory=session_factory)
    plan = store.study_plan_for_learner(learner_id, _NOW)
    assert plan.due_reviews == [KCId.NUMBER_LINE_PLACEMENT.value]
    # a due review takes priority over introducing the unlocked new skill
    assert plan.recommended == KCId.NUMBER_LINE_PLACEMENT.value
