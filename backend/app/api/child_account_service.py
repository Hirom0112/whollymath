"""Child-account orchestration: create / list / reset-PIN / delete / sessions (Slice S3).

Routes call this; this calls the repository + the auth primitives (CLAUDE.md §7 — no
business logic in handlers, no SQL in services). The service owns the unit of work
(commits), mirroring ``parent_auth_service`` which also commits its writes here.

Security posture pinned in this module (RESEARCH.md COPPA / OWASP API Top 10):

  - **BOLA (OWASP API #1).** Every child the parent names is resolved through
    ``repo.get_child_for_parent(parent_id, public_id)``, which scopes the lookup to the
    authenticated parent IN the query. A parent asking for another family's child gets a
    ``ChildNotFoundError`` → 404, never another family's data — authorization is enforced
    in the query, not trusted from the request. The opaque ``public_id`` (UUID4) is
    defense-in-depth (IDOR) on top, never the authorization itself.
  - **COPPA verifiable parental consent.** Creating a child stamps a ``ConsentRecord`` in
    the SAME unit of work as the child row (they commit together), so a child never exists
    without its proof of consent. Deletion implements the COPPA parental deletion right.
  - **PIN brute-force (OWASP).** A 4-digit PIN has only 10,000 possibilities, so hashing
    alone is not enough; the independent ``child_login`` path enforces the per-account
    online lockout (``app.auth.pin_lockout``) and answers unknown-parent / unknown-username
    / wrong-PIN with ONE generic error so credentials cannot be enumerated. A dummy hash is
    verified on the not-found path to equalize timing.

Layering (ARCHITECTURE.md §14 invariant 8): identity gates the surface only, never the
turn loop. This service reaches no mastery/policy/LLM/domain code.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.api.child_account_schemas import (
    ChildCredentialResponse,
    ChildSessionResponse,
    ChildSummary,
)
from app.api.parent_session import CHILD_SESSION_TTL
from app.auth.csrf import generate_csrf_token
from app.auth.passwords import hash_pin, validate_pin, verify_pin
from app.auth.pin_lockout import (
    LockoutState,
    after_failed_attempt,
    after_successful_attempt,
    is_locked,
)
from app.auth.tokens import CHILD_KIND, mint_session_token
from app.db import repositories as repo
from app.db.models import Learner

# The privacy-policy version a fresh consent is recorded against (COPPA audit trail). A
# bump here means a new policy a parent consents to at child-create time.
POLICY_VERSION = "2026-06-03"

# A fixed dummy Argon2id PIN hash, verified against on the "no such parent / username"
# login path so an attacker cannot tell an existent account from a nonexistent one by
# timing (the not-found branch must take roughly as long as a real verify). OWASP
# enumeration/credential-stuffing defense, mirroring parent_auth_service._DUMMY_HASH.
_DUMMY_PIN_HASH = hash_pin("0000")


def _now() -> datetime:
    """The real wall clock (UTC). Isolated here so the policy stays the explicit-``now`` form."""
    return datetime.now(UTC)


def _as_aware_utc(value: datetime | None) -> datetime | None:
    """Normalize a DB-read timestamp to tz-aware UTC before comparing it against ``now``.

    The ``pin_locked_until`` column is ``DateTime(timezone=True)``: Postgres round-trips it
    tz-aware, but SQLite (the test/default backend) drops the tzinfo and returns it NAIVE.
    The lockout policy compares against a tz-aware ``now``, so a naive value would raise
    ``TypeError`` (can't compare naive vs aware). We attach UTC to a naive value — every
    timestamp we ever WRITE is computed in UTC (``_now`` / ``now + LOCKOUT_DURATION``), so
    re-tagging the dropped tzinfo as UTC restores the original instant. A value that is
    already aware is left untouched.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class UsernameTakenError(Exception):
    """Create/duplicate: the username is already in use within this parent's household."""


class ChildNotFoundError(Exception):
    """The named child does not exist OR is not owned by this parent (BOLA → 404, no leak)."""


class ChildLockedError(Exception):
    """Child login refused: too many wrong PINs; the account is locked (→ 423)."""


class InvalidChildCredentialsError(Exception):
    """Child login failed: unknown parent / username / wrong PIN — ONE generic error (no enum)."""


@dataclass(frozen=True)
class IssuedChildSession:
    """A freshly minted child session the route turns into cookies (Netflix-style switch)."""

    token: str
    csrf_token: str
    ttl: timedelta


@dataclass(frozen=True)
class ChildSessionOutcome:
    """What opening a child session returns: the child profile + the session to set."""

    child: ChildSessionResponse
    session: IssuedChildSession


def _issue_child_session(
    db: OrmSession, *, learner_id: int, signing_key: str, now: datetime
) -> IssuedChildSession:
    """Mint a child session JWT + its revocable AuthSession row + a CSRF token.

    Mirrors ``parent_auth_service._issue_parent_session`` but with the ``child`` kind and
    the shorter child TTL (a child often uses a shared/school device). The ``jti`` ties the
    JWT to a revocable ``AuthSession`` row so the parent kill-switch actually works.
    """
    jti = uuid4().hex
    expires_at = now + CHILD_SESSION_TTL
    token = mint_session_token(
        learner_id=learner_id,
        kind=CHILD_KIND,
        jti=jti,
        secret=signing_key,
        issued_at=now,
        ttl=CHILD_SESSION_TTL,
    )
    repo.create_auth_session(
        db, learner_id=learner_id, jti=jti, kind=CHILD_KIND, expires_at=expires_at
    )
    return IssuedChildSession(token=token, csrf_token=generate_csrf_token(), ttl=CHILD_SESSION_TTL)


def create_child_account(
    db: OrmSession,
    *,
    parent_id: int,
    display_name: str,
    grade_level: int,
    locale: str,
    username: str,
    pin: str,
    ip_address: str | None,
) -> ChildCredentialResponse:
    """Create one child for ``parent_id`` and stamp the COPPA consent in the same commit.

    Raises ``InvalidPinError`` (caller → 400) if the PIN is not four digits, and
    ``UsernameTakenError`` (caller → 409) if the username collides within this household.
    The ``public_id`` is server-generated (UUID4) so the client can never set it; the PIN
    is Argon2id-hashed before it reaches the repository (which never sees the plaintext).
    """
    validate_pin(pin)  # InvalidPinError → 400 at the route
    public_id = uuid4().hex
    child = repo.create_child(
        db,
        parent_id=parent_id,
        public_id=public_id,
        display_name=display_name,
        grade_level=grade_level,
        locale=locale,
        child_username=username,
        pin_hash=hash_pin(pin),
    )
    try:
        # flush assigns child.id AND surfaces the per-parent unique-username collision
        # (uq_learner_parent_username) as an IntegrityError before we link the consent row.
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise UsernameTakenError from exc

    # Consent commits in the same unit of work as the child: a child never exists without
    # its proof of verifiable parental consent (COPPA, RESEARCH.md).
    repo.record_consent(
        db,
        parent_id=parent_id,
        child_id=child.id,
        policy_version=POLICY_VERSION,
        ip_address=ip_address,
    )
    db.commit()
    return ChildCredentialResponse(public_id=public_id, username=username)


def list_children(db: OrmSession, *, parent_id: int) -> list[ChildSummary]:
    """Return the parent's children as dashboard/profile-picker summaries (no secrets)."""
    children: Sequence[Learner] = repo.get_children_of_parent(db, parent_id)
    return [_to_summary(child) for child in children]


def get_child_summary(db: OrmSession, *, parent_id: int, public_id: str) -> ChildSummary:
    """Return ONE owned child as a summary, or raise ``ChildNotFoundError`` (BOLA → 404)."""
    child = _require_owned_child(db, parent_id=parent_id, public_id=public_id)
    return _to_summary(child)


def reset_child_pin(db: OrmSession, *, parent_id: int, public_id: str, pin: str) -> None:
    """Set a new PIN for an owned child and clear its lockout. 404 if not owned, 400 on bad PIN.

    Resetting the PIN also resets ``failed_pin_attempts`` / ``pin_locked_until`` so a parent
    helping a locked-out child immediately restores access (the new PIN is the source of
    truth; the old failure window is moot).
    """
    validate_pin(pin)  # InvalidPinError → 400 at the route
    child = _require_owned_child(db, parent_id=parent_id, public_id=public_id)
    child.pin_hash = hash_pin(pin)
    child.failed_pin_attempts = 0
    child.pin_locked_until = None
    db.commit()


def delete_child(db: OrmSession, *, parent_id: int, public_id: str) -> None:
    """Delete an owned child (COPPA parental deletion right). 404 if not owned."""
    child = _require_owned_child(db, parent_id=parent_id, public_id=public_id)
    db.delete(child)
    db.commit()


def open_child_session_for_parent(
    db: OrmSession, *, parent_id: int, public_id: str, signing_key: str, now: datetime
) -> ChildSessionOutcome:
    """Open a child session for the AUTHENTICATED parent's own child (profile-pick at home).

    No PIN is required: the parent is already authenticated and owns the child, so this is a
    Netflix-style profile switch. Ownership is verified (BOLA → 404 otherwise). The route
    then sets the child cookie, which REPLACES the parent's cookie — that is intended.
    """
    child = _require_owned_child(db, parent_id=parent_id, public_id=public_id)
    session = _issue_child_session(db, learner_id=child.id, signing_key=signing_key, now=now)
    outcome = ChildSessionOutcome(
        child=ChildSessionResponse(public_id=public_id, display_name=child.display_name),
        session=session,
    )
    db.commit()
    return outcome


def sign_out_child_everywhere(db: OrmSession, *, parent_id: int, public_id: str) -> None:
    """Revoke every live session for an owned child (the parent kill-switch). 404 if not owned."""
    child = _require_owned_child(db, parent_id=parent_id, public_id=public_id)
    repo.revoke_all_sessions_for_learner(db, child.id, _now())
    db.commit()


def child_login(
    db: OrmSession,
    *,
    username: str,
    pin: str,
    signing_key: str,
    now: datetime,
) -> ChildSessionOutcome:
    """Independent child login (school/shared device): username + PIN (no parent email).

    Owner decision 2026-06-04: a kid does not know their parent's email, so login is the
    globally-unique username + the 4-digit PIN alone. Failure modes:

      - an unknown username or a wrong PIN both raise ONE ``InvalidChildCredentialsError``
        (→ generic 401), so a username cannot be confirmed by the error. The unknown-username
        path verifies a dummy hash so timing does not reveal it;
      - a child whose lockout window is open raises ``ChildLockedError`` (→ 423) before any
        PIN check (online brute-force defense, ``app.auth.pin_lockout`` — the control that
        now carries the weight, since usernames are globally enumerable).

    On success the lockout counters reset, a child session is minted, and the unit of work
    commits. On a wrong PIN the new failure count / lock instant are persisted and committed
    before the generic 401, so the lockout actually advances across attempts.
    """
    child = repo.get_child_by_username(db, username)
    if child is None or child.pin_hash is None:
        verify_pin(_DUMMY_PIN_HASH, pin)  # equalize timing; result ignored
        raise InvalidChildCredentialsError

    state = LockoutState(
        failed_attempts=child.failed_pin_attempts,
        locked_until=_as_aware_utc(child.pin_locked_until),
    )
    if is_locked(state, now):
        raise ChildLockedError

    if not verify_pin(child.pin_hash, pin):
        # Persist the advanced lockout window (may trip the lock) before refusing.
        new_state = after_failed_attempt(state, now)
        child.failed_pin_attempts = new_state.failed_attempts
        child.pin_locked_until = new_state.locked_until
        db.commit()
        raise InvalidChildCredentialsError

    cleared = after_successful_attempt()
    child.failed_pin_attempts = cleared.failed_attempts
    child.pin_locked_until = cleared.locked_until
    session = _issue_child_session(db, learner_id=child.id, signing_key=signing_key, now=now)
    outcome = ChildSessionOutcome(
        child=ChildSessionResponse(
            public_id=child.public_id or "", display_name=child.display_name
        ),
        session=session,
    )
    db.commit()
    return outcome


def export_child_data(db: OrmSession, *, parent_id: int, public_id: str) -> dict[str, Any]:
    """Return everything we store about an owned child (the COPPA review/export right).

    COPPA gives a parent the right to REVIEW the personal information collected from their
    child (FTC COPPA Rule, RESEARCH.md). This gathers it into one JSON-able payload: the
    profile, the recorded consent audit trail, the per-KC mastery, and the volume of learning
    activity. BOLA-scoped via ``_require_owned_child`` → a foreign ``public_id`` raises
    ``ChildNotFoundError`` (404), so a parent can only export their OWN child's data.
    Read-only (no commit).
    """
    child = _require_owned_child(db, parent_id=parent_id, public_id=public_id)
    mastery = repo.load_mastery_states(db, child.id)
    turns = repo.load_turns_for_learner(db, child.id)
    consents = repo.get_consent_records_for_child(db, child.id)
    return {
        "profile": {
            "public_id": child.public_id,
            "display_name": child.display_name,
            "grade_level": child.grade_level,
            "locale": child.locale,
            "username": child.child_username,
            "created_at": child.created_at.isoformat(),
        },
        "consent": [
            {
                "policy_version": c.policy_version,
                "method": c.method,
                "consented_at": c.consented_at.isoformat(),
            }
            for c in consents
        ],
        "mastery": [
            {
                "kc_id": m.kc_id,
                "p_known": m.bkt_probability,
                "attempts": m.attempt_count,
                "confirmed": m.confirmed,
            }
            for m in mastery
        ],
        "total_turns": len(turns),
    }


def _require_owned_child(db: OrmSession, *, parent_id: int, public_id: str) -> Learner:
    """Resolve a child by ``public_id`` scoped to ``parent_id``, or raise ``ChildNotFoundError``.

    The single BOLA chokepoint (OWASP API #1): every parent-authed operation on a specific
    child funnels through here, so ownership is checked in exactly one place and a foreign
    or unknown ``public_id`` is indistinguishable — both become a 404, never another
    family's data.
    """
    child = repo.get_child_for_parent(db, parent_id, public_id)
    if child is None:
        raise ChildNotFoundError
    return child


def _to_summary(child: Learner) -> ChildSummary:
    """Project a child ``Learner`` to the no-secrets summary the parent surface shows."""
    return ChildSummary(
        public_id=child.public_id or "",
        display_name=child.display_name,
        grade_level=child.grade_level,
        locale=child.locale,
    )
