"""Parent-auth orchestration: signup, login, email verification (Slice S3).

Routes call this; this calls the repository + the auth primitives (CLAUDE.md §7 — no
business logic in handlers, no queries in services). It owns the unit of work (commits),
mirroring the existing ``current_learner`` seam which also commits its mapping write.

Security posture pinned here (RESEARCH.md COPPA/OWASP):
  - passwords are validated (strength) then Argon2id-hashed before they ever reach the
    repository (which stores only the hash);
  - login gives ONE generic error for "no such parent" and "wrong password", and hashes a
    dummy on the not-found path so timing cannot enumerate accounts;
  - signup issues a session (cookie token + CSRF) AND sends a COPPA email-verification
    link; ``email_verified`` starts False until the parent clicks it (the consent anchor).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.api.parent_auth_schemas import ParentMeResponse
from app.api.parent_session import PARENT_SESSION_TTL
from app.auth.csrf import generate_csrf_token
from app.auth.google import InvalidIdTokenError, google_client_id, verify_google_id_token
from app.auth.passwords import hash_password, validate_password_strength, verify_password
from app.auth.tokens import PARENT_KIND, mint_session_token
from app.db import repositories as repo
from app.db.models import Learner
from app.notifications.email_sender import EmailSender

# The token "kind" for an email-verification link (distinct from a session token). We reuse
# the audited JWT mint/verify from tokens.py with this kind rather than a second crypto path.
EMAIL_VERIFY_KIND = "email_verify"
_EMAIL_VERIFY_TTL = timedelta(hours=24)

# A fixed dummy Argon2id hash, verified against on the "no such parent" path so a login
# probe takes the same time whether or not the account exists (enumeration defense).
_DUMMY_HASH = hash_password("dummy-password-for-constant-time-login")


class EmailTakenError(Exception):
    """Signup with an email that already has a parent account."""


class InvalidCredentialsError(Exception):
    """Login with no matching parent or a wrong password (one generic error — no enum)."""


class GoogleNotConfiguredError(Exception):
    """Google sign-in was attempted but GOOGLE_CLIENT_ID is unset (caller → 503)."""


@dataclass(frozen=True)
class IssuedSession:
    """A freshly minted session the route turns into cookies."""

    token: str
    csrf_token: str
    ttl: timedelta


@dataclass(frozen=True)
class AuthOutcome:
    """What an authenticating call returns: the parent profile + the session to set."""

    me: ParentMeResponse
    session: IssuedSession


def _issue_parent_session(
    db: OrmSession, *, learner_id: int, signing_key: str, now: datetime
) -> IssuedSession:
    """Mint a parent session JWT + its revocable AuthSession row + a CSRF token."""
    jti = uuid4().hex
    expires_at = now + PARENT_SESSION_TTL
    token = mint_session_token(
        learner_id=learner_id,
        kind=PARENT_KIND,
        jti=jti,
        secret=signing_key,
        issued_at=now,
        ttl=PARENT_SESSION_TTL,
    )
    repo.create_auth_session(
        db, learner_id=learner_id, jti=jti, kind=PARENT_KIND, expires_at=expires_at
    )
    return IssuedSession(token=token, csrf_token=generate_csrf_token(), ttl=PARENT_SESSION_TTL)


def signup_parent(
    db: OrmSession,
    *,
    email: str,
    password: str,
    signing_key: str,
    now: datetime,
    email_sender: EmailSender,
    verify_base_url: str,
) -> AuthOutcome:
    """Create an email/password parent, open a session, and send the verification email.

    Raises ``WeakPasswordError`` (caller → 400) if the password fails policy and
    ``EmailTakenError`` (caller → 409) if the email already has a parent account. The
    email send is best-effort (the sender swallows transport errors).
    """
    validate_password_strength(password)  # WeakPasswordError → 400 at the route
    if repo.get_parent_by_email(db, email) is not None:
        raise EmailTakenError
    learner = repo.create_parent_with_password(
        db, email=email, password_hash=hash_password(password)
    )
    try:
        db.flush()  # assign learner.id; surfaces the unique-session_id collision as IntegrityError
    except IntegrityError as exc:
        db.rollback()
        raise EmailTakenError from exc

    session = _issue_parent_session(db, learner_id=learner.id, signing_key=signing_key, now=now)
    verify_token = mint_session_token(
        learner_id=learner.id,
        kind=EMAIL_VERIFY_KIND,
        jti="email-verify",  # not a session; no AuthSession row backs it
        secret=signing_key,
        issued_at=now,
        ttl=_EMAIL_VERIFY_TTL,
    )
    me = ParentMeResponse(email=learner.email, email_verified=learner.email_verified)
    db.commit()
    # Send AFTER commit so we never email a link for a parent that failed to persist.
    email_sender.send_verification_email(
        to_email=learner.email or email,
        verify_url=f"{verify_base_url}?token={verify_token}",
    )
    return AuthOutcome(me=me, session=session)


def login_parent(
    db: OrmSession, *, email: str, password: str, signing_key: str, now: datetime
) -> AuthOutcome:
    """Authenticate an email/password parent and open a session, or raise InvalidCredentialsError.

    One generic failure for both "no such parent" and "wrong password"; the not-found path
    still runs a hash verify (against a dummy) so timing does not reveal which it was.
    """
    learner = repo.get_parent_by_email(db, email)
    if learner is None or learner.password_hash is None:
        verify_password(_DUMMY_HASH, password)  # equalize timing; result ignored
        raise InvalidCredentialsError
    if not verify_password(learner.password_hash, password):
        raise InvalidCredentialsError

    session = _issue_parent_session(db, learner_id=learner.id, signing_key=signing_key, now=now)
    me = ParentMeResponse(email=learner.email, email_verified=learner.email_verified)
    db.commit()
    return AuthOutcome(me=me, session=session)


def google_login_parent(
    db: OrmSession, *, id_token: str, signing_key: str, now: datetime
) -> AuthOutcome:
    """Sign a parent in via Google and open a session (idempotent on the Google sub).

    Verifies the Google ID token with Google's official library (app.auth.google — we do
    not hand-roll JWT/JWKS), then maps the stable ``sub`` to a parent Learner row
    (``role="parent"``, ``email_verified=True`` — Google asserts a verified email, so no
    separate verification step is needed). Raises ``GoogleNotConfiguredError`` (→ 503) when
    GOOGLE_CLIENT_ID is unset, and ``InvalidCredentialsError`` (→ 401) for any token failure
    (the verifier already collapses the reason — no detail leak).
    """
    client_id = google_client_id()
    if client_id is None:
        raise GoogleNotConfiguredError
    try:
        identity = verify_google_id_token(id_token, client_id=client_id)
    except InvalidIdTokenError as exc:
        raise InvalidCredentialsError from exc

    parent = repo.get_or_create_parent_by_google_sub(db, identity.sub, email=identity.email)
    db.flush()
    session = _issue_parent_session(db, learner_id=parent.id, signing_key=signing_key, now=now)
    me = ParentMeResponse(email=parent.email, email_verified=parent.email_verified)
    db.commit()
    return AuthOutcome(me=me, session=session)


def verify_parent_email(db: OrmSession, *, token: str, signing_key: str, now: datetime) -> bool:
    """Mark a parent's email verified from a verification token. Returns success.

    A missing/expired/wrong-kind token, or one whose learner is not a parent, returns
    False (the route maps that to a generic 400) — no detail leak.
    """
    from app.auth.tokens import decode_session_token  # local: avoid a top-level cycle hint

    claims = decode_session_token(token, secret=signing_key, now=now)
    if claims is None or claims.kind != EMAIL_VERIFY_KIND:
        return False
    learner = db.get(Learner, claims.learner_id)
    if learner is None or learner.role != "parent":
        return False
    learner.email_verified = True
    db.commit()
    return True
