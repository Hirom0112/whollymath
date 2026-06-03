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

from app.db.models import (
    Assignment,
    AuthSession,
    ConsentRecord,
    InteractionEvent,
    Learner,
    Lesson,
    MasteryState,
    Roster,
    Session,
    TeacherReminder,
    Turn,
    Unit,
)


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


def get_or_create_learner_by_google_sub(
    db: OrmSession, sub: str, *, email: str | None = None
) -> Learner:
    """Return the learner for a Google account ``sub``, creating it if new (Slice PL.3).

    ``sub`` is the stable Google account id (the OIDC ``sub`` claim) — the unique key an
    authenticated learner is mapped to (we store NO password). The lookup is by the unique
    ``Learner.google_sub`` column, so calling this twice for the same ``sub`` returns the same
    learner: this is exactly the "same Google login anywhere → same learner row (→ same carried
    mastery)" property (PROJECT.md §3.12). Idempotent in the same sense as
    ``get_or_create_learner`` is for an anonymous session id.

    ``email`` is recorded when supplied and NEVER blanked: a later call that omits it leaves a
    previously-known email intact, and a call that supplies one when none was stored fills it
    in. The email is a convenience handle, not an auth secret (invariant 8).

    A new authed learner still needs the non-null, unique ``session_id`` column the model
    requires; we mint a synthetic, namespaced one (``"google:<sub>"``) so it cannot collide
    with a browser session id and so the row is well-formed. ``add``-ed but NOT committed — the
    caller owns the transaction boundary (same contract as the other ``get_or_create``).
    """
    existing = db.scalars(select(Learner).where(Learner.google_sub == sub)).first()
    if existing is not None:
        # Fill in an email we did not have before, but never blank a known one.
        if email is not None and existing.email is None:
            existing.email = email
        return existing
    learner = Learner(session_id=f"google:{sub}", google_sub=sub, email=email)
    db.add(learner)
    return learner


# The stable external key (``Learner.session_id``) of the single, shared DEMO teacher. The
# one-click "Teacher demo" tab (Slice TCH.B2) authenticates by echoing a NON-secret handle —
# ``demo:<this id>`` — back as a Bearer credential; there is no password, by owner decision. A
# fixed id keeps the demo teacher (and, at TCH.B9, their demo class) idempotent across reboots.
DEMO_TEACHER_SESSION_ID = "demo-teacher"
_DEMO_TEACHER_EMAIL = "demo.teacher@whollymath.dev"


def get_or_create_demo_teacher(db: OrmSession) -> Learner:
    """Return the shared demo teacher, creating (and forcing ``role="teacher"``) if new.

    Backs ``POST /teacher/demo-login`` (Slice TCH.B2). Keyed on the fixed
    ``DEMO_TEACHER_SESSION_ID`` so clicking the demo button repeatedly maps to ONE learner row
    (idempotent — the same contract as the other ``get_or_create`` helpers). The row is forced to
    ``role="teacher"`` (a fresh ``Learner`` defaults to ``"student"``); a no-op if already so.
    ``add``/mutate only — the caller owns the commit (so the route's unit of work is atomic).
    """
    existing = db.scalars(
        select(Learner).where(Learner.session_id == DEMO_TEACHER_SESSION_ID)
    ).first()
    if existing is not None:
        if existing.role != "teacher":
            existing.role = "teacher"
        return existing
    teacher = Learner(session_id=DEMO_TEACHER_SESSION_ID, email=_DEMO_TEACHER_EMAIL, role="teacher")
    db.add(teacher)
    return teacher


