"""Contract tests for the child-account endpoints (Slice auth/parent-child, S3).

Drives the real ASGI stack with the cookie-aware client (the parent/child surface uses
HttpOnly session cookies + double-submit CSRF, owner decision 2026-06-03). Mirrors
``test_parent_auth.py``. Pins the behavior matrix:

  - a parent creates a child → 201 returns the username + opaque public_id; it lists;
  - a bad PIN → 400; a duplicate username within the same household → 409;
  - **BOLA (OWASP API #1):** parent A asking for parent B's child public_id → 404, never
    another family's data;
  - reset-pin → 204; delete → 204 then the list is empty;
  - profile-pick (``start-session``) opens a CHILD session for the parent's own child;
  - independent ``/child/login``: right email+username+PIN → 200 + cookie, wrong PIN → 401,
    unknown parent email → 401 (one generic error, no enumeration);
  - **PIN lockout:** 5 wrong PINs lock the account, so a 6th attempt with the RIGHT PIN is
    still refused with 423;
  - sign-out-everywhere → 204.

The child_account_router is not wired into ``create_app`` yet (the owner wires it); the app
fixture mounts it so these contract tests exercise the real router on the real stack.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.app import create_app
from app.api.child_account_routes import child_account_router
from app.api.parent_auth_routes import get_email_sender
from app.db.engine import create_all, create_session_factory
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.api.asgi_client import CookieClient

_GOOD_PASSWORD = "a-long-enough-passphrase"
_GOOD_PIN = "1234"


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
    # The child router is wired by the owner in app.py; mount it here so the contract tests
    # run against the real router on the real stack.
    application.include_router(child_account_router)
    return application


@pytest.fixture(autouse=True)
def _configure_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sessions are CONFIGURED (a signing key is set); cookies non-Secure so http tests work."""
    monkeypatch.setenv("SESSION_SIGNING_KEY", "test-signing-key-not-a-real-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")


def _signed_up_parent(app: FastAPI, email: str) -> CookieClient:
    """Sign a parent up and return the authed cookie client (its session cookie is set)."""
    client = CookieClient(app)
    status, _ = client.post("/parent/signup", {"email": email, "password": _GOOD_PASSWORD})
    assert status == 201
    return client


def _create_child(
    client: CookieClient,
    *,
    username: str = "kiddo",
    pin: str = _GOOD_PIN,
    display_name: str = "Kid One",
) -> tuple[int, object]:
    return client.post(
        "/parent/children",
        {"display_name": display_name, "username": username, "pin": pin},
    )


def test_create_child_returns_credentials_and_lists(app: FastAPI) -> None:
    parent = _signed_up_parent(app, "mom@example.com")
    status, body = _create_child(parent, username="kiddo")
    assert status == 201
    assert body["username"] == "kiddo"
    assert isinstance(body["public_id"], str) and body["public_id"]

    # The new child shows up in the parent's list.
    status, listing = parent.get("/parent/children")
    assert status == 200
    assert len(listing) == 1
    assert listing[0]["display_name"] == "Kid One"
    assert listing[0]["public_id"] == body["public_id"]


def test_create_child_requires_parent_session(app: FastAPI) -> None:
    # No parent cookie → 401 (the parent surface is gated).
    status, _ = CookieClient(app).post(
        "/parent/children", {"display_name": "X", "username": "nope", "pin": _GOOD_PIN}
    )
    assert status == 401


def test_create_child_bad_pin_is_400(app: FastAPI) -> None:
    parent = _signed_up_parent(app, "badpin@example.com")
    status, _ = parent.post(
        "/parent/children",
        {"display_name": "Kid", "username": "kiddo", "pin": "12ab"},
    )
    assert status == 400


def test_create_child_duplicate_username_is_409(app: FastAPI) -> None:
    parent = _signed_up_parent(app, "dup@example.com")
    status, _ = _create_child(parent, username="twins")
    assert status == 201
    status, _ = _create_child(parent, username="twins", display_name="Kid Two")
    assert status == 409


def test_get_other_familys_child_is_404_bola(app: FastAPI) -> None:
    # Parent A and parent B each create a child.
    parent_a = _signed_up_parent(app, "a@example.com")
    _, child_a = _create_child(parent_a, username="achild")
    assert isinstance(child_a, dict)

    parent_b = _signed_up_parent(app, "b@example.com")
    _, child_b = _create_child(parent_b, username="bchild")
    assert isinstance(child_b, dict)

    # Parent A asking for parent B's child public_id gets a 404 (BOLA — never B's data).
    status, _ = parent_a.get(f"/parent/children/{child_b['public_id']}")
    assert status == 404

    # Parent A can read their OWN child (control).
    status, body = parent_a.get(f"/parent/children/{child_a['public_id']}")
    assert status == 200
    assert body["public_id"] == child_a["public_id"]


def test_reset_pin_is_204(app: FastAPI) -> None:
    parent = _signed_up_parent(app, "reset@example.com")
    _, child = _create_child(parent, username="kiddo")
    assert isinstance(child, dict)
    status, _ = parent.post(f"/parent/children/{child['public_id']}/reset-pin", {"pin": "5678"})
    assert status == 204


