"""Tests for Argon2id password + child-PIN hashing (Slice auth/parent-child, S2).

SECURITY-SENSITIVE, so this is TDD-first (CLAUDE.md §2 treats the auth layer as
load-bearing). The contract pinned here:

  - passwords + PINs are hashed with Argon2id (OWASP Password Storage Cheat Sheet
    ranks it first), salted (two hashes of the same secret differ), and verified
    without ever leaking why a verify failed (a bad/garbage hash returns False, it
    does not raise — an auth layer must not hand an attacker a side channel);
  - the policy validators enforce the NIST 800-63B / OWASP shape: a minimum length,
    a max length, a small breached/common blocklist for passwords; exactly four
    digits for a child PIN.

No network (no HaveIBeenPwned call) so the unit tests stay hermetic; the live
breached-password check is a documented hook, not exercised here.
"""

from __future__ import annotations

import pytest
from app.auth import passwords

# ── Password hashing ─────────────────────────────────────────────────────────


def test_hash_password_roundtrips() -> None:
    h = passwords.hash_password("correct horse battery staple")
    assert passwords.verify_password(h, "correct horse battery staple") is True


def test_verify_password_rejects_wrong() -> None:
    h = passwords.hash_password("correct horse battery staple")
    assert passwords.verify_password(h, "Tr0ubador&3") is False


def test_password_hash_is_argon2id_and_salted() -> None:
    a = passwords.hash_password("same-password-123")
    b = passwords.hash_password("same-password-123")
    assert a.startswith("$argon2id$")  # the OWASP-preferred variant
    assert a != b  # per-hash random salt → identical secrets hash differently


def test_verify_password_returns_false_on_garbage_hash() -> None:
    # A malformed stored hash must NOT raise (no side channel) — it just fails.
    assert passwords.verify_password("not-a-real-hash", "anything") is False


# ── PIN hashing ──────────────────────────────────────────────────────────────


def test_hash_pin_roundtrips() -> None:
    h = passwords.hash_pin("0427")
    assert passwords.verify_pin(h, "0427") is True


def test_verify_pin_rejects_wrong() -> None:
    h = passwords.hash_pin("0427")
    assert passwords.verify_pin(h, "1234") is False


def test_verify_pin_returns_false_on_garbage_hash() -> None:
    assert passwords.verify_pin("garbage", "0427") is False


# ── Password policy ──────────────────────────────────────────────────────────


def test_validate_password_rejects_too_short() -> None:
    with pytest.raises(passwords.WeakPasswordError):
        passwords.validate_password_strength("short")


def test_validate_password_rejects_common_password() -> None:
    with pytest.raises(passwords.WeakPasswordError):
        passwords.validate_password_strength("password")


def test_validate_password_rejects_overlong() -> None:
    # An absurdly long password is a DoS vector against the hasher; cap it.
    with pytest.raises(passwords.WeakPasswordError):
        passwords.validate_password_strength("a" * 200)


def test_validate_password_accepts_reasonable() -> None:
    # Should not raise.
    passwords.validate_password_strength("a-long-enough-passphrase")


# ── PIN policy ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["12", "123456", "abcd", "12a4", "", "12 4"])
def test_validate_pin_requires_exactly_four_digits(bad: str) -> None:
    with pytest.raises(passwords.InvalidPinError):
        passwords.validate_pin(bad)


@pytest.mark.parametrize("good", ["0427", "8350", "1593"])
def test_validate_pin_accepts_uncommon_four_digits(good: str) -> None:
    passwords.validate_pin(good)  # should not raise


@pytest.mark.parametrize("common", ["1234", "0000", "1111", "9999", "4321", "1212", "2580"])
def test_validate_pin_rejects_common_pins(common: str) -> None:
    # The credential-spraying defense: the popular PINs are refused at setup.
    with pytest.raises(passwords.InvalidPinError):
        passwords.validate_pin(common)


# ── Rehash hook ──────────────────────────────────────────────────────────────


def test_freshly_hashed_password_does_not_need_rehash() -> None:
    h = passwords.hash_password("a-long-enough-passphrase")
    assert passwords.needs_rehash(h) is False