# ─────────────────────────────────────────────────────────────────────────────
# Parent/child accounts (Slice auth/parent-child, owner decision 2026-06-03).
#
# Pure data-layer reads/writes for the verifiable-parental-consent model
# (RESEARCH.md COPPA/auth): a PARENT is a Learner with role="parent" (email/password
# or Google); a CHILD is a Learner the parent owns via ``parent_id``. Crypto is NOT
# here — callers pass an ALREADY-Argon2id-hashed ``password_hash``/``pin_hash`` (the
# hashing lives in app/auth/, Slice S2; CLAUDE.md §8 keeps one home per concern).
# Every function ``add``-s/mutates but does NOT commit: the caller owns the unit of
# work (same contract as the helpers above), so creating a child + recording its
# consent commit atomically.
# ─────────────────────────────────────────────────────────────────────────────

PARENT_ROLE = "parent"


def _normalize_email(email: str) -> str:
    """Lower-case + strip an email for use as a stable lookup/identity key."""
    return email.strip().lower()


def create_parent_with_password(db: OrmSession, *, email: str, password_hash: str) -> Learner:
    """Create an email/password PARENT learner (role="parent"), email unverified.

    The parent's ``session_id`` is the namespaced ``parent:<normalized-email>``. That
    column is UNIQUE, so it doubles as the one-parent-per-email guard: a second
    signup with the same email collides on the unique constraint rather than minting
    a duplicate parent. ``email_verified`` starts False — child profiles do not go
    live until the parent verifies their email (the consent anchor, RESEARCH.md).
    ``password_hash`` is already Argon2id-hashed by the caller; we store only the
    hash (OWASP Password Storage). add-only; caller commits.
    """
    normalized = _normalize_email(email)
    learner = Learner(
        session_id=f"parent:{normalized}",
        email=normalized,
        role=PARENT_ROLE,
        password_hash=password_hash,
        email_verified=False,
    )
    db.add(learner)
    return learner


def get_parent_by_email(db: OrmSession, email: str) -> Learner | None:
    """Return the email/password PARENT for an email, or ``None``. Read-only.

    Matches on the normalized email AND ``role="parent"`` so it never returns a
    student/teacher who happens to share the email label. Backs the login lookup and
    the signup-collision check.
    """
    normalized = _normalize_email(email)
    return db.scalars(
        select(Learner).where(Learner.email == normalized, Learner.role == PARENT_ROLE)
    ).first()


def get_or_create_parent_by_google_sub(
    db: OrmSession, sub: str, *, email: str | None = None
) -> Learner:
    """Return the PARENT for a Google ``sub``, creating it (role="parent") if new.

    The Google sign-in path for parents. Mirrors
    ``get_or_create_learner_by_google_sub`` (idempotent on the unique ``google_sub``)
    but the created row is a PARENT whose email is already verified by Google
    (``email_verified=True``) — Google asserts a verified email, so it is a reliable
    consent anchor with no extra step. A previously-known email is never blanked.
    add-only; caller commits.
    """
    existing = db.scalars(select(Learner).where(Learner.google_sub == sub)).first()
    if existing is not None:
        if email is not None and existing.email is None:
            existing.email = email
        return existing
    learner = Learner(
        session_id=f"google:{sub}",
        google_sub=sub,
        email=email,
        role=PARENT_ROLE,
        email_verified=True,
    )
    db.add(learner)
    return learner


def create_child(
    db: OrmSession,
    *,
    parent_id: int,
    public_id: str,
    display_name: str,
    grade_level: int | None,
    locale: str,
    child_username: str,
    pin_hash: str,
) -> Learner:
    """Create a CHILD learner owned by ``parent_id`` (role stays "student").

    A child is a normal student Learner (role stays "student" — identity gates
    surfaces only, invariant 8) plus the parent link and login credential. Its
    ``session_id`` is the namespaced ``child:<public_id>`` (public_id is a unique
    UUID4, so the session_id is unique too). ``child_username`` is unique only within
    the parent's household (the ``uq_learner_parent_username`` index). ``pin_hash`` is
    already Argon2id-hashed by the caller. add-only; caller commits.
    """
    child = Learner(
        session_id=f"child:{public_id}",
        public_id=public_id,
        parent_id=parent_id,
        role="student",
        display_name=display_name,
        grade_level=grade_level,
        locale=locale,
        child_username=child_username,
        pin_hash=pin_hash,
    )
    db.add(child)
    return child


