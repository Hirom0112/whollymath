"""Tests for the double-submit CSRF token check (Slice auth/parent-child, S3).

Because parent/child sessions ride in cookies (auto-sent by the browser), every
state-changing request must also prove it came from OUR app, not a forged cross-site
form. We use the signed-free double-submit pattern: a readable ``wm_csrf`` cookie whose
value the client echoes in an ``X-CSRF-Token`` header; the server requires the two to
match. An attacker's cross-site request can neither read the cookie (same-origin policy)
nor set the custom header cross-origin, so it cannot satisfy the check.

This pins the pure comparison: both sides present and equal (constant-time) → ok;
anything missing or mismatched → rejected.
"""

from __future__ import annotations

from app.auth import csrf


def test_generated_tokens_are_nonempty_and_vary() -> None:
    a = csrf.generate_csrf_token()
    b = csrf.generate_csrf_token()
    assert a and b
    assert a != b  # random per issue


def test_matching_tokens_pass() -> None:
    token = csrf.generate_csrf_token()
    assert csrf.verify_csrf(cookie_token=token, header_token=token) is True


def test_mismatched_tokens_fail() -> None:
    assert csrf.verify_csrf(cookie_token="aaa", header_token="bbb") is False


def test_missing_either_side_fails() -> None:
    assert csrf.verify_csrf(cookie_token=None, header_token="x") is False
    assert csrf.verify_csrf(cookie_token="x", header_token=None) is False
    assert csrf.verify_csrf(cookie_token="", header_token="") is False
