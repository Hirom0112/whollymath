"""Mint + verify our own short-lived session JWTs — confined to ``auth/`` (S2).

SECURITY-SENSITIVE (Slice auth/parent-child, owner decision 2026-06-03). ``google.py``
only VERIFIES Google's tokens; a parent/child session needs a token WE issue. We use the
audited ``PyJWT`` library (we do not hand-roll JWT/crypto — CLAUDE.md §8.7) with HS256 and
a server-held signing key (from Secrets Manager in prod).

Design (OWASP Authentication / JWT guidance, RESEARCH.md):

  - the token carries only ``sub`` (learner id), ``kind`` ("parent"/"child"), a unique
    ``jti``, ``iat`` and ``exp`` — no PII;
  - the ``jti`` links the token to a REVOCABLE server-side session record (see the
    ``AuthSession`` table + repository): the JWT proves authenticity, the DB row proves
    the session is still live, so a parent's "sign out everywhere" / kill-switch actually
    works (a bare stateless JWT cannot be un-issued);
  - :func:`decode_session_token` NEVER raises and never half-trusts — a wrong key, a
    tampered token, malformed input, or an expired token all return ``None`` (no side
    channel). Expiry is checked against an EXPLICIT ``now`` so the server owns the clock
    and the behavior is deterministic/testable.

This module is pure: it imports only ``jwt`` + stdlib, holds no identity beyond the
opaque ids it copies, and reaches no mastery/policy/LLM/domain code (invariant 8). The
signing key is passed IN by the caller (see :func:`session_signing_key` for the env read)
so the crypto stays a pure function of its inputs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

_ALGORITHM = "HS256"

# The two session kinds. A parent session may manage children; a child session is the
# learner themselves. ``kind`` gates which surface the token may use (invariant 8 —
# identity gates surfaces, never turn-loop decisions).
PARENT_KIND = "parent"
CHILD_KIND = "child"


@dataclass(frozen=True)
class SessionClaims:
    """The verified, minimal claims carried by a session token."""

    learner_id: int
    kind: str
    jti: str


def mint_session_token(
    *,
    learner_id: int,
    kind: str,
    jti: str,
    secret: str,
    issued_at: datetime,
    ttl: timedelta,
) -> str:
    """Return a signed HS256 session JWT for ``learner_id``.

    ``jti`` is the caller-supplied unique token id that ties this JWT to its revocable
    server-side ``AuthSession`` row. ``issued_at`` + ``ttl`` set ``iat``/``exp`` (a short
    TTL keeps a stolen token's window small; the refresh/renew path mints a fresh one).
    """
    payload = {
        "sub": str(learner_id),
        "kind": kind,
        "jti": jti,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + ttl).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_session_token(token: str, *, secret: str, now: datetime) -> SessionClaims | None:
    """Return the verified claims, or ``None`` if the token is not trustworthy right now.

    Verifies the HS256 signature with ``secret`` and the structural shape, then enforces
    expiry against the EXPLICIT ``now`` (we disable PyJWT's internal exp check so the
    server controls the clock — deterministic + testable). Any failure — bad signature,
    tampering, malformed token, missing claim, or ``now`` past ``exp`` — yields ``None``
    and never raises (no side channel).
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            # We enforce exp ourselves against `now`; disable the library's wall-clock check.
            options={"verify_exp": False},
        )
        exp = int(payload["exp"])
        if int(now.timestamp()) >= exp:
            return None
        return SessionClaims(
            learner_id=int(payload["sub"]),
            kind=str(payload["kind"]),
            jti=str(payload["jti"]),
        )
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        return None


def session_signing_key() -> str | None:
    """The HS256 signing key from the environment, or ``None`` if unconfigured.

    Mirrors ``google.py``'s ``google_client_id()``: read once from ``SESSION_SIGNING_KEY``
    (set via ``.env`` in dev, Secrets Manager in prod — CLAUDE.md §10), returning ``None``
    when unset so the API layer can fail closed (refuse to mint/accept sessions) rather
    than signing with an empty key.
    """
    value = os.environ.get("SESSION_SIGNING_KEY", "").strip()
    return value or None
