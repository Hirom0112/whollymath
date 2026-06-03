"""Contract tests for the parent-auth endpoints (Slice auth/parent-child, S3).

Drives the real ASGI stack with a cookie-aware client (the parent surface uses HttpOnly
session cookies + double-submit CSRF, owner decision 2026-06-03). Pins the behavior matrix:

  - signup creates a parent, sets the session + CSRF cookies, returns the profile
    (email_verified False), and sends a verification email (the COPPA consent anchor);
  - /me requires a live session cookie (401 without one);
  - weak password → 400; duplicate email → 409;
  - login: right password → 200 + cookies; wrong password / unknown email → ONE generic 401;
  - logout revokes the session server-side (a replayed old cookie is dead) and is
    CSRF-protected (no X-CSRF-Token → 403);
  - clicking the verification link marks the email verified.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.app import create_app
from app.api.parent_auth_routes import get_email_sender
from app.db.engine import create_all, create_session_factory
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.api.asgi_client import CookieClient, post_json

_GOOD_PASSWORD = "a-long-enough-passphrase"


class _CapturingSender:
    """Fake email sender that records the last verification link (no real delivery)."""

    def __init__(self) -> None:
        self.last_url: str | None = None
        self.last_to: str | None = None

    def send_verification_email(self, *, to_email: str, verify_url: str) -> None:
        self.last_to = to_email
        self.last_url = verify_url


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def sender() -> _CapturingSender:
    return _CapturingSender()


@pytest.fixture
def app(session_factory: sessionmaker[OrmSession], sender: _CapturingSender) -> FastAPI:
    application = create_app()
    application.state.session_store.session_factory = session_factory
    application.dependency_overrides[get_email_sender] = lambda: sender
    return application


@pytest.fixture(autouse=True)
def _configure_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sessions are CONFIGURED (a signing key is set); cookies non-Secure so http tests work."""
    monkeypatch.setenv("SESSION_SIGNING_KEY", "test-signing-key-not-a-real-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")


def test_signup_sets_session_and_sends_verification(app: FastAPI, sender: _CapturingSender) -> None:
    client = CookieClient(app)
    status, body = client.post(
        "/parent/signup", {"email": "mom@example.com", "password": _GOOD_PASSWORD}
    )
    assert status == 201
    assert body == {"email": "mom@example.com", "email_verified": False}
    # Both cookies were issued.
    assert "wm_session" in client.cookies
    assert "wm_csrf" in client.cookies
    # A verification email "went out".
    assert sender.last_to == "mom@example.com"
    assert sender.last_url is not None and "token=" in sender.last_url


def test_me_requires_session(app: FastAPI) -> None:
    # No cookie → 401.
    status, _ = CookieClient(app).get("/parent/me")
    assert status == 401

    # After signup the same client's cookie authenticates /me.
    client = CookieClient(app)
    client.post("/parent/signup", {"email": "a@example.com", "password": _GOOD_PASSWORD})
    status, body = client.get("/parent/me")
    assert status == 200
    assert body["email"] == "a@example.com"


def test_signup_weak_password_is_400(app: FastAPI) -> None:
    status, _ = CookieClient(app).post(
        "/parent/signup", {"email": "b@example.com", "password": "short"}
    )
    assert status == 400


def test_signup_duplicate_email_is_409(app: FastAPI) -> None:
    CookieClient(app).post(
        "/parent/signup", {"email": "dup@example.com", "password": _GOOD_PASSWORD}
    )
    status, _ = CookieClient(app).post(
        "/parent/signup", {"email": "dup@example.com", "password": _GOOD_PASSWORD}
    )
    assert status == 409


def test_login_success_and_wrong_password(app: FastAPI) -> None:
    CookieClient(app).post(
        "/parent/signup", {"email": "log@example.com", "password": _GOOD_PASSWORD}
    )

    # Wrong password → generic 401.
    bad = CookieClient(app)
    status, _ = bad.post(
        "/parent/login", {"email": "log@example.com", "password": "wrong-password-x"}
    )
    assert status == 401

    # Right password → 200 + a fresh session cookie.
    good = CookieClient(app)
    status, body = good.post(
        "/parent/login", {"email": "log@example.com", "password": _GOOD_PASSWORD}
    )
    assert status == 200
    assert body["email"] == "log@example.com"
    assert "wm_session" in good.cookies


def test_login_unknown_email_is_generic_401(app: FastAPI) -> None:
    status, _ = CookieClient(app).post(
        "/parent/login", {"email": "nobody@example.com", "password": _GOOD_PASSWORD}
    )
    assert status == 401


def test_logout_revokes_session_and_requires_csrf(app: FastAPI) -> None:
    client = CookieClient(app)
    client.post("/parent/signup", {"email": "out@example.com", "password": _GOOD_PASSWORD})
    old_session = client.cookies["wm_session"]

    # CSRF required: a request carrying the session cookie but NO X-CSRF-Token is refused.
    status, _ = post_json(
        app, "/parent/logout", None, headers={"cookie": f"wm_session={old_session}"}
    )
    assert status == 403

    # Proper logout (client echoes the CSRF token) → 204 and cookies cleared.
    status, _ = client.post("/parent/logout")
    assert status == 204
    assert "wm_session" not in client.cookies

    # The revoked session is dead server-side: replaying the OLD cookie no longer authenticates.
    replay = CookieClient(app)
    replay.cookies["wm_session"] = old_session
    status, _ = replay.get("/parent/me")
    assert status == 401


def test_verify_email_marks_verified(app: FastAPI, sender: _CapturingSender) -> None:
    client = CookieClient(app)
    client.post("/parent/signup", {"email": "verify@example.com", "password": _GOOD_PASSWORD})
    assert sender.last_url is not None
    token = sender.last_url.split("token=", 1)[1]

    status, body = client.get(f"/parent/verify-email?token={token}")
    assert status == 200
    assert body == {"status": "verified"}

    status, me = client.get("/parent/me")
    assert me["email_verified"] is True


def test_verify_email_rejects_garbage_token(app: FastAPI) -> None:
    status, _ = CookieClient(app).get("/parent/verify-email?token=not-a-real-token")
    assert status == 400
