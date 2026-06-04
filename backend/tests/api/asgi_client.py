"""A tiny in-process ASGI client for contract tests (no extra dependencies).

WHY this exists instead of ``fastapi.testclient.TestClient``: Starlette's
TestClient requires ``httpx``, which is not installed in the backend venv, and
this slice is under a hard "no new dependencies / do not run uv add" constraint.
Rather than install httpx, we drive the real ASGI app directly through its ASGI
interface — which is exactly what TestClient does under the hood, minus the httpx
transport. This exercises the *full* FastAPI stack (routing, Pydantic validation,
status codes, JSON serialization), so these remain genuine HTTP-level contract
tests (CLAUDE.md §9), not handler-function unit tests.

The client is deliberately minimal: JSON in, status + JSON out, for the two verbs
the contract uses (GET/POST). It is test infrastructure, not product code.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

import anyio
from fastapi import FastAPI

# ASGI's message type. We annotate ``send`` with this (not ``dict``) because a
# function accepting a narrower ``dict`` is NOT assignable where ASGI expects one
# accepting the wider ``MutableMapping`` (parameter types are contravariant) —
# matching the spec type keeps mypy --strict happy. Plain alias (not the 3.12
# ``type`` statement) because the project targets py311 (pyproject target-version).
AsgiMessage = MutableMapping[str, Any]


def _request(
    app: FastAPI,
    method: str,
    path: str,
    body: Any | None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """Send one request to the ASGI ``app`` in-process; return (status, json|None).

    ``headers`` lets a contract test attach extra request headers (e.g. an
    ``Authorization: Bearer <token>`` for the Slice PL.3 auth dependency). They are
    appended to the default ``content-type``; header names are lower-cased per the ASGI
    spec (HTTP header names are case-insensitive and the spec sends them lower-cased).
    """
    body_bytes = b"" if body is None else json.dumps(body).encode("utf-8")
    captured: dict[str, Any] = {}
    chunks: list[bytes] = []

    async def receive() -> AsgiMessage:
        # Single-shot body; the contract endpoints take small JSON payloads.
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    async def send(message: AsgiMessage) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    raw_headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json")]
    for name, value in (headers or {}).items():
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))

    # Split any query string off the path: ASGI carries them in separate scope keys, and
    # Starlette matches routes on ``path`` alone, so a query must not stay glued to the path
    # (otherwise the route won't match and query params won't parse).
    path_only, _, query = path.partition("?")
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "path": path_only,
        "raw_path": path.encode("utf-8"),
        "query_string": query.encode("utf-8"),
        "headers": raw_headers,
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "root_path": "",
    }

    async def _run() -> None:
        await app(scope, receive, send)

    anyio.run(_run)

    raw = b"".join(chunks)
    parsed = json.loads(raw) if raw else None
    return captured["status"], parsed


def post_json(
    app: FastAPI, path: str, body: Any, headers: dict[str, str] | None = None
) -> tuple[int, Any]:
    """POST ``body`` as JSON to ``path``; return (status_code, parsed_json)."""
    return _request(app, "POST", path, body, headers)


def patch_json(
    app: FastAPI, path: str, body: Any, headers: dict[str, str] | None = None
) -> tuple[int, Any]:
    """PATCH ``body`` as JSON to ``path``; return (status_code, parsed_json)."""
    return _request(app, "PATCH", path, body, headers)


def get(app: FastAPI, path: str, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    """GET ``path``; return (status_code, parsed_json)."""
    return _request(app, "GET", path, None, headers)


def get_raw(app: FastAPI, path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    """GET ``path`` returning the RAW response bytes (for non-JSON, e.g. a static mp3 asset).

    The cached mascot audio is served by ``StaticFiles`` as ``audio/mpeg``, so the JSON-parsing
    ``get`` would choke on the binary body. This variant returns the status and the raw bytes so a
    contract test can assert the static mount resolves an audio path (Slice AR.3).
    """
    body_bytes = b""
    captured: dict[str, Any] = {}
    chunks: list[bytes] = []

    async def receive() -> AsgiMessage:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    async def send(message: AsgiMessage) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    raw_headers: list[tuple[bytes, bytes]] = []
    for name, value in (headers or {}).items():
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))

    path_only, _, query = path.partition("?")
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "path": path_only,
        "raw_path": path.encode("utf-8"),
        "query_string": query.encode("utf-8"),
        "headers": raw_headers,
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "root_path": "",
    }

    async def _run() -> None:
        await app(scope, receive, send)

    anyio.run(_run)
    return captured["status"], b"".join(chunks)


# ── Cookie-aware client (for the cookie-borne parent/child sessions, Slice S3) ──


class CookieClient:
    """A tiny stateful client that carries cookies across requests, like a browser.

    The parent/child auth surface uses HttpOnly session cookies + a double-submit CSRF
    token, so a contract test needs to (a) keep the Set-Cookie values the server issues
    and resend them, and (b) echo the readable ``wm_csrf`` cookie in the ``X-CSRF-Token``
    header on unsafe verbs — exactly what the real SPA does. This wraps the same in-process
    ASGI drive as ``_request`` but also captures response headers and maintains a cookie jar.
    """

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self.cookies: dict[str, str] = {}

    def _drive(
        self, method: str, path: str, body: Any | None, extra_headers: dict[str, str] | None
    ) -> tuple[int, Any]:
        body_bytes = b"" if body is None else json.dumps(body).encode("utf-8")
        captured: dict[str, Any] = {"headers": []}
        chunks: list[bytes] = []

        async def receive() -> AsgiMessage:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        async def send(message: AsgiMessage) -> None:
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]
                captured["headers"] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        raw_headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json")]
        # Send the cookie jar back, like a browser.
        if self.cookies:
            jar = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            raw_headers.append((b"cookie", jar.encode("latin-1")))
        # Echo the CSRF token (double-submit) on every request, mirroring the SPA.
        if "wm_csrf" in self.cookies:
            raw_headers.append((b"x-csrf-token", self.cookies["wm_csrf"].encode("latin-1")))
        for name, value in (extra_headers or {}).items():
            raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))

        path_only, _, query = path.partition("?")
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "path": path_only,
            "raw_path": path.encode("utf-8"),
            "query_string": query.encode("utf-8"),
            "headers": raw_headers,
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 12345),
            "root_path": "",
        }

        async def _run() -> None:
            await self._app(scope, receive, send)

        anyio.run(_run)
        self._absorb_set_cookie(captured["headers"])
        raw = b"".join(chunks)
        return captured["status"], (json.loads(raw) if raw else None)

    def _absorb_set_cookie(self, headers: list[tuple[bytes, bytes]]) -> None:
        """Update the jar from Set-Cookie response headers (value, or delete on max-age=0)."""
        for name, value in headers:
            if name.lower() != b"set-cookie":
                continue
            cookie = value.decode("latin-1")
            pair, _, attrs = cookie.partition(";")
            key, _, val = pair.partition("=")
            key, val = key.strip(), val.strip()
            if "max-age=0" in attrs.lower() or "expires=thu, 01 jan 1970" in attrs.lower():
                self.cookies.pop(key, None)
            else:
                self.cookies[key] = val

    def post(
        self, path: str, body: Any | None = None, headers: dict[str, str] | None = None
    ) -> tuple[int, Any]:
        return self._drive("POST", path, body, headers)

    def get(self, path: str, headers: dict[str, str] | None = None) -> tuple[int, Any]:
        return self._drive("GET", path, None, headers)
