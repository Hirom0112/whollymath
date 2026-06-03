"""Argon2id hashing + policy for parent passwords and child PINs — confined to ``auth/``.

SECURITY-SENSITIVE (Slice auth/parent-child, S2; owner decision 2026-06-03). We do
NOT hand-roll crypto (CLAUDE.md §8.7, PROJECT.md §3.12 "don't build your own auth"):
the single source of truth for "hash/verify a secret" is the audited ``argon2-cffi``
``PasswordHasher``, configured for Argon2id — the variant the OWASP Password Storage
Cheat Sheet ranks first. This module is a thin, conservative wrapper:

  - it hashes with a fixed, documented Argon2id parameter set (memory/time/parallel),
    so every stored hash is salted (the library adds a per-hash random salt) and a
    future parameter bump is detectable via :func:`needs_rehash`;
  - it verifies WITHOUT leaking the failure reason: a wrong secret OR a malformed
    stored hash both return ``False`` and never raise (an auth layer must not hand an
    attacker a side channel through exceptions or error text);
  - it enforces the NIST 800-63B / OWASP password shape (length floor + ceiling, a
    small breached/common blocklist) and the child-PIN shape (exactly four digits) at
    REGISTRATION time, where giving the user specific feedback is appropriate.

Layering (ARCHITECTURE.md §14 invariant 8): this module imports ONLY ``argon2`` +
stdlib. It holds no identity and reaches no mastery/policy/LLM/domain code — it is a
pure credential primitive the API layer calls before storing a hash via the
repository (which never sees the plaintext).

On child PINs: a 4-digit PIN has only 10,000 possibilities, so Argon2id alone does
not make it strong against an *offline* guess of a leaked hash. The PIN's real
defense is online: per-account lockout + per-parent username namespacing (see
``Learner.failed_pin_attempts`` / ``pin_locked_until`` and the lockout policy). We
still hash it (defense in depth if the DB leaks) rather than storing it in clear.
"""

from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions

# Argon2id parameters. argon2-cffi defaults to the Argon2id variant. These exceed the
# OWASP minimum (m=19 MiB, t=2, p=1) and sit at its preferred server profile band
# (~64 MiB, t=3): tune ``time_cost`` up if a single hash drops well under ~250 ms on
# the deploy hardware. Pinned explicitly (not left implicit) so :func:`needs_rehash`
# has a stable target and a future bump is an intentional, reviewable change.
_TIME_COST = 3
_MEMORY_COST_KIB = 64 * 1024  # 64 MiB
_PARALLELISM = 4

_hasher = PasswordHasher(
    time_cost=_TIME_COST,
    memory_cost=_MEMORY_COST_KIB,
    parallelism=_PARALLELISM,
)

# Password length bounds (OWASP / NIST 800-63B): allow long passphrases, but cap the
# input so an absurdly long string cannot be used to DoS the (deliberately expensive)
# hasher.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# A child PIN is exactly four digits (owner decision 2026-06-03: a PIN, not a full
# password, is developmentally right for an 11-12-year-old).
_PIN_RE = re.compile(r"^\d{4}$")

# A small embedded blocklist of the most common/breached passwords. This is the
# offline, hermetic floor; the production build SHOULD additionally check a live
# breached-password corpus (e.g. the HaveIBeenPwned k-anonymity range API) — that
# call is a documented hook, intentionally NOT made here so this primitive stays
# pure, fast, and testable without network.
_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty",
        "qwertyuiop",
        "11111111",
        "iloveyou",
        "letmein",
        "welcome",
        "admin",
        "abc12345",
        "football",
        "monkey",
        "dragon",
        "sunshine",
        "princess",
        "whollymath",
    }
)


class WeakPasswordError(Exception):
    """A proposed parent password fails the registration policy (length / common)."""


class InvalidPinError(Exception):
    """A proposed child PIN is not exactly four digits."""


def hash_password(password: str) -> str:
    """Return a salted Argon2id hash of ``password`` (PHC string format)."""
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """Return whether ``password`` matches ``stored_hash`` — never raises.

    A wrong password OR a malformed/garbage stored hash both yield ``False`` so the
    caller cannot distinguish "wrong password" from "corrupt record" (no side
    channel). Verification timing is dominated by Argon2id either way.
    """
    try:
        return _hasher.verify(stored_hash, password)
    except (
        argon2_exceptions.VerifyMismatchError,
        argon2_exceptions.InvalidHashError,
        argon2_exceptions.VerificationError,
    ):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Whether ``stored_hash`` was made with weaker params than the current set.

    Lets the login path transparently upgrade a hash to stronger parameters on the
    next successful login. A malformed hash is treated as not-needing-rehash here
    (the verify step already rejected it); callers act only on a verified hash.
    """
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except argon2_exceptions.InvalidHashError:
        return False


def hash_pin(pin: str) -> str:
    """Return a salted Argon2id hash of a child ``pin`` (same hasher as passwords)."""
    return _hasher.hash(pin)


def verify_pin(stored_hash: str, pin: str) -> bool:
    """Return whether ``pin`` matches ``stored_hash`` — never raises (see verify_password)."""
    return verify_password(stored_hash, pin)


def validate_password_strength(password: str) -> None:
    """Raise :class:`WeakPasswordError` if ``password`` fails the registration policy.

    Enforced at signup/change time, where specific feedback is appropriate (it is the
    user's own new password, not a login probe). Checks: length floor + ceiling and a
    common/breached blocklist (case-insensitive). Composition rules (must-have-symbol
    etc.) are deliberately NOT imposed — NIST 800-63B advises against them.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    if password.lower() in _COMMON_PASSWORDS:
        raise WeakPasswordError("That password is too common; please choose another.")


def validate_pin(pin: str) -> None:
    """Raise :class:`InvalidPinError` unless ``pin`` is exactly four digits."""
    if not _PIN_RE.match(pin):
        raise InvalidPinError("PIN must be exactly four digits.")
