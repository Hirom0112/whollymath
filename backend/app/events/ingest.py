"""Best-effort persistence of buffered interaction events, OFF the turn loop (Slice PL.2).

ARCHITECTURE.md §14 invariant 7 is the hard rule here: "Telemetry never blocks a turn —
event capture happens off the turn loop. Fire-and-forget with retry; never blocking an
endpoint." This module is the persistence half of that: given a session factory and a batch
of already-validated events, it opens a short-lived DB session, writes the rows via the
repository (the ONLY place queries live, CLAUDE.md §7), commits, and is BEST-EFFORT — any
exception is caught, logged, and swallowed so it can NEVER propagate to the caller and break
the request that triggered it.

It deliberately knows nothing about the turn loop. It contains NO business logic, NO SymPy,
NO LLM, and never reaches into verify/mastery/policy — it only records (a structural import
guard test pins this). The mapping from the wire ``InteractionEventIn`` schema to the
repository's ``EventRow`` happens upstream in the API layer (the SessionStore), so this module
imports neither the API schemas nor the service: the dependency direction stays one-way
(API → events → repository), with nothing importing back into the turn loop.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.db import repositories as repo
from app.db.repositories import EventRow

# Swallowed-failure channel: invariant 7 says a telemetry write must never break the request,
# so every failure below is logged here rather than raised.
_log = logging.getLogger(__name__)


def ingest_events(
    session_factory: sessionmaker[OrmSession] | None,
    *,
    session_id: str,
    events: Sequence[EventRow],
    session_row_id: int | None = None,
    learner_id: int | None = None,
) -> int:
    """Persist a batch of interaction events best-effort; return the count attempted-persisted.

    Opens its own short-lived DB session from ``session_factory``, writes every event via
    ``repo.persist_events`` (linking each to ``session_row_id``/``learner_id`` when known — both
    nullable, telemetry is lenient), and commits the batch as one unit of work. The return value
    is how many rows the write attempted, not a durability guarantee: this is fire-and-forget
    capture off the turn loop (invariant 7).

    Two graceful non-error paths:

      - ``session_factory is None`` → no DB is wired (the in-memory demo). Nothing is persisted;
        returns 0. This is not a failure, just the no-DB mode.
      - any exception during open/write/commit → caught, logged, and swallowed. The function
        returns 0 (nothing durably attempted) rather than re-raising, because telemetry must
        NEVER error the request that produced it (the §14 invariant-7 contract).

    ``session_id`` is carried only for log context (so a swallowed failure names the session);
    the row linkage uses the resolved ``session_row_id``/``learner_id`` the caller looked up.
    """
    if session_factory is None:
        return 0
    if not events:
        return 0
    try:
        with session_factory() as db:
            count = repo.persist_events(
                db,
                session_row_id=session_row_id,
                learner_id=learner_id,
                events=events,
            )
            db.commit()
            return count
    except Exception:  # noqa: BLE001 — invariant 7: a telemetry write must never break the request.
        _log.exception("event ingest failed for session %s; events dropped (off loop)", session_id)
        return 0


__all__ = ["ingest_events"]
