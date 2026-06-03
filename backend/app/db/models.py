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

Wave 1 (DAT.1) adds the curriculum and teacher-layer tables on top of the same
thin, portable-types foundation:

  - ``Unit`` / ``Lesson`` — the curriculum skeleton (one Unit per CCSS/TEKS
    cluster, ordered Lessons inside it). A Lesson may carry a ``kc_id`` string to
    reuse an existing KnowledgeComponentId, but it is NULLABLE because some lessons
    do not map to a KC yet (DAT.1).
  - ``role`` on ``Learner`` + ``Roster`` + ``Assignment`` — the teacher layer
    (TEACHER_NEEDS.md): a learner can be a teacher, a teacher↔student roster is a
    many-to-many membership, and an Assignment hands a Unit to a student. Identity/
    role never reaches the mastery/policy/tutor/llm path (ARCHITECTURE.md §14
    invariant 8) — it only governs which surface a request may use.

Defer reasons recorded so the decision log is intact (CLAUDE.md §8.4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
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
    # A CHILD's login username is unique only WITHIN its parent's household, not
    # globally — so child usernames cannot be enumerated across families and two
    # families may reuse the same name (OWASP enumeration mitigation; owner decision
    # 2026-06-03, RESEARCH.md COPPA/auth). Modeled as a UNIQUE INDEX (not a table
    # UNIQUE constraint) so the Alembic migration can add it to the ALREADY-EXISTING
    # learner table on SQLite, which rejects ALTER TABLE ADD CONSTRAINT (the test-DB
    # path); ``create_all`` builds the identical unique index. Rows with NULL
    # parent_id/child_username (every non-child learner) are exempt because SQL
    # treats NULLs as distinct.
    __table_args__ = (
        Index("uq_learner_parent_username", "parent_id", "child_username", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The externally-visible session id the frontend sends in place of auth. Unique
    # so the same browser session maps to exactly one learner row (TECH_STACK §9).
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # The Google account id (OIDC ``sub``) when this learner has signed in (Slice PL.3).
    # NULLABLE: anonymous, session-id-keyed learners (the v1 default flow) leave it None; an
    # authenticated learner has their stable Google ``sub`` here. UNIQUE so the same Google
    # login maps to exactly one learner row anywhere (the "same login → same state" property,
    # PROJECT.md §3.12). We store NO password — the learner is keyed to ``sub`` alone. Identity
    # never reaches the mastery model/policy/LLM (ARCHITECTURE.md §14 invariant 8); this column
    # only lets persistence/continuity find the right learner row.
    google_sub: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    # The Google account email, if the verified token carried one (Slice PL.3). Nullable: a
    # token may omit it and we never require it. It is a convenience handle for the learner, NOT
    # an auth secret and NOT consumed by any turn-loop decision (invariant 8).
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Which kind of user this row is: "student" (the default, every v1 learner) or
    # "teacher" (a learner who also owns a roster + assigns units, Wave 1 TCH layer).
    # A PLAIN STRING TAG, not a DB ENUM — same rationale as ``kc_id`` on MasteryState:
    # adding/renaming a role is a code change, not a Postgres migration, and SQLite and
    # Postgres agree on the column type (the §4 portability rule). NOT NULL with a
    # Python-side default so every existing and new row has a concrete role.
    #
    # IMPORTANT (ARCHITECTURE.md §14 invariant 8): role is IDENTITY, and identity NEVER
    # reaches the mastery model / policy / tutor / LLM. It only gates which API surface a
    # request may use (a teacher's dashboard vs. a student's tutor) and who may read whose
    # state. No turn-loop decision branches on it.
    role: Mapped[str] = mapped_column(String(16), default="student", nullable=False)
    # The learner's HELP-LANGUAGE preference — a RENDERING preference, not identity (Slice 0.3).
    # Under the bilingual-scaffold design (V2_TODO §0.3 / §3.6 + owner clarification 2026-06-02),
    # on-screen lesson/problem content stays ENGLISH; only the avatar's voice + hint text localize.
    # This column is the single sticky flag that toggle writes and the surface/help layer reads to
    # choose which language to SPEAK — it changes nothing the learner reads on the page.
    #
    # A PLAIN STRING TAG, not a DB ENUM — same rationale as ``role``/``kc_id``: adding a
    # help-language is a code change (a validated set in the surface layer), not a Postgres
    # migration, and SQLite and Postgres agree on the column type (the §4 portability rule). Allowed
    # values: ``"en"`` (default) and ``"es-MX"`` (the LOCKED Spanish target — es-US/es-MX, owner
    # decision 2026-06-02). NOT NULL with a Python-side default so every row has a concrete locale.
    #
    # CRITICAL BOUNDARY: locale is NOT identity and is NOT consumed by the mastery model / policy /
    # tutor / turn loop. It would only ever be read by the surface/help layer to pick a language, so
    # no turn-loop decision branches on it. This is ADJACENT to ARCHITECTURE.md §14 invariant 8
    # (which keeps IDENTITY off the mastery path) but DISTINCT from it: locale is a rendering
    # preference, not identity. Source: V2_TODO §0.3 + owner clarification 2026-06-02.
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    # ─────────────────────────────────────────────────────────────────────────
    # Parent/child accounts (Slice auth/parent-child, owner decision 2026-06-03).
    # These columns turn the session-id-only Learner of TECH_STACK §9 into the
    # foundation for verifiable-parental-consent accounts: a PARENT is a Learner
    # with role="parent" who may also carry a ``password_hash`` (email/password
    # signup) on top of the existing ``google_sub`` path; a CHILD is a Learner the
    # parent created, linked by ``parent_id`` and reached by a non-identifying
    # ``child_username`` + PIN for independent login. This reverses the "auth is
    # post-launch" line in TECH_STACK §9 (recorded there + in the commit), and is
    # grounded in COPPA verifiable parental consent (RESEARCH.md, FTC COPPA Rule)
    # and the OWASP authentication guidance.
    #
    # CRITICAL (ARCHITECTURE.md §14 invariant 8): every column here is IDENTITY or
    # a CREDENTIAL. None of it reaches the mastery model / policy / tutor / LLM — it
    # only gates which surface a request may use and who may read whose state.

    # The parent who created and owns this child account (a Learner with
    # role="parent"). NULL for everyone else (anonymous/Google students, teachers,
    # and the parents themselves). CASCADE so deleting a parent purges their
    # children in one unit — the COPPA "parent may delete the child's data" right
    # (FTC COPPA Rule; 2025 retention amendment). Indexed so "children of a parent"
    # is cheap.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # Argon2id hash of a PARENT's password, when they signed up with email/password
    # rather than Google (owner decision 2026-06-03: support both). NULL for Google
    # parents (keyed on ``google_sub``) and for every student/teacher. We store ONLY
    # the hash, never the password (OWASP Password Storage Cheat Sheet). Read solely
    # by the auth layer; never consumed by a turn-loop decision (invariant 8).
    # String(255) comfortably holds an Argon2id PHC-format hash.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Whether a PARENT has verified their email. An unverified email is not a
    # reliable consent anchor, so child profiles do not go live until this is True
    # (RESEARCH.md COPPA verifiable-parental-consent). Default False; left False (and
    # meaningless) for Google parents — Google already asserts a verified email — and
    # for students/teachers. NOT NULL with a Python-side default.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # A CHILD's display nickname, shown on the parent dashboard and the profile
    # picker. NULL for non-children. COPPA data-minimization: parents are instructed
    # to use a NON-identifying nickname, not the child's real name (mirrors Khan
    # Academy's guidance, RESEARCH.md). A plain display string — never identity.
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # A CHILD's grade level (the curriculum is Grade 6, with remediation down a level
    # — CURRICULUM_STANDARD.md). NULL for non-children. Stored for routing/display
    # only; not consumed by the turn loop (invariant 8).
    grade_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A CHILD's login handle for INDEPENDENT login (the school/shared-device path —
    # owner decision 2026-06-03: profiles at home, username+PIN away). NULL for
    # non-children. UNIQUE PER PARENT, not globally (see ``__table_args__``).
    child_username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Argon2id hash of a CHILD's 4-digit PIN (owner decision 2026-06-03: a PIN, not a
    # full password, is developmentally right for an 11-12-year-old — RESEARCH.md).
    # NULL for non-children. Like ``password_hash`` we store ONLY the hash. The PIN's
    # small keyspace is defended by per-account lockout (the two columns below) and
    # the per-parent namespacing above, not by the hash alone.
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Consecutive failed PIN attempts on a CHILD account, for brute-force lockout
    # (OWASP brute-force mitigation, RESEARCH.md). Reset to 0 on a correct PIN. NOT
    # NULL, default 0. The lockout POLICY (threshold, cooldown) lives in the auth
    # layer; this column only holds the counter.
    failed_pin_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # When a CHILD account is locked out until, after too many failed PINs. NULL when
    # not locked. The auth layer compares against ``now()`` before accepting a PIN.
    pin_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # An OPAQUE, unguessable public identifier (UUID4 hex) used in URLs/API paths in
    # place of the sequential integer id, so child records cannot be enumerated by
    # iterating ids (OWASP IDOR defense-in-depth; authorization is STILL enforced by
    # the ``parent_id`` ownership check, RESEARCH.md). UNIQUE, NULL for rows that
    # predate it. String(36), not a Postgres UUID type, per the §4 portability rule.
    public_id: Mapped[str | None] = mapped_column(
        String(36), unique=True, index=True, nullable=True
    )

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
    # Self-referential parent↔children link (the FK is ``parent_id`` above). cascade
    # so a parent's children delete with them — the COPPA deletion right (FTC COPPA
    # Rule). ``remote_side`` on the parent side resolves the self-join direction.
    children: Mapped[list[Learner]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent: Mapped[Learner | None] = relationship(
        back_populates="children",
        remote_side="Learner.id",
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
    # The Turn-0 route key this session started in (a tutor ``RouteOption.key``, e.g.
    # "combine"). Stored so a resume after a server restart can re-derive the session's
    # goal KC and serve a fresh problem in it (Slice PL.1.2) — the routing table is the
    # single source of truth (tutor ``routing_choices``), so the key is enough to rebuild.
    # Nullable so older rows (pre-PL.1) and any non-routed session load without breaking.
    route_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    # Whether this KC's PROVISIONAL mastery has been CONFIRMED by the S5 transfer probe
    # ("mastered means CONFIRMED", PROJECT.md §3.4 / the live confirm-gate). This is real
    # mastery state, not a transient: it must survive a restart so a resumed session does
    # not re-demand a probe the learner already passed. Default False (provisional/none).
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    learner: Mapped[Learner] = relationship(back_populates="mastery_states")


class InteractionEvent(Base):
    """One raw behavioral event captured OFF the turn loop (Slice PL.2, invariant 7).

    The append-only stream of fine-grained interaction events the surface emits beyond
    the coarse ``Turn`` row: number-line drags, answer edits, focus/blur, idle, the
    moment a problem was presented, a submit, a hint request, the first interaction.
    PL.4's richer HelpNeed model trains on this stream (TODO PL.2/PL.4), so the table is
    intentionally minimal-and-wide: a typed tag plus an open JSON ``payload`` rather than
    a column per event kind (a fixed schema would force a migration for every new event
    type the surface starts emitting).

    Append-only and decoupled by design (ARCHITECTURE.md §14 invariant 7 — "telemetry
    never blocks a turn"): events arrive on a SEPARATE ``/events`` endpoint, are persisted
    best-effort off the request path, and a write failure is swallowed. Nothing in the turn
    loop reads this table, so a slow or failed event write can never perturb a turn outcome.

    Nullable foreign keys on purpose. ``session_id`` and ``learner_id`` are nullable because
    telemetry is LENIENT: an event may arrive for a ``session_id`` the server no longer holds
    in memory (a restart) or before its Session row exists — we still record what we can rather
    than drop it or 404 (the ``/events`` endpoint never 404s). The FKs point at the same rows the
    turn loop uses when they ARE known, so a recorded event joins back to its session/learner.

    Portable JSON column (NOT Postgres-only JSONB), deliberately. SQLAlchemy's generic ``JSON``
    type maps to ``json`` on Postgres and to ``TEXT`` with JSON serialization on SQLite, so the
    SAME column type works in the in-memory SQLite test DB and in prod Postgres (the §27/§4
    portability rule the other models follow — no Postgres-only UUID/JSONB/ENUM). JSONB would
    diverge between test and prod; we do not need its indexed-query speed for an append-only
    capture table at this slice (CLAUDE.md §8.6 — no premature optimization).
    """

    __tablename__ = "interaction_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable FK: an event may arrive for a session row we do not (yet) have (see class doc).
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # Nullable FK: likewise the learner may be unknown for a lenient telemetry write.
    learner_id: Mapped[int | None] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # The event kind as a short tag (numberline_drag / answer_edit / focus / blur / idle /
    # problem_presented / submit / hint_request / first_interaction / ...). Kept open (a
    # string, not an ENUM) so the surface can emit a new kind without a Postgres migration.
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # The event's free-form detail (e.g. the dragged value, the edited text, the idle ms).
    # Portable JSON — see the class docstring for why generic JSON, not Postgres JSONB.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # When the CLIENT recorded the event (its clock), if it sent one. Nullable because a
    # client may omit it; the server clock (``server_ts``) is always authoritative for ordering.
    client_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When the SERVER received the event — the always-present, authoritative timestamp. Same
    # Python-side UTC default the other tables use, so it is identical on SQLite and Postgres.
    server_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Unit(Base):
    """One curriculum unit — a CCSS/TEKS cluster of lessons (Wave 1, DAT.1).

    The top of the curriculum skeleton: U1..U8 (TEKS_CCSS_COMPARISON.md /
    CURRICULUM_STANDARD.md). One row per unit, ordered by ``order`` for display.
    Lessons hang off it (``Unit.lessons``). This is content metadata, not learner
    state — it is the same for every learner and changes only when the curriculum
    does.

    ``slug`` is the STABLE external key (e.g. ``"u1-ratios"``): unique + indexed so
    code, the API, and assignments can reference a unit by a human-readable handle
    that survives reseeding, rather than by the autoincrement ``id`` (which is not
    stable across environments). ``ccss_cluster``/``teks_cluster`` carry the
    standard codes the teacher dashboard surfaces (TEACHER_NEEDS.md — teachers map
    work to standards). Both are NULLABLE: our coverage is dual but not universally
    so — single-framework units exist. The whole of U-INT (integer arithmetic,
    CCSS parks it in Grade 7) and U8 (personal financial literacy, no CCSS strand)
    are TEKS-only and carry ``ccss_cluster=None``; symmetrically a CCSS-only unit
    would carry ``teks_cluster=None``. This mirrors the already-nullable per-lesson
    ``Lesson.ccss_code``/``teks_code`` (same single-framework reality at the leaf).
    Source: the dual-coverage standard (TEKS_CCSS_COMPARISON.md /
    CURRICULUM_STANDARD.md) and the catalog's TEKS-only units in
    ``app.domain.curriculum`` (``uint``/``u8`` have ``ccss_cluster=None``).
    """

    __tablename__ = "unit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stable, human-readable external key for the unit (see class doc). Unique +
    # indexed so a unit is referenced by slug, not by the non-stable autoincrement id.
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Display/sequence order within the curriculum (1-based). Not unique — ordering is
    # a presentation concern, and reordering should not require a uniqueness dance.
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    # CCSS cluster code (e.g. "6.RP.A") and TEKS cluster code (e.g. "6.4") — the dual
    # standards coverage the teacher dashboard maps work to (TEKS_CCSS_COMPARISON.md).
    # NULLABLE for single-framework units: a TEKS-only unit (U-INT integer arithmetic,
    # U8 financial literacy) carries ccss_cluster=None; a CCSS-only unit would carry
    # teks_cluster=None. Mirrors the already-nullable Lesson.ccss_code/teks_code — see
    # the class docstring for the source (the dual-coverage standard + the catalog).
    ccss_cluster: Mapped[str | None] = mapped_column(String(32), nullable=True)
    teks_cluster: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str] = mapped_column(String(1024), nullable=False)

    # Lessons read back in their authored order (mirrors Session.turns by turn_index).
    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="unit",
        cascade="all, delete-orphan",
        order_by="Lesson.order",
    )


class Lesson(Base):
    """One lesson inside a Unit (Wave 1, DAT.1).

    The leaf of the curriculum skeleton. Like ``Unit`` it is content metadata, not
    learner state. Ordered within its unit by ``order`` (``Unit.lessons`` sorts on it).

    ``kc_id`` is NULLABLE on purpose (DAT.1): some lessons reuse an existing
    ``KnowledgeComponentId`` catalog string (so the lesson's practice updates that
    KC's MasteryState), but others do not map to a KC yet — we model the curriculum
    structure now and wire the KC mapping in as it is authored, rather than blocking
    a lesson row on a KC that may not exist. When set, it is the SAME catalog string
    ``MasteryState.kc_id`` stores (knowledge_components.py is the single source of
    truth), kept as a string (not a DB ENUM) for the same portability reason.

    ``ccss_code``/``teks_code`` are the per-lesson standard codes (finer than the
    unit's cluster) the teacher dashboard surfaces.
    """

    __tablename__ = "lesson"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stable external key for the lesson (e.g. "u1-l1"), same rationale as Unit.slug.
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # Owning unit. NOT NULL (a lesson always belongs to a unit) and indexed so
    # "lessons of this unit" is a cheap lookup. CASCADE so deleting a unit removes
    # its lessons at the DB level too (the ORM relationship cascade handles the
    # session-level delete; the FK rule covers raw deletes).
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("unit.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Display/sequence order within the unit (1-based). Not unique — see Unit.order.
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    # Optional KnowledgeComponentId catalog string this lesson trains (see class doc).
    # NULLABLE: not every lesson maps to a KC yet (DAT.1).
    kc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Per-lesson standard codes (finer than the unit cluster). Nullable so a lesson can
    # exist before its exact standard code is pinned (curriculum is authored incrementally).
    ccss_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    teks_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable: a lesson row can be created before its blurb is written.
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    unit: Mapped[Unit] = relationship(back_populates="lessons")


class Roster(Base):
    """A teacher↔student membership row (Wave 1, DAT.1; TEACHER_NEEDS.md).

    The many-to-many association between a teacher Learner and a student Learner:
    "this student is in this teacher's roster". A join table rather than a column on
    Learner because the relationship is many-to-many (a student may appear in more
    than one teacher's roster; a teacher has many students) and because we want to
    record WHEN the membership was created.

    Both FKs point at ``learner.id`` (teacher and student are both Learner rows; the
    ``role`` tag distinguishes them — see ``Learner.role``). CASCADE on both so
    deleting either learner removes the membership rather than leaving a dangling row.
    Indexed on both sides so "students of a teacher" and "teachers of a student" are
    both cheap. The (teacher, student) pair is UNIQUE so the same student cannot be
    enrolled twice in the same teacher's roster (a clean idempotent enroll target).
    """

    __tablename__ = "roster"
    # One membership per (teacher, student): makes enroll idempotent and prevents
    # duplicate roster rows (TEACHER_NEEDS.md — a roster is a set, not a multiset).
    __table_args__ = (
        UniqueConstraint("teacher_id", "student_id", name="uq_roster_teacher_student"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Assignment(Base):
    """A unit assigned by a teacher to a student (Wave 1, DAT.1; TEACHER_NEEDS.md).

    The teacher hands a ``Unit`` to a student and tracks its ``status`` as the
    student works it. ``teacher_id`` records who assigned it (TEACHER_NEEDS.md
    surfaces "assigned by" and lets a teacher manage their own assignments);
    ``student_id``/``unit_id`` are the assignment itself.

    ``status`` is a PLAIN STRING tag (default ``"assigned"``), not a DB ENUM — same
    portability rationale as ``Learner.role`` and ``MasteryState.kc_id``: the state
    machine's labels can evolve without a Postgres migration, and SQLite/Postgres
    agree on the type. The status STATE MACHINE itself is owned by the teacher
    service/policy layer (not modeled here — models are thin, CLAUDE.md §7); this
    column only persists the current label.

    The (student, unit) pair is UNIQUE (``uq_assignment_student_unit``) so a student
    has AT MOST ONE assignment per unit. That makes TCH's "assign the next unit"
    flow an idempotent UPSERT (re-assigning the same unit updates the existing row's
    status/note rather than spawning duplicates). ``teacher_id`` is deliberately NOT
    part of the uniqueness: a unit is assigned to a student once regardless of which
    teacher pressed the button (two teachers cannot create two competing assignments
    of the same unit to the same student).
    """

    __tablename__ = "assignment"
    # One assignment per (student, unit): the idempotent upsert target for "assign
    # next unit" (TCH). teacher_id is intentionally excluded from the key — see class doc.
    __table_args__ = (UniqueConstraint("student_id", "unit_id", name="uq_assignment_student_unit"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("unit.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Current state-machine label (e.g. "assigned"). Default "assigned" — a freshly
    # created assignment is in the initial state. The transitions live in the service
    # layer; this column only holds the current label (see class doc).
    status: Mapped[str] = mapped_column(String(32), default="assigned", nullable=False)
    # Optional free-text note from the teacher to the student ("start here"). Nullable
    # because most assignments carry none.
    note: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Stamped on every update (status change, note edit) so the dashboard can show
    # "last touched" and so an upsert reflects when it last ran.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class TeacherReminder(Base):
    """A teacher's private to-do reminder on the dashboard (dashboard upgrade).

    A lightweight checklist item a teacher jots for themselves ("call Maya's parent",
    "re-teach common denominators Friday"). Scoped to ONE teacher via ``teacher_id`` (a
    ``Learner.id`` with ``role="teacher"``) — a teacher only ever reads/writes their own
    reminders, mirroring the owns-roster isolation of the rest of the teacher surface
    (TEACHER_NEEDS.md). CASCADE on the FK so deleting a teacher removes their reminders.

    ``done`` is a plain boolean toggle (default False). This is teacher-private UI state,
    NOT learner state and NOT on any turn-loop path — identity/role gates this surface only
    (ARCHITECTURE.md §14 invariant 8). Thin model: no queries/logic here (CLAUDE.md §7);
    the repository owns the reads/writes. Portable column types only (String/Boolean/
    DateTime), so the same definition works on the SQLite test DB and prod Postgres (the §4
    portability rule the other models follow).
    """

    __tablename__ = "teacher_reminder"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(String(512), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ConsentRecord(Base):
    """A recorded act of verifiable parental consent (Slice auth/parent-child).

    COPPA requires verifiable parental consent before collecting a child's data,
    and an auditable record that it happened (FTC COPPA Rule; RESEARCH.md). In our
    model the consent EVENT is the authenticated parent creating a child profile, so
    we stamp one row per (parent, child) at creation time: who consented, to which
    privacy-policy version, by what method, and from where. This is the tracked
    proof we can show a regulator, and the anchor for honoring later revocation /
    deletion (the 2025 COPPA retention amendment, RESEARCH.md).

    Both FKs point at ``learner.id`` (parent and child are both Learner rows; the
    ``role``/``parent_id`` columns distinguish them). CASCADE on both so deleting
    either the parent or the child removes the consent row with them, keeping the
    deletion a clean unit. ``child_id`` is NULLABLE so an account-level consent
    (recorded before any child exists) can also be stored.

    Thin model, portable column types only (the §4 rule); the repository owns the
    writes (CLAUDE.md §7). Never on a turn-loop path (invariant 8).
    """

    __tablename__ = "consent_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=False
    )
    child_id: Mapped[int | None] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # The privacy-policy / direct-notice version the parent consented to, so we can
    # prove WHICH disclosures they saw (policies change; consent is version-bound).
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # How consent was obtained. Default "parent_account": the authenticated parent's
    # own action creating the child IS the consent (the method our architecture
    # uses, RESEARCH.md). A plain string tag, not a DB ENUM (§4 portability), so
    # adding a stronger VPC method later (e.g. "text_plus") is a code change, not a
    # Postgres migration.
    method: Mapped[str] = mapped_column(String(32), default="parent_account", nullable=False)
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # The IP the consent was given from, recorded as part of the auditable consent
    # context. Nullable (may be unavailable). String(45) holds a full IPv6 literal.
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)


class AuthSession(Base):
    """A revocable server-side session record (Slice auth/parent-child, S2).

    A session JWT (``app.auth.tokens``) proves a request is authentic, but a bare
    stateless JWT cannot be un-issued — so a parent's "sign out everywhere" / a
    kill-switch on a child's session left open on a school device would be
    impossible. This row is the revocable half: the JWT carries a unique ``jti`` that
    points at exactly one ``AuthSession``, and a request is only honored while its
    row is present, NOT revoked, and NOT past ``expires_at`` (OWASP session-management
    guidance, RESEARCH.md). Logout / kill-switch just stamps ``revoked_at``.

    ``learner_id`` CASCADEs so deleting a learner drops their sessions. ``kind`` is the
    same "parent"/"child" tag the token carries — identity that gates surfaces only
    (ARCHITECTURE.md §14 invariant 8), never a turn-loop decision. ``expires_at``
    mirrors the JWT ``exp`` so a sweep can purge dead rows. Portable column types only
    (§4); the repository owns the reads/writes (CLAUDE.md §7).
    """

    __tablename__ = "auth_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learner.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The JWT id (``jti`` claim) this row backs — the link between the stateless token
    # and this revocable record. UNIQUE so a token maps to exactly one session.
    jti: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    # "parent" or "child" — mirrors the token's kind; gates which surface the session
    # may use (invariant 8). Plain string tag, not a DB ENUM (§4 portability).
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Mirror of the JWT ``exp``: a request is refused once now ≥ this, even if the row
    # was never revoked, and a cleanup sweep can delete rows past it.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Stamped when the session is explicitly ended (logout / parent kill-switch). NULL
    # while live; once set the session is dead even before ``expires_at``.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
