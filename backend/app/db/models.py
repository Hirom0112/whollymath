"""SQLAlchemy ORM models for the core WhollyMath tables (Slice 1.8).

These four tables are exactly the structured data TECH_STACK §4 says we store:

  - ``Learner``      — the identity a session hangs off. TECH_STACK §9 commits to
                       NO authentication in v1: a learner is just a session id, so
                       this row is a thin handle (a generated id + when we first
                       saw it), nothing more.
  - ``Session``      — one tutoring sitting belonging to a learner. TECH_STACK §4
                       "Learner sessions" are the top-level unit of the trace.
  - ``Turn``         — one learner action inside a session. TECH_STACK §4 names
                       the per-turn fields verbatim: the sequence of
                       (turn / problem / action / state_transition / timing). The
                       columns below are that sequence plus the correctness +
                       error-type + hint signals the mastery model and the
                       HelpNeed predictor read (ARCHITECTURE.md §6, §8).
  - ``MasteryState`` — per learner, per KC: the BKT probability and the counts
                       the mastery-model augmentation rules need (ARCHITECTURE.md
                       §6: unscaffolded-correct and hint counts). TECH_STACK §4
                       "Mastery state per learner per KC".

Design constraints honored here:

  - **Models are thin.** No queries, no business logic — those live in
    repositories in a later slice (CLAUDE.md §7, ARCHITECTURE.md §14 invariant 5).
    These classes only declare shape.
  - **Portable column types.** Prod is PostgreSQL (TECH_STACK §4) but unit tests
    run against in-memory SQLite, so every type here is one both backends accept:
    ``String`` for ids and the KC value (the ``KnowledgeComponentId`` StrEnum
    serializes to its catalog string), ``Boolean``, ``Integer``, ``Float``, and
    ``DateTime(timezone=True)``. No Postgres-only types (UUID, JSONB, ENUM) — those
    would diverge between test and prod. Timestamps default in Python (``UTC``) so
    the default is identical on both backends rather than relying on a server clock.
  - **Deferred** (NOT modeled here — they land with the harness in Weeks 2/5,
    TECH_STACK §4): persona-run-results and baseline-comparison tables.

Defer reasons recorded so the decision log is intact (CLAUDE.md §8.4).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    """Timezone-aware UTC now, used as the Python-side column default.

    Defining the default in Python (not via a DB ``server_default``) keeps the
    behavior identical between the SQLite test engine and prod Postgres, instead
    of depending on each backend's clock function. ``UTC`` everywhere avoids the
    naive/aware comparison bugs that bite when one row is tz-aware and another
    isn't.
    """
    return datetime.now(UTC)


class Learner(Base):
    """A learner identity — session-id-based, no auth (TECH_STACK §9).

    v1 deliberately has no authentication, so a learner is just an opaque id we
    mint on first contact plus when we first saw them. Real auth (SSO, parent
    accounts) is post-launch and flagged in the limitations memo (TECH_STACK §9).
    """

    __tablename__ = "learner"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The externally-visible session id the frontend sends in place of auth. Unique
    # so the same browser session maps to exactly one learner row (TECH_STACK §9).
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # ORM-side conveniences only; the FK lives on the child. cascade keeps a
    # learner's whole trace deletable as a unit in tests/fixtures.
    sessions: Mapped[list[Session]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )
    mastery_states: Mapped[list[MasteryState]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )


class Session(Base):
    """One tutoring sitting belonging to a learner (TECH_STACK §4 "Learner sessions").

    The top-level unit of the interaction trace; ``Turn`` rows hang off it in
    order. ``ended_at`` is nullable because a session is open until it closes.
    """

    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    learner: Mapped[Learner] = relationship(back_populates="sessions")
    turns: Mapped[list[Turn]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Turn.turn_index",  # turns read back in their played order
    )


class Turn(Base):
    """One learner action within a session — the unit TECH_STACK §4 enumerates.

    TECH_STACK §4 stores the per-session sequence of
    ``(turn_id, problem_id, action, state_transition, timing)``. This row is that
    tuple, plus the correctness / error-type / hint signals the mastery model
    (ARCHITECTURE.md §6) and the HelpNeed predictor (ARCHITECTURE.md §8) consume.

    Nullable fields are nullable for a reason: ``error_type`` is only set on a
    wrong answer; ``state_transition`` is only set on the turns that actually
    moved the surface state (most turns don't — refuse-rules keep transitions
    sparse, ARCHITECTURE.md §7).
    """

    __tablename__ = "turn"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # 0-based position of this turn within its session — the sequence order.
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Which problem was presented (the problem-generator id; see Slice 1.3).
    problem_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # What the learner did (submit / hint-request / etc.) as a short tag.
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # SymPy's verdict (ARCHITECTURE.md §9) — never an LLM's (invariant 2).
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Named misconception/error pattern, only present when the answer was wrong.
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The surface state the learner was in for this turn (S1–S5; ARCHITECTURE.md §7).
    surface_state: Mapped[str] = mapped_column(String(16), nullable=False)
    # The transition triggered by this turn, if any (labeled per refuse-rule 4).
    state_transition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Response timing — a top HelpNeed feature (ARCHITECTURE.md §8).
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # Whether scaffolding was used; gates the unscaffolded-correct mastery rule.
    hint_used: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="turns")


class MasteryState(Base):
    """Per-learner, per-KC mastery record (TECH_STACK §4 "Mastery state per learner per KC").

    Holds the BKT probability plus the counts the mastery-model augmentation rules
    read: total attempts, hinted attempts, and unscaffolded-correct attempts (the
    last is the ">=1 correct with no scaffolding" rule that defeats Hint-hunter
    Hugo, ARCHITECTURE.md §6 rule 3). The mastery *logic* lives in ``mastery/``;
    this is only its persisted shape.

    ``kc_id`` stores the ``KnowledgeComponentId`` StrEnum's catalog string (e.g.
    ``"KC_equivalence"``) — the registry is the single source of truth for those
    values (knowledge_components.py), and StrEnum serializing to its string keeps
    the DB, API, and gem bank all speaking the same id. We store the string rather
    than a DB ENUM so adding a KC is a registry edit, not a Postgres migration, and
    so SQLite and Postgres agree on the column type.
    """

    __tablename__ = "mastery_state"
    # One row per (learner, KC): defeats double-counting a KC's mastery state and
    # gives a clean upsert target. TECH_STACK §4 is explicit it's "per learner per KC".
    __table_args__ = (UniqueConstraint("learner_id", "kc_id", name="uq_mastery_learner_kc"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Catalog string of a KnowledgeComponentId (validated at the registry, not here).
    kc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # BKT mastery probability P(known) for this KC (ARCHITECTURE.md §6, threshold τ).
    bkt_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unscaffolded_correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    learner: Mapped[Learner] = relationship(back_populates="mastery_states")
