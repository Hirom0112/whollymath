"""Child-PIN brute-force lockout policy — a pure decision over login state (S2).

SECURITY-SENSITIVE (Slice auth/parent-child, owner decision 2026-06-03). A 4-digit
PIN has only 10,000 possibilities, so :mod:`app.auth.passwords` hashing alone does not
make it strong against guessing — the PIN's real defense is ONLINE rate-limiting:
after :data:`LOCKOUT_THRESHOLD` consecutive wrong PINs the account is locked for
:data:`LOCKOUT_DURATION`, which (together with per-parent username namespacing) defeats
online brute force and targeted attacks (OWASP brute-force mitigation, RESEARCH.md).

This module is PURE: every function is a deterministic function of the current
:class:`LockoutState` and an explicit ``now`` — no DB, no wall clock, no identity. The
auth endpoint maps the ``Learner.failed_pin_attempts`` / ``pin_locked_until`` columns to
and from :class:`LockoutState`, and supplies ``now``. That keeps the policy trivially
testable and keeps this off any mastery/policy/LLM path (ARCHITECTURE.md §14 invariant 8).

The counter is PER-ACCOUNT (not per-IP): an attacker spreading guesses across IPs must
still trip the same single account's counter (OWASP credential-stuffing guidance).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# After this many consecutive failures the account locks. 5 balances "don't punish a
# kid's honest fat-finger" against "cut off guessing fast" (10k keyspace / 5 per window).
LOCKOUT_THRESHOLD = 5
# How long a locked account stays locked. Long enough to make online enumeration of the
# 10k keyspace hopeless, short enough that a real child is not stranded.
LOCKOUT_DURATION = timedelta(minutes=15)


@dataclass(frozen=True)
class LockoutState:
    """The two persisted lockout fields, lifted out of the Learner row.

    ``failed_attempts`` counts consecutive failures in the CURRENT window (reset to 0
    when the account locks or on any success). ``locked_until`` is the instant the
    current lock expires, or ``None`` when the account is not locked.
    """

    failed_attempts: int
    locked_until: datetime | None


def is_locked(state: LockoutState, now: datetime) -> bool:
    """Whether a PIN attempt must be refused right now (the lock has not yet expired)."""
    return state.locked_until is not None and now < state.locked_until


def after_failed_attempt(state: LockoutState, now: datetime) -> LockoutState:
    """Return the state after one more wrong PIN.

    Increments the consecutive-failure counter; once it reaches
    :data:`LOCKOUT_THRESHOLD` the account locks for :data:`LOCKOUT_DURATION` and the
    counter resets to 0 so the next window starts clean.
    """
    attempts = state.failed_attempts + 1
    if attempts >= LOCKOUT_THRESHOLD:
        return LockoutState(failed_attempts=0, locked_until=now + LOCKOUT_DURATION)
    return LockoutState(failed_attempts=attempts, locked_until=state.locked_until)


def after_successful_attempt() -> LockoutState:
    """Return the cleared state after a correct PIN (counter 0, no lock)."""
    return LockoutState(failed_attempts=0, locked_until=None)
