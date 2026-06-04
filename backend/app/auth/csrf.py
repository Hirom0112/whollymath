"""Double-submit CSRF protection for cookie-borne sessions — confined to ``auth/`` (S3).

SECURITY-SENSITIVE (Slice auth/parent-child, owner decision 2026-06-03). Parent/child
sessions live in an HttpOnly cookie, which the browser attaches automatically — so a
forged cross-site request would otherwise ride the victim's session. The standard
defense (OWASP CSRF Cheat Sheet) is the double-submit token:

  - on login we also set a SEPARATE, readable (NOT HttpOnly) ``wm_csrf`` cookie with a
    random value;
  - the SPA reads that cookie and echoes it in an ``X-CSRF-Token`` header on every
    state-changing request;
  - the server requires cookie value == header value.

An attacker's cross-site request cannot read the cookie (same-origin policy) nor set a
custom header cross-origin (CORS preflight blocks it), so it cannot produce a matching
pair. Combined with ``SameSite`` on the session cookie this is belt-and-suspenders.

Pure module: only ``secrets`` + stdlib; holds no identity (invariant 8). The comparison
is constant-time to avoid leaking it via timing.
"""

from __future__ import annotations

import secrets

# The readable CSRF cookie name and the header the client echoes it in. Single source of
# truth so the issuing/clearing code and the verifying middleware cannot drift.
CSRF_COOKIE_NAME = "wm_csrf"
CSRF_HEADER_NAME = "x-csrf-token"


def generate_csrf_token() -> str:
    """Return a fresh, URL-safe random CSRF token (issued alongside a session)."""
    return secrets.token_urlsafe(32)


def verify_csrf(*, cookie_token: str | None, header_token: str | None) -> bool:
    """Return whether the double-submit pair is present and matches (constant-time).

    Both the cookie value and the echoed header must be present, non-empty, and equal.
    A missing or empty side fails closed.
    """
    if not cookie_token or not header_token:
        return False
    return secrets.compare_digest(cookie_token, header_token)