def get_children_of_parent(db: OrmSession, parent_id: int) -> Sequence[Learner]:
    """Return all CHILD learners owned by a parent, oldest first. Read-only."""
    return db.scalars(
        select(Learner).where(Learner.parent_id == parent_id).order_by(Learner.id)
    ).all()


def get_child_for_parent(db: OrmSession, parent_id: int, public_id: str) -> Learner | None:
    """Return ONE child by ``public_id`` ONLY IF it belongs to ``parent_id``, else None.

    The BOLA / object-ownership guard (OWASP API #1, RESEARCH.md): the ``parent_id``
    is part of the WHERE clause, so a parent asking for another family's child
    ``public_id`` gets ``None`` — authorization is enforced IN the query, never
    trusted from the request. The opaque ``public_id`` is defense-in-depth on top
    (IDOR), not the authorization itself.
    """
    return db.scalars(
        select(Learner).where(Learner.public_id == public_id, Learner.parent_id == parent_id)
    ).first()


def get_child_by_parent_and_username(
    db: OrmSession, parent_id: int, child_username: str
) -> Learner | None:
    """Return a child by (parent, username) for the independent-login path, or None.

    Child login is namespaced under the parent (owner decision 2026-06-03): the
    lookup REQUIRES the ``parent_id``, so a bare child username is never globally
    resolvable and child usernames cannot be enumerated across families (OWASP
    enumeration mitigation). PIN verification + lockout happen in the auth layer.
    """
    return db.scalars(
        select(Learner).where(
            Learner.parent_id == parent_id,
            Learner.child_username == child_username,
        )
    ).first()


def record_consent(
    db: OrmSession,
    *,
    parent_id: int,
    child_id: int | None,
    policy_version: str,
    method: str = "parent_account",
    ip_address: str | None = None,
) -> ConsentRecord:
    """Stamp a verifiable-parental-consent row (FTC COPPA Rule, RESEARCH.md).

    Written in the same unit of work as ``create_child`` so the child and the proof
    of consent for it commit together. add-only; caller commits.
    """
    consent = ConsentRecord(
        parent_id=parent_id,
        child_id=child_id,
        policy_version=policy_version,
        method=method,
        ip_address=ip_address,
    )
    db.add(consent)
    return consent


# ── Revocable sessions (the kill-switch backing, Slice auth/parent-child S2) ───


def create_auth_session(
    db: OrmSession,
    *,
    learner_id: int,
    jti: str,
    kind: str,
    expires_at: datetime,
) -> AuthSession:
    """Open a revocable server-side session for a freshly-minted JWT.

    ``jti`` is the token's unique id (UNIQUE here, so one token ↔ one session);
    ``expires_at`` mirrors the JWT ``exp``. add-only; caller commits.
    """
    session = AuthSession(learner_id=learner_id, jti=jti, kind=kind, expires_at=expires_at)
    db.add(session)
    return session


