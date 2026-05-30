"""Tests for persistence wired into the live turn loop — OFF the decision path (Slice PL.1).

The load-bearing property (ARCHITECTURE.md §14 invariant 7): session/mastery writes
happen ALONGSIDE or AFTER the response, never on the sub-100ms decision path, and
persistence is observe/record-only — a turn's ``TurnResponse`` is identical whether or
not a ``session_factory`` is wired. These tests pin exactly that:

  - EQUIVALENCE: the same session walked through ``process_turn`` with a factory and
    without yields byte-identical responses (persistence changes no outcome).
  - mastery accumulates: turns persist/upsert MasteryState; the latest BKT prob +
    counts are stored once per (learner, kc).
  - failure tolerance: a factory whose commit raises does NOT break the turn.
  - resume: an open session's persisted mastery rehydrates so a resumed session
    carries the prior BKT/confirmed forward.

All run against an in-memory SQLite engine + ``create_all`` (no Postgres, CLAUDE.md
§8.7), matching ``tests/db/``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.schemas import ActionType, SurfaceState, TurnRequest
from app.api.service import SessionStore
from app.db.engine import create_all, create_session_factory
from app.db.models import MasteryState, Turn
from app.domain.knowledge_components import KnowledgeComponentId
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_ADDITION_ROUTE_KEY = "combine"
_ADDITION_CORRECT_ANSWER = "7/12"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    """A shared in-memory SQLite engine + schema, as a session factory."""
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def _turn(session_id: str, problem_id: str, answer: str = _ADDITION_CORRECT_ANSWER) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.SUBMIT_ANSWER,
        submitted_answer=answer,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=3000,
        hint_used=False,
    )


def _walk(store: SessionStore, n_turns: int, *, session_id: str | None = None) -> list[object]:
    """Start a session and submit ``n_turns`` correct answers; return the responses.

    ``session_id`` may be pinned so two stores walk the SAME session: the problem seed is
    derived from the session id (Fix A), so an equivalence test must hold the id fixed to
    isolate the variable under test (the factory/predictor/arm), not the session identity.
    """
    started = store.start(_ADDITION_ROUTE_KEY, session_id=session_id)
    responses: list[object] = []
    session_id = started.session_id
    problem_id = started.problem.problem_id
    for _ in range(n_turns):
        resp = store.process_turn(_turn(session_id, problem_id))
        responses.append(resp)
        assert resp.next_problem is not None
        problem_id = resp.next_problem.problem_id
    return responses


def test_responses_identical_with_and_without_factory(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """EQUIVALENCE: persistence is observe-only — responses match a no-DB run exactly."""
    plain = SessionStore()
    persisted = SessionStore(session_factory=session_factory)

    fixed_id = "equivsession0000000000000000pers"
    plain_responses = _walk(plain, 6, session_id=fixed_id)
    persisted_responses = _walk(persisted, 6, session_id=fixed_id)

    assert plain_responses == persisted_responses


def test_turns_and_mastery_are_persisted(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Each submit persists a Turn; mastery is upserted once per (learner, kc)."""
    store = SessionStore(session_factory=session_factory)
    _walk(store, 4)

    with session_factory() as db:
        turns = db.query(Turn).order_by(Turn.turn_index).all()
        assert len(turns) == 4
        assert [t.turn_index for t in turns] == [0, 1, 2, 3]
        assert all(t.action == ActionType.SUBMIT_ANSWER.value for t in turns)

        mastery = db.query(MasteryState).all()
        # One row per (learner, kc) — no duplicates despite multiple turns per KC.
        keys = [(m.learner_id, m.kc_id) for m in mastery]
        assert len(keys) == len(set(keys))
        # Every persisted mastery row has a real attempt count from the walk.
        assert all(m.attempt_count >= 1 for m in mastery)


def test_mastery_counts_reflect_latest_state(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """The stored counts equal the in-session tally after the last turn (upsert, not append)."""
    store = SessionStore(session_factory=session_factory)
    _walk(store, 5)

    with session_factory() as db:
        rows = db.query(MasteryState).all()
        total_attempts = sum(m.attempt_count for m in rows)
        # Five answered turns ⇒ five attempts spread across the KCs the scheduler served
        # (one attempt per turn, tallied per KC). The total must equal the turns taken.
        assert total_attempts == 5
        # No hints were used, so no row records one. (Only the addition answers verify
        # correct against the fixed "7/12"; the count being a real, bounded tally — not a
        # duplicate-row artifact — is the upsert property under test.)
        assert all(m.hint_count == 0 for m in rows)
        assert all(0 <= m.unscaffolded_correct_count <= m.attempt_count for m in rows)


def test_commit_failure_does_not_break_the_turn(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A factory whose session raises on commit still returns the turn response (invariant 7)."""

    class _BoomSession:
        """A stand-in ORM session that explodes on commit but is otherwise inert."""

        def __init__(self, real: OrmSession) -> None:
            self._real = real

        def __getattr__(self, name: str) -> object:
            return getattr(self._real, name)

        def commit(self) -> None:
            raise RuntimeError("boom: simulated DB failure")

        def __enter__(self) -> _BoomSession:
            return self

        def __exit__(self, *exc: object) -> None:
            self._real.close()

    def boom_factory() -> _BoomSession:
        return _BoomSession(session_factory())

    store = SessionStore(session_factory=boom_factory)  # type: ignore[arg-type]
    started = store.start(_ADDITION_ROUTE_KEY)  # start persistence also fails-soft
    response = store.process_turn(_turn(started.session_id, started.problem.problem_id))
    assert response.correct is True
    assert response.next_problem is not None


def test_resume_carries_prior_mastery_forward(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A resumed open session rehydrates persisted mastery so progress is not lost."""
    store = SessionStore(session_factory=session_factory)
    started = store.start(_ADDITION_ROUTE_KEY)
    session_id = started.session_id
    problem_id = started.problem.problem_id
    for _ in range(4):
        resp = store.process_turn(_turn(session_id, problem_id))
        assert resp.next_problem is not None
        problem_id = resp.next_problem.problem_id

    # Read what was persisted for the addition KC (the route's goal KC).
    with session_factory() as db:
        rows = db.query(MasteryState).all()
        persisted_by_kc = {m.kc_id: m.bkt_probability for m in rows}
    assert persisted_by_kc  # something was recorded

    # Simulate a server restart: a brand-new store (empty in-memory map) over the SAME DB.
    fresh_store = SessionStore(session_factory=session_factory)
    resumed = fresh_store.resume(session_id)
    assert resumed is not None
    # The rehydrated session carries the persisted BKT priors forward for each KC.
    for kc_id, prob in persisted_by_kc.items():
        kc = KnowledgeComponentId(kc_id)
        assert fresh_store.prior_for(session_id, kc) == pytest.approx(prob)


def test_resume_unknown_session_returns_none(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Resuming an id with no open DB session yields None (caller starts fresh)."""
    store = SessionStore(session_factory=session_factory)
    assert store.resume("never-existed") is None


def test_no_factory_means_no_persistence() -> None:
    """Without a factory the store is pure in-memory; a fresh (restarted) store can't resume."""
    store = SessionStore()
    started = store.start(_ADDITION_ROUTE_KEY)
    store.process_turn(_turn(started.session_id, started.problem.problem_id))
    # An in-memory session is still resumable from the SAME store (it's just in the map)...
    assert store.resume(started.session_id) is not None
    # ...but a fresh store (simulated restart) with no DB has nothing to rehydrate from.
    assert SessionStore().resume(started.session_id) is None