def test_reset_pin_other_family_is_404(app: FastAPI) -> None:
    parent_a = _signed_up_parent(app, "ra@example.com")
    parent_b = _signed_up_parent(app, "rb@example.com")
    _, child_b = _create_child(parent_b, username="bkid")
    assert isinstance(child_b, dict)
    status, _ = parent_a.post(f"/parent/children/{child_b['public_id']}/reset-pin", {"pin": "5678"})
    assert status == 404


def test_delete_child_then_list_empty(app: FastAPI) -> None:
    parent = _signed_up_parent(app, "del@example.com")
    _, child = _create_child(parent, username="kiddo")
    assert isinstance(child, dict)
    # CookieClient has no ``delete`` helper (it only needs GET/POST for the parent-auth
    # suite); drive DELETE through its cookie/CSRF-aware core so this stays a real
    # cookie-borne request (carries the session cookie + echoes X-CSRF-Token).
    status, _ = parent._drive("DELETE", f"/parent/children/{child['public_id']}", None, None)
    assert status == 204

    status, listing = parent.get("/parent/children")
    assert status == 200
    assert listing == []


def test_start_session_sets_child_cookie(app: FastAPI) -> None:
    parent = _signed_up_parent(app, "pick@example.com")
    _, child = _create_child(parent, username="kiddo", display_name="Pick Me")
    assert isinstance(child, dict)
    status, body = parent.post(f"/parent/children/{child['public_id']}/start-session")
    assert status == 200
    assert body["display_name"] == "Pick Me"
    assert body["public_id"] == child["public_id"]
    # A fresh session cookie was set (switching the cookie to the child).
    assert "wm_session" in parent.cookies


def test_start_session_other_family_is_404(app: FastAPI) -> None:
    parent_a = _signed_up_parent(app, "sa@example.com")
    parent_b = _signed_up_parent(app, "sb@example.com")
    _, child_b = _create_child(parent_b, username="bkid")
    assert isinstance(child_b, dict)
    status, _ = parent_a.post(f"/parent/children/{child_b['public_id']}/start-session")
    assert status == 404


def test_child_login_success_and_wrong_pin_and_unknown_parent(app: FastAPI) -> None:
    parent = _signed_up_parent(app, "household@example.com")
    _, child = _create_child(parent, username="kiddo", pin=_GOOD_PIN)
    assert isinstance(child, dict)

    # Right email + username + PIN → 200 + child session cookie.
    good = CookieClient(app)
    status, body = good.post(
        "/child/login",
        {"parent_email": "household@example.com", "username": "kiddo", "pin": _GOOD_PIN},
    )
    assert status == 200
    assert body["public_id"] == child["public_id"]
    assert "wm_session" in good.cookies

    # Wrong PIN → generic 401.
    bad = CookieClient(app)
    status, _ = bad.post(
        "/child/login",
        {"parent_email": "household@example.com", "username": "kiddo", "pin": "0000"},
    )
    assert status == 401

    # Unknown parent email → generic 401 (no enumeration).
    unknown = CookieClient(app)
    status, _ = unknown.post(
        "/child/login",
        {"parent_email": "nobody@example.com", "username": "kiddo", "pin": _GOOD_PIN},
    )
    assert status == 401


def test_child_login_lockout_after_five_wrong_pins(app: FastAPI) -> None:
    parent = _signed_up_parent(app, "lock@example.com")
    _, child = _create_child(parent, username="kiddo", pin=_GOOD_PIN)
    assert isinstance(child, dict)

    # Five consecutive wrong PINs trip the lockout (LOCKOUT_THRESHOLD = 5).
    for _ in range(5):
        status, _ = CookieClient(app).post(
            "/child/login",
            {"parent_email": "lock@example.com", "username": "kiddo", "pin": "0000"},
        )
        assert status == 401

    # The 6th attempt — even with the CORRECT PIN — is refused with 423 (locked).
    status, _ = CookieClient(app).post(
        "/child/login",
        {"parent_email": "lock@example.com", "username": "kiddo", "pin": _GOOD_PIN},
    )
    assert status == 423


def test_sign_out_everywhere_is_204(app: FastAPI) -> None:
    parent = _signed_up_parent(app, "kill@example.com")
    _, child = _create_child(parent, username="kiddo")
    assert isinstance(child, dict)
    status, _ = parent.post(f"/parent/children/{child['public_id']}/sign-out-everywhere")
    assert status == 204


def test_sign_out_everywhere_other_family_is_404(app: FastAPI) -> None:
    parent_a = _signed_up_parent(app, "ka@example.com")
    parent_b = _signed_up_parent(app, "kb@example.com")
    _, child_b = _create_child(parent_b, username="bkid")
    assert isinstance(child_b, dict)
    status, _ = parent_a.post(f"/parent/children/{child_b['public_id']}/sign-out-everywhere")
    assert status == 404
