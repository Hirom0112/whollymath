"""Tests for the in-process auth rate limiter (Slice S3, OWASP brute-force mitigation).

Two layers, matching the module's two layers:

  - ``RateLimiter`` is unit-tested DIRECTLY with explicit ``now`` values -- no clock, fully
    deterministic (CLAUDE.md §9): allowed up to ``max_hits`` in a window, blocked on the
    (max+1)th, allowed again once ``now`` advances past the window, and independent keys do
    not share a budget.
  - The FastAPI ``rate_limit`` dependency is exercised through a throwaway app driven by the
    in-process ASGI client, asserting the 3rd rapid request to a max=2 route returns 429.

``reset_all`` runs before every test so per-scope counter state never leaks between tests.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.rate_limit import RateLimiter, rate_limit, reset_all
from fastapi import Depends, FastAPI

from tests.api.asgi_client import get


@pytest.fixture(autouse=True)
def _isolate_limiters() -> Iterator[None]:
    """Clear all limiter state before AND after each test for full isolation."""
    reset_all()
    yield
    reset_all()


# ── RateLimiter unit tests (deterministic, explicit ``now``) ─────────────────────────────────


def test_allows_up_to_max_hits_in_window() -> None:
    """Exactly ``max_hits`` hits inside one window are all allowed."""
    limiter = RateLimiter(max_hits=3, window_seconds=60.0)
    assert limiter.check("k", now=0.0) is True
    assert limiter.check("k", now=1.0) is True
    assert limiter.check("k", now=2.0) is True


def test_blocks_the_hit_past_max_in_window() -> None:
    """The (max+1)th hit inside the same window is blocked."""
    limiter = RateLimiter(max_hits=3, window_seconds=60.0)
    for now in (0.0, 1.0, 2.0):
        assert limiter.check("k", now=now) is True
    assert limiter.check("k", now=3.0) is False


def test_allows_again_after_window_rolls_over() -> None:
    """Once ``now`` advances past ``window_seconds``, a fresh window opens and allows again."""
    limiter = RateLimiter(max_hits=2, window_seconds=60.0)
    assert limiter.check("k", now=0.0) is True
    assert limiter.check("k", now=10.0) is True
    assert limiter.check("k", now=20.0) is False  # over budget within the first window
    # Advance past the window (start was 0.0, window 60s -> 60.0 opens a new window).
    assert limiter.check("k", now=60.0) is True
    assert limiter.check("k", now=61.0) is True
    assert limiter.check("k", now=62.0) is False


def test_window_start_is_anchored_not_sliding() -> None:
    """The window is anchored at first-hit time; it does not slide forward on each hit."""
    limiter = RateLimiter(max_hits=2, window_seconds=10.0)
    assert limiter.check("k", now=0.0) is True  # window [0, 10)
    assert limiter.check("k", now=9.0) is True  # still in [0, 10)
    assert limiter.check("k", now=9.5) is False  # 3rd hit, still in [0, 10) -> blocked
    assert limiter.check("k", now=10.0) is True  # now [10, 20) opens -> allowed


def test_independent_keys_do_not_share_budget() -> None:
    """Two distinct keys each get their own budget; one saturating does not block the other."""
    limiter = RateLimiter(max_hits=1, window_seconds=60.0)
    assert limiter.check("a", now=0.0) is True
    assert limiter.check("a", now=1.0) is False  # 'a' is now over budget
    assert limiter.check("b", now=2.0) is True  # 'b' is untouched
    assert limiter.check("b", now=3.0) is False


def test_blocked_hits_keep_window_saturated() -> None:
    """Sustained hammering within the window stays blocked (a blocked hit still counts)."""
    limiter = RateLimiter(max_hits=1, window_seconds=60.0)
    assert limiter.check("k", now=0.0) is True
    assert limiter.check("k", now=1.0) is False
    assert limiter.check("k", now=2.0) is False  # still saturated, not reset by being blocked


def test_reset_clears_state() -> None:
    """``reset`` forgets all windows so budgets start fresh."""
    limiter = RateLimiter(max_hits=1, window_seconds=60.0)
    assert limiter.check("k", now=0.0) is True
    assert limiter.check("k", now=1.0) is False
    limiter.reset()
    assert limiter.check("k", now=2.0) is True


def test_constructor_rejects_bad_args() -> None:
    """A non-positive budget or window is a programming error -> ValueError at construction."""
    with pytest.raises(ValueError):
        RateLimiter(max_hits=0, window_seconds=60.0)
    with pytest.raises(ValueError):
        RateLimiter(max_hits=1, window_seconds=0.0)


# ── FastAPI dependency integration (in-process ASGI) ─────────────────────────────────────────


def _build_app() -> FastAPI:
    """A throwaway app with one route guarded by a max=2 limiter (scope 'test').

    The guard is attached via the route decorator's ``dependencies=`` list (not a parameter):
    the dependency is a pure side-effecting guard with no value, so it belongs in the route's
    dependency list rather than the signature. This mirrors how the real auth routes will wire
    the limiter (it produces nothing the handler needs)."""
    app = FastAPI()

    @app.get(
        "/guarded",
        dependencies=[Depends(rate_limit(max_hits=2, window_seconds=60.0, scope="test"))],
    )
    def guarded() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_dependency_throttles_third_rapid_request() -> None:
    """The 3rd rapid request to a max=2 route returns 429; the first two return 200."""
    app = _build_app()
    assert get(app, "/guarded")[0] == 200
    assert get(app, "/guarded")[0] == 200
    status_code, body = get(app, "/guarded")
    assert status_code == 429
    assert body == {"detail": "too many requests"}


def test_dependency_scopes_are_independent() -> None:
    """Saturating one scope's route does not throttle a route on a different scope."""
    app = FastAPI()

    @app.get(
        "/a",
        dependencies=[Depends(rate_limit(max_hits=1, window_seconds=60.0, scope="scope-a"))],
    )
    def route_a() -> dict[str, bool]:
        return {"ok": True}

    @app.get(
        "/b",
        dependencies=[Depends(rate_limit(max_hits=1, window_seconds=60.0, scope="scope-b"))],
    )
    def route_b() -> dict[str, bool]:
        return {"ok": True}

    assert get(app, "/a")[0] == 200
    assert get(app, "/a")[0] == 429  # scope-a saturated
    assert get(app, "/b")[0] == 200  # scope-b independent, still allowed
