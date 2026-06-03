"""Tests for session-token minting/verification (Slice auth/parent-child, S2).

SECURITY-SENSITIVE, TDD-first. These are OUR OWN short-lived session JWTs (google-auth
only verifies Google's tokens, it cannot issue ours). The contract pinned here:

  - a minted token round-trips its claims (learner_id, kind, jti) under the right key;
  - a token signed with a DIFFERENT key, a tampered token, or garbage decodes to
    ``None`` — never raises, never half-trusts (no side channel);
  - expiry is enforced against an EXPLICIT ``now`` (so the test is deterministic and
    the server controls the clock), and a token past its exp decodes to ``None``.

The JWT alone is not the whole session — it is paired with a revocable server-side
record (the ``jti`` is the link); that persistence is tested separately.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.auth import tokens

_SECRET = "test-signing-key-not-a-real-secret"
_NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC)


def _mint(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "learner_id": 42,
        "kind": "parent",
        "jti": "jti-abc",
        "secret": _SECRET,
        "issued_at": _NOW,
        "ttl": timedelta(minutes=30),
    }
    kwargs.update(overrides)
    return tokens.mint_session_token(**kwargs)  # type: ignore[arg-type]


def test_token_roundtrips_claims() -> None:
    token = _mint()
    claims = tokens.decode_session_token(token, secret=_SECRET, now=_NOW)
    assert claims is not None
    assert claims.learner_id == 42
    assert claims.kind == "parent"
    assert claims.jti == "jti-abc"


def test_wrong_secret_decodes_to_none() -> None:
    token = _mint()
    assert tokens.decode_session_token(token, secret="a-different-key", now=_NOW) is None


def test_tampered_token_decodes_to_none() -> None:
    token = _mint()
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    assert tokens.decode_session_token(tampered, secret=_SECRET, now=_NOW) is None


def test_garbage_decodes_to_none() -> None:
    assert tokens.decode_session_token("not.a.jwt", secret=_SECRET, now=_NOW) is None


def test_expired_token_decodes_to_none() -> None:
    token = _mint(ttl=timedelta(minutes=30))
    later = _NOW + timedelta(minutes=31)
    assert tokens.decode_session_token(token, secret=_SECRET, now=later) is None


def test_token_valid_just_before_expiry() -> None:
    token = _mint(ttl=timedelta(minutes=30))
    almost = _NOW + timedelta(minutes=29)
    claims = tokens.decode_session_token(token, secret=_SECRET, now=almost)
    assert claims is not None
    assert claims.learner_id == 42
