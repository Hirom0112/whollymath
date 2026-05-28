"""Persistence repositories — the ONLY place DB queries live (Slice PL.1).

CLAUDE.md §7 and ARCHITECTURE.md §14 invariant 5 are explicit: services call
repositories, repositories own the queries, and no business logic leaks in here.
Every function below takes a SQLAlchemy ORM ``Session`` and does one bounded read
or write against the Slice-1.8 models (``app.db.models``); none of them decides
mastery, correctness, or transitions (that is the tutor/mastery/policy layers'
job) and none of them opens, commits, or closes the session — the CALLER owns the
unit-of-work boundary, so the service can batch a turn's writes into one commit
and so persistence stays OFF the decision path (ARCHITECTURE.md §14 invariant 7:
session/mastery writes happen alongside or AFTER the response).

Why this matters for invariant 7: because these are flush-free, commit-free pure
queries, the service can run the whole deterministic verify/mastery/policy turn,
build the response, and only THEN call these to record what happened. A failure
here can be caught and swallowed by the caller without ever having mutated the
turn's outcome.

No SymPy, no LLM — those live in ``domain/`` and ``llm/`` (CLAUDE.md §8.1/§8.2).
SQLAlchemy 2.0 typed style (``select`` + typed ``Mapped`` columns), matching
``models.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import selectinload

from app.db.models import InteractionEvent, Learner, MasteryState, Session, Turn


@dataclass(frozen=True)
class EventRow:
    """One interaction event as the repository ingests it (Slice PL.2).

    A small typed carrier for a batch ``persist_events`` write so the repository takes a
    structured list rather than parallel arrays — the ingest service builds these from the
    validated ``InteractionEventIn`` wire schema (the schema stays an API-layer concern; the
    repository speaks this plain dataclass). The session/learner ids are NOT on the row because
    every event in a batch shares them (they are passed once to ``persist_events``).
    """

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    client_ts: datetime | None = None


def get_or_create_learner(db: OrmSession, session_id: str) -> Learner:
    """Return the learner for an opaque external ``session_id``, creating it if new.

    ``session_id`` is the learner's external key (the browser-session id the
    frontend sends in place of auth — ``Learner.session_id``, TECH_STACK §9), NOT a
    tutoring ``Session`` row id. The lookup is by that unique column, so calling
    this twice for the same id returns the same learner — idempotent, which is what
    lets a resumed/restarted server re-find a learner without minting duplicates.

    The new learner is ``add``-ed but NOT committed: the caller owns the
    transaction boundary (so a whole start/turn can commit atomically). Callers that
    need the generated ``id`` immediately should ``flush``.
    """
    existing = db.scalars(select(Learner).where(Learner.session_id == session_id)).first()
    if existing is not None:
        return existing
    learner = Learner(session_id=session_id)
    db.add(learner)
    return learner


def get_learner(db: OrmSession, session_id: str) -> Learner | None:
    """Return the learner for an opaque external ``session_id``, or ``None`` if unknown.

    The read-only sibling of ``get_or_create_learner`` — the resume path uses it so a
    rehydrate of an id we never saw returns ``None`` (start-fresh) instead of minting an
    empty learner.
    """
    return db.scalars(select(Learner).where(Learner.session_id == session_id)).first()


def create_session(db: OrmSession, *, learner_id: int, route_key: str | None = None) -> Session:
    """Open a new tutoring ``Session`` row for a learner and return it.

    ``route_key`` is the Turn-0 route the session started in (a tutor
    ``RouteOption.key``); it is persisted so a resume after a restart can re-derive
    the session's goal KC (Slice PL.1.2). ``ended_at`` is left NULL (the session is
    open until ``end_session`` stamps it). ``add``-ed, not committed — the caller
    owns the unit of work.
    """
    session = Session(learner_id=learner_id, route_key=route_key)
    db.add(session)
    return session


def end_session(db: OrmSession, session_id: int) -> None:
    """Stamp a session's ``ended_at`` to now (UTC), closing it.

    A no-op if the id is unknown — closing a session that does not exist is not an
    error worth raising on a teardown path. Not committed (caller's boundary).
    """
    session = db.get(Session, session_id)
    if session is None:
        return
    session.ended_at = datetime.now(UTC)


def persist_turn(
    db: OrmSession,
    *,
    session_id: int,
    turn_index: int,
    problem_id: str,
    action: str,
    correct: bool,
    error_type: str | None,
    surface_state: str,
    state_transition: str | None,
    latency_ms: int,
    hint_used: bool,
) -> Turn:
    """Persist one ``Turn`` row from the already-decided turn fields.

    The values map 1:1 onto the Turn columns (``models.py``): the verifier's
    ``correct``/``error_type`` verdict, the surface state the turn happened in, the
    applied transition label (if any), the timing, and the hint flag. This records a
    turn that has ALREADY been verified, scored, and routed — it never decides any of
    those (CLAUDE.md §8.2). ``add``-ed, not committed (caller's boundary).
    """
    turn = Turn(
        session_id=session_id,
        turn_index=turn_index,
        problem_id=problem_id,
        action=action,
        correct=correct,
        error_type=error_type,
        surface_state=surface_state,
        state_transition=state_transition,
        latency_ms=latency_ms,
        hint_used=hint_used,
    )
    db.add(turn)
    return turn


def upsert_mastery_state(
    db: OrmSession,
    *,
    learner_id: int,
    kc_id: str,
    bkt_probability: float,
    attempt_count: int,
    hint_count: int,
    unscaffolded_correct_count: int,
    confirmed: bool = False,
) -> MasteryState:
    """Insert or update the (learner, kc) mastery row to the supplied values.

    One row per (learner, kc) — the model declares ``UniqueConstraint(learner_id,
    kc_id)`` (models.py), so this looks the row up on that pair and updates it in
    place when present, inserting only on first sight. The values are the mastery
    model's current readout for the KC (the BKT probability plus the §3.4 counts the
    rules range over, and whether the S5 probe has confirmed it); this repository
    stores them, it does not compute them (CLAUDE.md §7 — the counting lives in the
    service, the math in ``mastery/``).

    ``confirmed`` is sticky by construction at the call site: the service passes
    ``True`` once the probe has been passed and never re-derives it downward here, so
    a later non-probe turn's upsert (which passes the still-true confirmed flag) keeps
    it set.

    ``add``-ed/updated, not committed (caller's boundary).
    """
    row = db.scalars(
        select(MasteryState).where(
            MasteryState.learner_id == learner_id, MasteryState.kc_id == kc_id
        )
    ).first()
    if row is None:
        row = MasteryState(learner_id=learner_id, kc_id=kc_id)
        db.add(row)
    row.bkt_probability = bkt_probability
    row.attempt_count = attempt_count
    row.hint_count = hint_count
    row.unscaffolded_correct_count = unscaffolded_correct_count
    row.confirmed = confirmed
    return row


def load_open_session(db: OrmSession, session_id: int) -> Session | None:
    """Load an OPEN session (``ended_at IS NULL``) by id, with its turns eager-loaded.

    Returns ``None`` when the id is unknown OR the session has already ended — the
    resume path only cares about a session that is still open (a server restart left
    the in-memory ``_LiveSession`` gone but the DB row open). ``selectinload`` pulls
    the turns in one extra query so the caller can read history without a lazy-load
    surprise after the session closes; ``Turn.turns`` is already ordered by
    ``turn_index`` in the model relationship.
    """
    return db.scalars(
        select(Session)
        .where(Session.id == session_id, Session.ended_at.is_(None))
        .options(selectinload(Session.turns))
    ).first()


def load_open_session_for_learner(db: OrmSession, learner_id: int) -> Session | None:
    """The learner's most recent OPEN session (``ended_at IS NULL``), turns eager-loaded.

    A learner keyed by an opaque session id has one sitting in practice, but we order by
    ``started_at`` descending and take the latest open one defensively. ``None`` when the
    learner has no open session (all ended, or none yet) — the resume path then starts fresh.
    """
    return db.scalars(
        select(Session)
        .where(Session.learner_id == learner_id, Session.ended_at.is_(None))
        .order_by(Session.started_at.desc())
        .options(selectinload(Session.turns))
    ).first()


def load_mastery_states(db: OrmSession, learner_id: int) -> list[MasteryState]:
    """Load all of a learner's per-KC ``MasteryState`` rows.

    The resume path reads these to re-seed a rehydrated session's per-KC priors and
    confirmed-KC set (so progress survives a restart). Returns an empty list for a
    learner with no recorded mastery yet.
    """
    return list(db.scalars(select(MasteryState).where(MasteryState.learner_id == learner_id)).all())


def persist_event(
    db: OrmSession,
    *,
    session_row_id: int | None,
    learner_id: int | None,
    event_type: str,
    payload: dict[str, Any],
    client_ts: datetime | None,
) -> InteractionEvent:
    """Persist one raw ``InteractionEvent`` row (Slice PL.2).

    Maps the supplied event fields 1:1 onto the InteractionEvent columns (``models.py``).
    ``session_row_id``/``learner_id`` are nullable on purpose — telemetry is lenient, so an
    event for an unknown session/learner still records (the FKs are simply left NULL). ``server_ts``
    is stamped by the column's Python-side UTC default. ``add``-ed, not committed (caller's
    boundary) — and crucially this is reached OFF the turn loop (ARCHITECTURE.md §14 invariant 7),
    so a failure here is the ingest caller's to swallow, never the turn's.
    """
    event = InteractionEvent(
        session_id=session_row_id,
        learner_id=learner_id,
        event_type=event_type,
        payload=payload,
        client_ts=client_ts,
    )
    db.add(event)
    return event


def persist_events(
    db: OrmSession,
    *,
    session_row_id: int | None,
    learner_id: int | None,
    events: Sequence[EventRow],
) -> int:
    """Persist a batch of ``InteractionEvent`` rows and return the number added (Slice PL.2).

    Every event in the batch shares the same ``session_row_id``/``learner_id`` (they came in
    on one ``/events`` POST for one session). Each ``EventRow`` is mapped via ``persist_event``;
    the count returned is how many rows were ``add``-ed. ``add``-ed, not committed — the ingest
    service commits the whole batch as one unit of work off the turn loop (invariant 7).
    """
    for row in events:
        persist_event(
            db,
            session_row_id=session_row_id,
            learner_id=learner_id,
            event_type=row.event_type,
            payload=row.payload,
            client_ts=row.client_ts,
        )
    return len(events)


__all__ = [
    "EventRow",
    "create_session",
    "end_session",
    "get_learner",
    "get_or_create_learner",
    "load_mastery_states",
    "load_open_session",
    "load_open_session_for_learner",
    "persist_event",
    "persist_events",
    "persist_turn",
    "upsert_mastery_state",
]
