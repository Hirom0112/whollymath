"""Tests for the child-PIN brute-force lockout policy (Slice auth/parent-child, S2).

A 4-digit PIN has only 10,000 possibilities, so the PIN's real defense is ONLINE:
after a few consecutive wrong PINs the account is locked for a cooldown, defeating
both online guessing and (with per-parent namespacing) targeted attacks (OWASP
brute-force mitigation, RESEARCH.md). This pins that policy as a PURE, deterministic
function of (failed_attempts, locked_until, now) — no DB, no clock — so it is trivial
to reason about and the endpoint just maps the Learner columns to/from it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.auth import pin_lockout
from app.auth.pin_lockout import LockoutState

_NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC)


def test_fresh_account_is_not_locked() -> None:
    assert pin_lockout.is_locked(LockoutState(failed_attempts=0, locked_until=None), _NOW) is False


def test_below_threshold_does_not_lock() -> None:
    state = LockoutState(failed_attempts=0, locked_until=None)
    for _ in range(pin_lockout.LOCKOUT_THRESHOLD - 1):
        state = pin_lockout.after_failed_attempt(state, _NOW)
    assert pin_lockout.is_locked(state, _NOW) is False


def test_reaching_threshold_locks_the_account() -> None:
    state = LockoutState(failed_attempts=0, locked_until=None)
    for _ in range(pin_lockout.LOCKOUT_THRESHOLD):
        state = pin_lockout.after_failed_attempt(state, _NOW)
    assert state.locked_until is not None
    assert pin_lockout.is_locked(state, _NOW) is True


def test_lockout_expires_after_the_cooldown() -> None:
    state = LockoutState(failed_attempts=0, locked_until=None)
    for _ in range(pin_lockout.LOCKOUT_THRESHOLD):
        state = pin_lockout.after_failed_attempt(state, _NOW)
    # Still locked just before the cooldown ends...
    assert pin_lockout.is_locked(state, _NOW + pin_lockout.LOCKOUT_DURATION - timedelta(seconds=1))
    # ...and unlocked once it has passed.
    assert (
        pin_lockout.is_locked(state, _NOW + pin_lockout.LOCKOUT_DURATION + timedelta(seconds=1))
        is False
    )


def test_success_resets_the_counter_and_lock() -> None:
    # A correct PIN clears the counter and any lock, regardless of prior state.
    reset = pin_lockout.after_successful_attempt()
    assert reset.failed_attempts == 0
    assert reset.locked_until is None
    assert pin_lockout.is_locked(reset, _NOW) is False
