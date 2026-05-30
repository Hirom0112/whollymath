"""The first mastery star must be DURABLE — it survives a server restart (Slice AR.2).

AUDIT.md §6 blocker 2 (2026-05-29): "The 1★ is not durably recorded in the default run."
When a learner passes the S5 transfer probe the live loop sets ``confirmed`` only on the
in-memory ``_LiveSession`` (``service.py`` ``_probe_turn``); the DB write was an OPTIONAL
injected ``session_factory`` that defaulted OFF, so the confirmed mastery was lost on a
restart. PROJECT.md §3.4 makes mastery mean CONFIRMED (the probe passed), and that earned
state must persist — a resumed learner must not be re-probed on a KC they already mastered.

These tests pin the durability property end-to-end at the ``SessionStore`` seam (matching
``test_persistence_wiring.py``): drive a real session through the probe to a pass, then
assert (1) a ``mastery_state`` row with ``confirmed=True`` is persisted for that learner's
goal KC, and (2) a FRESHLY-constructed store over the SAME database (a simulated restart)
still sees that confirmed mastery — both the persisted row and the carried-forward live
``confirmed`` set after a ``resume``. SymPy decides every answer (we compute the correct
response from the served problem); no LLM, no mocks. In-memory SQLite + ``create_all`` (no
Postgres, CLAUDE.md §8.7), the established suite pattern.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api import app as app_module
from app.api.app import create_app
from app.api.schemas import ActionType, ProblemView, SurfaceState, TurnRequest, TurnResponse
from app.api.service import SessionStore
from app.db.engine import create_all, create_session_factory
from app.db.models import MasteryState
from app.domain.knowledge_components import KnowledgeComponentId
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sympy import Rational

_ADDITION_ROUTE_KEY = "combine"
_GOAL_KC = KnowledgeComponentId.ADDITION_UNLIKE


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    """A shared in-memory SQLite engine + schema, as a session factory (one DB across stores)."""
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def _fractions(statement: str) -> list[Rational]:
    return [Rational(int(p), int(q)) for p, q in re.findall(r"(\d+)/(\d+)", statement)]


def _correct_answer(problem: ProblemView) -> str:
    """The correct answer string for any served problem (practice or probe step).

    A ``ProblemView``-typed port of the dict-based ``_correct_answer`` in
    ``test_transfer_probe_live`` — same SymPy-derived logic, reading the view's attributes so
    the test drives the store directly (no ASGI round-trip) while still letting the real domain
    verifier judge every answer server-side (no answer leaks across the wire — §8.2)."""
    s = problem.statement
    if problem.answer_kind == "yes_no":
        fr = _fractions(s)
        if "Tim says" in s:  # reject step: is "a op b = c" right?
            value = fr[0] + fr[1] if "+" in s else fr[0] - fr[1]
            return "yes" if value == fr[2] else "no"
        if "greater than" in s:
            return "yes" if fr[0] > fr[1] else "no"
        if "into" in s and "took" in s:  # equivalence word problem
            pieces = int(re.search(r"into (\d+) equal", s).group(1))  # type: ignore[union-attr]
            taken = int(re.search(r"took (\d+)", s).group(1))  # type: ignore[union-attr]
            return "yes" if Rational(taken, pieces) == fr[0] else "no"
        return "yes" if fr[0] == fr[1] else "no"  # symbolic equivalence "is a the same as b?"
    if problem.surface_format == "number_line":
        seg = problem.tick_segments
        assert seg is not None
        fr = _fractions(s)
        value = fr[0] + fr[1] if "Add" in s else fr[0] - fr[1] if "Subtract" in s else fr[0]
        return f"{int(value * seg)}/{seg}"
    if "missing top" in s:
        assert problem.given_denominator is not None
        return f"{int(_fractions(s)[0] * problem.given_denominator)}/{problem.given_denominator}"
    fr = _fractions(s)  # symbolic arithmetic ("a + b = ?" / "what does a + b really equal?")
    value = fr[0] + fr[1] if "+" in s else fr[0] - fr[1]
    return f"{value.p}/{value.q}"


def _turn(session_id: str, problem: ProblemView, answer: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem.problem_id,
        action=ActionType.SUBMIT_ANSWER,
        submitted_answer=answer,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=6000,
        hint_used=False,
    )


def _drive_to_confirmed(
    store: SessionStore, *, max_turns: int = 80
) -> tuple[str, TurnResponse]:
    """Start the addition route and answer EVERY problem (practice and probe) correctly until
    the lesson completes (the goal KC is confirmed by passing the S5 probe). Returns the
    session id and the terminal lesson-complete response. Asserts a confirmed pass was reached
    within the bound (the lesson cannot loop forever — CP.B)."""
    started = store.start(_ADDITION_ROUTE_KEY)
    session_id = started.session_id
    problem = started.problem
    for _ in range(max_turns):
        response = store.process_turn(_turn(session_id, problem, _correct_answer(problem)))
        if response.lesson_complete:
            return session_id, response
        assert response.next_problem is not None
        problem = response.next_problem
    raise AssertionError("never reached a confirmed-mastery lesson_complete within the bound")


def _confirmed_kc_ids(factory: sessionmaker[OrmSession]) -> set[str]:
    with factory() as db:
        return {m.kc_id for m in db.query(MasteryState).all() if m.confirmed}


def test_probe_pass_persists_confirmed_mastery_row(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """Passing the transfer probe writes a ``mastery_state`` row with ``confirmed=True`` for the
    goal KC — the earned 1★ is durable, not in-memory only (AUDIT §6 blocker 2; PROJECT §3.4)."""
    store = SessionStore(session_factory=session_factory)
    _, terminal = _drive_to_confirmed(store)

    # The terminal turn reports the goal KC as confirmed-mastered in the wire snapshot...
    assert any(m.kc_id == _GOAL_KC and m.mastered for m in terminal.mastery)
    # ...and that confirmation is durably written to the row, not just held in memory.
    with session_factory() as db:
        row = (
            db.query(MasteryState)
            .filter(MasteryState.kc_id == _GOAL_KC.value)
            .one()
        )
        assert row.confirmed is True


def test_confirmed_mastery_survives_restart(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """A freshly-constructed store over the SAME DB (a simulated server restart) still sees the
    confirmed goal KC — the 1★ survives losing all in-memory state (AUDIT §6 blocker 2)."""
    store = SessionStore(session_factory=session_factory)
    session_id, _ = _drive_to_confirmed(store)
    assert _GOAL_KC.value in _confirmed_kc_ids(session_factory)

    # Simulate a restart: a brand-new store (empty in-memory map) over the same database.
    fresh = SessionStore(session_factory=session_factory)
    assert session_id not in fresh._sessions  # nothing carried in memory across the "restart"
    resumed = fresh.resume(session_id)
    assert resumed is not None
    # The rehydrated session carries the confirmed KC forward, so the learner is NOT re-probed
    # on a KC they already mastered (the durability property that motivates this slice).
    assert _GOAL_KC in resumed.confirmed


def test_default_app_persists_with_no_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The DEFAULT app — built by ``create_app()`` with NO ``DATABASE_URL`` — wires a durable
    persistence factory (a default on-disk SQLite store), so the 1★ survives a restart out of
    the box, with no Postgres required (AUDIT §6 blocker 2 — "off by default" is the bug).

    We point the default SQLite path at a tmp file and clear ``DATABASE_URL`` so the test does
    not touch a real DB or the repo's ``backend/data/`` dir; this exercises the default branch."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(app_module, "_DEFAULT_SQLITE_PATH", tmp_path / "whollymath.db")

    app = create_app()
    store = app.state.session_store
    factory = store.session_factory
    # The default app is NOT in-memory-only: it has a real persistence channel.
    assert factory is not None

    # And it is genuinely durable: a probe pass writes confirmed mastery that a SECOND app
    # built over the same default store (a restart) still sees.
    session_id, _ = _drive_to_confirmed(store)
    assert _GOAL_KC.value in _confirmed_kc_ids(factory)

    restarted = create_app().state.session_store
    resumed = restarted.resume(session_id)
    assert resumed is not None
    assert _GOAL_KC in resumed.confirmed
