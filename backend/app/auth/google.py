"""Verify Google ID tokens with Google's OFFICIAL library — confined to ``auth/`` (Slice PL.3).

SECURITY-SENSITIVE. We do NOT hand-roll JWT/JWKS/crypto (PROJECT.md §3.12 "don't build
your own auth", CLAUDE.md §8.7). The single source of truth for "is this Google ID token
valid" is Google's ``google.oauth2.id_token.verify_oauth2_token``, which fetches Google's
JWKS and checks the RS256 signature, the issuer, the audience, and expiry. This module is
a thin, conservative wrapper around it:

  - it forwards the token + the configured ``client_id`` (as the ``audience``) to the
    official verifier;
  - it collapses EVERY failure mode (expired, wrong audience, bad signature, malformed,
    wrong issuer, or any unexpected error) into a single ``InvalidIdTokenError`` and never
    leaks the underlying error detail to callers (an auth layer must not hand an attacker a
    side-channel via error text);
  - it re-asserts the issuer is one of Google's even though the library already enforces it
    (defense in depth — a belt-and-suspenders check the brief requires);
  - it returns only the minimal verified identity: ``GoogleIdentity(sub, email)``.

Layering (ARCHITECTURE.md §14 invariant 8): the verified IDENTITY produced here NEVER
reaches the mastery model, the policy, or the LLM. This module therefore imports ONLY
google-auth + stdlib + the local ``GoogleIdentity`` type — it must not import
``app.mastery`` / ``app.policy`` / ``app.llm`` / ``app.domain`` (enforced by a structural
test, ``tests/auth/test_invariant8_imports.py``). The auth layer's only output downstream
is a ``learner_id`` used for persistence/continuity; the turn decision never sees identity.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

# The two issuer strings Google stamps into an ID token's ``iss`` claim. The official
# verifier already accepts exactly these; we re-check against this set as defense in depth.
_GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


@dataclass(frozen=True)
class GoogleIdentity:
    """The minimal verified identity from a Google ID token (Slice PL.3).

    ``sub`` is the stable Google account id — the key a learner is mapped to (we store NO
    passwords). ``email`` is optional (a token may not carry it, and we never require it).
    Frozen because a verified identity is read-only: nothing downstream may mutate it, and
    it must not become a mutable carrier that leaks into other layers (invariant 8).
    """

    sub: str
    email: str | None


class InvalidIdTokenError(Exception):
    """A presented token failed verification, for ANY reason (Slice PL.3).

    Deliberately ONE opaque error for every failure mode (bad signature, wrong audience,
    expired, malformed, wrong issuer, missing ``sub``, or an unexpected library error). The
    message is generic on purpose: an auth layer must not leak why a token was rejected, so
    callers (and ultimately an attacker probing the endpoint) learn only "invalid", never the
    underlying detail. The route maps this to a 401.
    """


def verify_google_id_token(token: str, *, client_id: str) -> GoogleIdentity:
    """Verify a Google ID ``token`` for our ``client_id`` and return its identity.

    Delegates the cryptographic verification to Google's official
    ``verify_oauth2_token`` (RS256 signature against Google's JWKS, issuer, audience ==
    ``client_id``, expiry). On success we additionally assert the issuer is Google's and that
    a ``sub`` is present, then return ``GoogleIdentity(sub, email)``.

    On ANY failure — a library exception (expired/wrong-aud/bad-sig/malformed/wrong-issuer),
    a non-Google issuer, or a missing ``sub`` — we raise ``InvalidIdTokenError`` with a
    generic message and ``from None`` so the underlying detail never reaches the caller
    (no error-text side channel). This function makes a network call inside the library (the
    JWKS fetch) and is therefore NOT on the sub-100ms turn loop — it runs only on the auth
    path (a login / ``/me`` call), never inside ``/turn`` (§8.1, invariant 8).
    """
    try:
        claims = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=client_id,
        )
    except Exception:
        # Collapse every verification failure to one opaque error; ``from None`` drops the
        # underlying exception so its message cannot leak through the chain.
        raise InvalidIdTokenError("invalid Google ID token") from None

    # Defense in depth: the library already enforces the issuer, but the brief requires we
    # assert it ourselves. A non-Google issuer is treated exactly like any other failure.
    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise InvalidIdTokenError("invalid Google ID token") from None

    sub = claims.get("sub")
    if not sub:
        # No stable account id ⇒ not a usable identity.
        raise InvalidIdTokenError("invalid Google ID token") from None

    email = claims.get("email")
    return GoogleIdentity(sub=str(sub), email=str(email) if email is not None else None)


def google_client_id() -> str | None:
    """The configured Google OAuth client id, or ``None`` when auth is not configured.

    Reads ``GOOGLE_CLIENT_ID`` from the environment (``.env`` locally via python-dotenv,
    Secrets Manager in prod — CLAUDE.md §10), mirroring the "optional, degrades gracefully"
    posture of the LangSmith tracing flag (Slice PL.0). ``None`` means accounts are not set
    up for this process: the anonymous session-id flow is unaffected, and a presented token
    is rejected (the dependency turns it into a 401 "auth not configured"). Going live is the
    operational step of setting a real client id.
    """
    value = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    return value or None


__all__ = [
    "GoogleIdentity",
    "InvalidIdTokenError",
    "google_client_id",
    "verify_google_id_token",
]
