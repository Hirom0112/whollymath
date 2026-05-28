"""Tests for the Google ID-token verifier (Slice PL.3).

This is SECURITY-SENSITIVE code, so the tests pin the conservative contract exactly:

  - we NEVER hit Google's network — ``google.oauth2.id_token.verify_oauth2_token`` is
    patched (CLAUDE.md §9: don't test the network/third party, test the behavior around
    it). The official library does the real RS256/JWKS/issuer/aud/expiry verification in
    production; here we assert that ``verify_google_id_token`` calls it correctly and maps
    its result/failures to OUR contract.
  - a valid token → ``GoogleIdentity(sub, email)`` (email optional).
  - EVERY failure the library can raise (expired, wrong-aud, bad-sig, malformed, wrong
    issuer) collapses to a SINGLE ``InvalidIdTokenError``, and the raised error must NOT
    carry the raw underlying message (no detail leak to callers).
  - the issuer is asserted to be Google's even though the library already checks it
    (defense in depth — the brief requires we assert it).

The verifier accepts the token + a configured ``client_id``; it never reads the env
itself (that is ``google_client_id`` / the dependency's job), keeping it a pure function
of its inputs.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.auth.google import (
    GoogleIdentity,
    InvalidIdTokenError,
    google_client_id,
    verify_google_id_token,
)

_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_RAW_SECRET = "super-secret-internal-jwks-detail-do-not-leak"


def _patch_verify(monkeypatch: pytest.MonkeyPatch, fn: Any) -> dict[str, Any]:
    """Patch the official verifier with ``fn`` and capture the args it was called with."""
    captured: dict[str, Any] = {}

    def _fake(token: str, request: Any, audience: Any = None) -> Any:
        captured["token"] = token
        captured["request"] = request
        captured["audience"] = audience
        return fn(token, request, audience)

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", _fake)
    return captured


def test_valid_token_returns_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid token yields GoogleIdentity(sub, email) from the verified claims."""
    _patch_verify(
        monkeypatch,
        lambda *_: {
            "iss": "https://accounts.google.com",
            "sub": "1234567890",
            "email": "kid@example.com",
            "aud": _CLIENT_ID,
        },
    )
    identity = verify_google_id_token("any.jwt.token", client_id=_CLIENT_ID)
    assert identity == GoogleIdentity(sub="1234567890", email="kid@example.com")


def test_valid_token_without_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """email is optional on the claims; a missing email maps to None, sub still required."""
    _patch_verify(
        monkeypatch,
        lambda *_: {"iss": "accounts.google.com", "sub": "no-email-sub"},
    )
    identity = verify_google_id_token("any.jwt.token", client_id=_CLIENT_ID)
    assert identity == GoogleIdentity(sub="no-email-sub", email=None)


def test_audience_is_passed_to_the_official_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configured client_id is forwarded as the audience the library checks."""
    captured = _patch_verify(
        monkeypatch,
        lambda *_: {"iss": "accounts.google.com", "sub": "s"},
    )
    verify_google_id_token("tok", client_id=_CLIENT_ID)
    assert captured["audience"] == _CLIENT_ID
    assert captured["token"] == "tok"


@pytest.mark.parametrize(
    "boom",
    [
        ValueError(f"Token expired. {_RAW_SECRET}"),  # lib raises ValueError on expiry
        ValueError(f"Wrong audience. {_RAW_SECRET}"),  # wrong aud
        ValueError(f"Could not verify token signature. {_RAW_SECRET}"),  # bad sig
        ValueError(f"Wrong number of segments in token. {_RAW_SECRET}"),  # malformed
        Exception(f"unexpected internal error {_RAW_SECRET}"),  # any other failure
    ],
)
def test_library_failures_collapse_to_invalid_without_leaking(
    monkeypatch: pytest.MonkeyPatch, boom: Exception
) -> None:
    """Any verifier failure → InvalidIdTokenError, with NO underlying detail leaked."""

    def _raise(*_: Any) -> Any:
        raise boom

    _patch_verify(monkeypatch, _raise)
    with pytest.raises(InvalidIdTokenError) as exc_info:
        verify_google_id_token("bad.token", client_id=_CLIENT_ID)
    # The raised error must not carry the raw underlying message (no detail leak).
    assert _RAW_SECRET not in str(exc_info.value)
    # And it must not chain the original exception's message out either.
    assert exc_info.value.__cause__ is None


def test_wrong_issuer_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if the library returned, a non-Google issuer is rejected (defense in depth)."""
    _patch_verify(
        monkeypatch,
        lambda *_: {"iss": "https://evil.example.com", "sub": "s", "email": "x@y.z"},
    )
    with pytest.raises(InvalidIdTokenError):
        verify_google_id_token("tok", client_id=_CLIENT_ID)


def test_missing_sub_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A claim set with no ``sub`` is not a usable identity → InvalidIdTokenError."""
    _patch_verify(
        monkeypatch,
        lambda *_: {"iss": "accounts.google.com", "email": "x@y.z"},
    )
    with pytest.raises(InvalidIdTokenError):
        verify_google_id_token("tok", client_id=_CLIENT_ID)


def test_google_client_id_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """google_client_id() reflects GOOGLE_CLIENT_ID, or None when unset (auth off)."""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert google_client_id() is None
    monkeypatch.setenv("GOOGLE_CLIENT_ID", _CLIENT_ID)
    assert google_client_id() == _CLIENT_ID


def test_google_identity_is_frozen() -> None:
    """GoogleIdentity is immutable — identity is read-only once verified."""
    identity = GoogleIdentity(sub="s", email=None)
    with pytest.raises(AttributeError):
        identity.sub = "other"  # type: ignore[misc]