def get_active_auth_session(db: OrmSession, jti: str, now: datetime) -> AuthSession | None:
    """Return the session for ``jti`` ONLY IF it is live (not revoked, not expired).

    The server-side check that makes revocation real: a token whose row is missing,
    revoked, or past ``expires_at`` resolves to ``None`` and the request is refused,
    even though the JWT signature itself is still valid.
    """
    return db.scalars(
        select(AuthSession).where(
            AuthSession.jti == jti,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    ).first()


def revoke_auth_session(db: OrmSession, jti: str, now: datetime) -> bool:
    """Revoke one session by ``jti`` (logout). Returns whether a live row was revoked.

    Idempotent: revoking an already-revoked/expired/unknown session is a no-op that
    returns False. mutate-only; caller commits.
    """
    session = db.scalars(
        select(AuthSession).where(AuthSession.jti == jti, AuthSession.revoked_at.is_(None))
    ).first()
    if session is None:
        return False
    session.revoked_at = now
    return True


def revoke_all_sessions_for_learner(db: OrmSession, learner_id: int, now: datetime) -> int:
    """Revoke EVERY live session for a learner (the "sign out everywhere" kill-switch).

    A parent uses this to end a child's session left open on a shared/school device,
    or to lock everyone out after a credential reset. Returns how many live sessions
    were revoked. mutate-only; caller commits.
    """
    live = db.scalars(
        select(AuthSession).where(
            AuthSession.learner_id == learner_id, AuthSession.revoked_at.is_(None)
        )
    ).all()
    for session in live:
        session.revoked_at = now
    return len(live)


def get_learner_locale(db: OrmSession, learner_id: int) -> str | None:
    """Return a learner's help-language ``locale``, or ``None`` if the learner is unknown (0.3).

    A pure read of the single sticky help-language flag (``Learner.locale``) the bilingual-scaffold
    toggle writes and the surface/help layer reads to choose which language to SPEAK (V2_TODO §0.3).
    Returns ``None`` (not ``"en"``) for an unknown ``learner_id`` so the caller can distinguish "no
    such learner" from "learner whose help-language is English" — a stored learner always has a
    concrete locale (the column is NOT NULL with an ``"en"`` default). This is a rendering
    preference, NOT identity, and is never on the turn loop (see ``Learner.locale``; CLAUDE.md §7).
    """
    learner = db.get(Learner, learner_id)
    if learner is None:
        return None
    return learner.locale


def set_learner_locale(db: OrmSession, learner_id: int, locale: str) -> Learner | None:
    """Set a learner's help-language ``locale`` and return the row, or ``None`` if unknown (0.3).

    Mutates the sticky help-language flag the toggle persists (V2_TODO §0.3). ``None`` for an
    unknown ``learner_id`` so the caller can 404 rather than this raising. The ALLOWED-VALUE check
    (``"en"`` / ``"es-MX"``) is the surface/help layer's, not the repository's — this writer stores
    the chosen tag the same way ``role`` is stored (CLAUDE.md §7: validation is the service's,
    persistence is here). Mutate only, NOT committed — the caller owns the unit of work (the same
    contract as the other writers here).
    """
    learner = db.get(Learner, learner_id)
    if learner is None:
        return None
    learner.locale = locale
    return learner


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


def load_events_for_session(db: OrmSession, session_row_id: int) -> list[InteractionEvent]:
    """Load one tutoring session's ``InteractionEvent`` rows in chronological order (Slice PL.4).

    Ordered by ``server_ts`` then ``id`` — ``server_ts`` is the authoritative server-stamped
    clock (the client clock is optional and untrusted for ordering, ``models.py``), and ``id``
    is the deterministic tie-break for events stamped within the same instant (a busy batch can
    share a server timestamp). This is the read the PL.4 offline derivation pipeline consumes to
    rebuild per-problem episodes from the raw behavioral stream; it is a pure query (no business
    logic, no commit) and is NOT on the turn loop (ARCHITECTURE.md §14 invariants 5 and 7).
    """
    return list(
        db.scalars(
            select(InteractionEvent)
            .where(InteractionEvent.session_id == session_row_id)
            .order_by(InteractionEvent.server_ts, InteractionEvent.id)
        ).all()
    )


def load_events_for_learner(db: OrmSession, learner_id: int) -> list[InteractionEvent]:
    """Load all of a learner's ``InteractionEvent`` rows in chronological order (Slice PL.4).

    Same ordering and contract as ``load_events_for_session`` but scoped to a learner across all
    their sessions — the grain the offline derivation uses when it wants a learner's whole
    behavioral history. Ordered by (``server_ts``, ``id``) for the same reason.
    """
    return list(
        db.scalars(
            select(InteractionEvent)
            .where(InteractionEvent.learner_id == learner_id)
            .order_by(InteractionEvent.server_ts, InteractionEvent.id)
        ).all()
    )


def load_turns_for_learner(db: OrmSession, learner_id: int) -> list[Turn]:
    """Load all of a learner's ``Turn`` rows across their sessions, chronologically (Slice TCH.B3).

    ``Turn`` rows hang off ``Session`` (``Turn.session_id`` → ``Session.id``), which carries the
    ``learner_id``; we join through it so the teacher overview/struggle/alerts services can read a
    student's whole answer history (correctness, ``error_type``, ``hint_used``, ``latency_ms``,
    ``created_at``) without the API layer ever touching a query (CLAUDE.md §7). Ordered by
    (``created_at``, ``id``) — the same authoritative-clock-then-id ordering the event reads use,
    so a busy batch sharing a timestamp is still deterministically ordered. A pure, commit-free
    read off the turn loop (ARCHITECTURE.md §14 invariants 5 and 7); ``[]`` for a learner with no
    recorded turns.
    """
    return list(
        db.scalars(
            select(Turn)
            .join(Session, Turn.session_id == Session.id)
            .where(Session.learner_id == learner_id)
            .order_by(Turn.created_at, Turn.id)
        ).all()
    )


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


def list_units(db: OrmSession) -> list[Unit]:
    """List every curriculum ``Unit`` in display order (Slice DAT.5).

    Ordered by ``Unit.order`` (the 1-based sequence the curriculum is taught in,
    models.py) so the course map / unit picker renders units in the right order
    without the caller re-sorting. This is content metadata, the same for every
    learner; it is a pure read off the turn loop (no learner state, no business
    logic — CLAUDE.md §7).
    """
    return list(db.scalars(select(Unit).order_by(Unit.order)).all())


def get_unit(db: OrmSession, slug: str) -> Unit | None:
    """Return the ``Unit`` for a stable external ``slug``, or ``None`` if unknown (Slice DAT.5).

    Lookup is by ``Unit.slug`` — the human-readable, reseed-stable key the API and
    assignments reference (models.py), NOT the non-stable autoincrement id. ``None``
    for an unknown slug so the caller can 404 rather than this raising.
    """
    return db.scalars(select(Unit).where(Unit.slug == slug)).first()


def list_lessons_for_unit(db: OrmSession, unit_slug: str) -> list[Lesson]:
    """List a unit's ``Lesson`` rows in authored order, by the unit's ``slug`` (Slice DAT.5).

    Joined on ``Lesson.unit_id == Unit.id`` and filtered by ``Unit.slug`` so the
    caller can ask by the stable slug it already holds, and ordered by
    ``Lesson.order`` (the 1-based sequence within the unit, models.py). An UNKNOWN
    unit slug yields an empty list rather than an error: a unit with no lessons and a
    unit that does not exist look the same to a read, and neither is exceptional on a
    list endpoint.
    """
    return list(
        db.scalars(
            select(Lesson)
            .join(Unit, Lesson.unit_id == Unit.id)
            .where(Unit.slug == unit_slug)
            .order_by(Lesson.order)
        ).all()
    )


def list_students_for_teacher(db: OrmSession, teacher_id: int) -> list[Learner]:
    """List the ``Learner`` rows rostered to a teacher, ordered by id (Slice TCH.B1).

    Joins the ``Roster`` membership table to ``Learner`` on ``student_id`` and filters
    by ``teacher_id`` so a teacher sees ONLY their own students (the isolation the
    dashboard depends on — TEACHER_NEEDS.md). Ordered by ``Learner.id`` for a stable,
    deterministic listing (roughly enrollment order). Empty list for a teacher with no
    roster. This is identity/roster surface only and never reaches the mastery/policy/
    tutor/LLM path (ARCHITECTURE.md §14 invariant 8).
    """
    return list(
        db.scalars(
            select(Learner)
            .join(Roster, Roster.student_id == Learner.id)
            .where(Roster.teacher_id == teacher_id)
            .order_by(Learner.id)
        ).all()
    )


def add_student_to_roster(db: OrmSession, teacher_id: int, student_id: int) -> Roster:
    """Enroll a student in a teacher's roster, idempotently (Slice TCH.B1).

    Looks the (teacher, student) pair up first and RETURNS THE EXISTING row if the
    membership is already there, otherwise ``add``-s a new ``Roster`` row — so calling
    this twice never creates a duplicate membership (the model's ``uq_roster_teacher_
    student`` constraint backs this; we check in Python so a re-enroll is a clean no-op
    rather than an IntegrityError the caller must catch). A roster is a SET, not a
    multiset (TEACHER_NEEDS.md). ``add``-ed, NOT committed — the caller owns the unit of
    work (same contract as the other writers here).
    """
    existing = db.scalars(
        select(Roster).where(Roster.teacher_id == teacher_id, Roster.student_id == student_id)
    ).first()
    if existing is not None:
        return existing
    membership = Roster(teacher_id=teacher_id, student_id=student_id)
    db.add(membership)
    return membership


def get_student_if_on_roster(db: OrmSession, teacher_id: int, student_id: int) -> Learner | None:
    """Return a student ``Learner`` ONLY if they are on this teacher's roster (Slice TCH.B1).

    The authorization primitive behind every "teacher reads/acts on a student"
    endpoint: it returns the student row when a ``Roster`` membership for exactly this
    (teacher, student) pair exists, and ``None`` otherwise — both when the learner is
    on no roster at all and when they belong to a DIFFERENT teacher. A foreign teacher
    therefore gets ``None`` and the caller denies the request. Identity/authz surface
    only; never on the turn loop (ARCHITECTURE.md §14 invariant 8).
    """
    return db.scalars(
        select(Learner)
        .join(Roster, Roster.student_id == Learner.id)
        .where(Roster.teacher_id == teacher_id, Roster.student_id == student_id)
    ).first()


def get_assigned_unit(db: OrmSession, student_id: int) -> Assignment | None:
    """Return a student's CURRENT teacher-assigned ``Assignment``, or ``None`` (Slice DAT.10).

    A student may hold more than one assignment over time (the model allows one per
    (student, unit) — ``uq_assignment_student_unit``); the "what should I work on now"
    surface wants the single CURRENT one. We define current as the MOST-RECENTLY-UPDATED
    assignment: ordered by ``Assignment.updated_at`` descending, with ``Assignment.id``
    descending as the deterministic tie-break for two rows stamped in the same instant.

    Why updated_at (not created_at): ``updated_at`` is bumped on every status change /
    note edit / re-assign (the model's ``onupdate``), so the assignment a teacher most
    recently *touched* — created OR re-prioritized — is the one surfaced. This is a
    deliberate ordering choice, not pinned by a source doc; recorded here so the
    decision log can see it (CLAUDE.md §8.4). ``None`` when the student has no
    assignment, so the surface falls back to the normal next-unit flow.
    """
    return db.scalars(
        select(Assignment)
        .where(Assignment.student_id == student_id)
        .order_by(Assignment.updated_at.desc(), Assignment.id.desc())
    ).first()


def assign_unit(
    db: OrmSession,
    *,
    teacher_id: int,
    student_id: int,
    unit_id: int,
    now: datetime,
) -> Assignment:
    """Assign a unit to a student, idempotently upserting on ``(student, unit)`` (Slice TCH.B7).

    The model keys uniqueness on ``(student_id, unit_id)`` (``uq_assignment_student_unit``), so
    re-assigning the same unit updates the existing row rather than spawning a duplicate. We stamp
    ``updated_at`` to ``now`` on every call (create OR re-assign) so this row becomes the student's
    CURRENT assignment — ``get_assigned_unit`` orders by ``updated_at`` desc, so the just-assigned
    unit is the one the student shell surfaces. ``now`` is passed in (not read from a clock here)
    to keep the repository deterministic and the unit of work the caller's (CLAUDE.md §7).
    ``add``/mutate only — the caller commits.
    """
    existing = db.scalars(
        select(Assignment).where(Assignment.student_id == student_id, Assignment.unit_id == unit_id)
    ).first()
    if existing is not None:
        existing.teacher_id = teacher_id
        existing.status = "assigned"
        existing.updated_at = now
        return existing
    row = Assignment(
        teacher_id=teacher_id,
        student_id=student_id,
        unit_id=unit_id,
        status="assigned",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    return row


def list_reminders_for_teacher(db: OrmSession, teacher_id: int) -> list[TeacherReminder]:
    """List a teacher's reminders, newest-first (dashboard upgrade).

    Scoped to ``teacher_id`` so a teacher only ever sees their own reminders (the owns-surface
    isolation the rest of the teacher reads use). Ordered by ``id`` descending — newest first —
    which is a stable, deterministic order (ids are monotonic). ``[]`` for a teacher with none.
    Pure read off the turn loop (CLAUDE.md §7; ARCHITECTURE.md §14 invariant 8).
    """
    return list(
        db.scalars(
            select(TeacherReminder)
            .where(TeacherReminder.teacher_id == teacher_id)
            .order_by(TeacherReminder.id.desc())
        ).all()
    )


def create_reminder(db: OrmSession, *, teacher_id: int, text: str) -> TeacherReminder:
    """Create a reminder for a teacher and return it (dashboard upgrade).

    ``done`` defaults to False (a fresh reminder is open). ``add``-ed, NOT committed — the caller
    owns the unit of work (same contract as the other writers here).
    """
    reminder = TeacherReminder(teacher_id=teacher_id, text=text)
    db.add(reminder)
    return reminder


def get_reminder_for_teacher(
    db: OrmSession, *, teacher_id: int, reminder_id: int
) -> TeacherReminder | None:
    """Return a teacher's reminder by id, or ``None`` if it is missing OR another teacher's.

    The authorization primitive for reminder writes: a reminder belonging to a different teacher
    is INDISTINGUISHABLE from a missing one (both ``None``), so a teacher can never read or mutate
    another teacher's reminder (mirrors ``get_student_if_on_roster``). Pure read (no commit).
    """
    return db.scalars(
        select(TeacherReminder).where(
            TeacherReminder.id == reminder_id, TeacherReminder.teacher_id == teacher_id
        )
    ).first()


def set_reminder_done(
    db: OrmSession, *, teacher_id: int, reminder_id: int, done: bool
) -> TeacherReminder | None:
    """Toggle a teacher's reminder ``done`` flag, returning the row, or ``None`` if not theirs.

    Looks the reminder up via ``get_reminder_for_teacher`` (so a foreign/unknown id is ``None``),
    sets ``done``, and returns the mutated row. ``None`` lets the route 404. Mutate only — the
    caller commits (caller's unit-of-work boundary).
    """
    reminder = get_reminder_for_teacher(db, teacher_id=teacher_id, reminder_id=reminder_id)
    if reminder is None:
        return None
    reminder.done = done
    return reminder


__all__ = [
    "DEMO_TEACHER_SESSION_ID",
    "EventRow",
    "add_student_to_roster",
    "assign_unit",
    "create_reminder",
    "create_session",
    "end_session",
    "get_assigned_unit",
    "get_learner",
    "get_learner_locale",
    "get_or_create_demo_teacher",
    "get_or_create_learner",
    "get_or_create_learner_by_google_sub",
    "get_reminder_for_teacher",
    "get_student_if_on_roster",
    "get_unit",
    "list_lessons_for_unit",
    "list_reminders_for_teacher",
    "list_students_for_teacher",
    "list_units",
    "load_events_for_learner",
    "load_events_for_session",
    "load_mastery_states",
    "load_turns_for_learner",
    "load_open_session",
    "load_open_session_for_learner",
    "persist_event",
    "persist_events",
    "persist_turn",
    "set_learner_locale",
    "set_reminder_done",
    "upsert_mastery_state",
]
