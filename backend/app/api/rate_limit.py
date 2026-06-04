"""In-process fixed-window rate limiter for auth routes (Slice S3, OWASP brute-force).

WHY this exists
---------------
The parent/child auth surface (signup / login / child-login) is the classic target for
credential-stuffing and brute-force password guessing. OWASP's Authentication and
Credential-Stuffing cheat sheets both call for *rate limiting on authentication endpoints*
as a first-line control, so an attacker cannot fire thousands of guesses per second against
a single account or from a single source. This module is that app-layer control.

WHY this is "defense in depth", NOT the only layer
--------------------------------------------------
Per CLAUDE.md §10 (AWS deployment) the production fronting is CloudFront -> ALB -> Fargate,
and the *authoritative* rate/abuse backstop is the edge: ALB / AWS WAF rate-based rules, which
see traffic before it reaches a Fargate task and span all tasks. That edge layer is the real
ceiling on volumetric abuse. This in-process limiter is deliberately a SECOND, finer-grained
layer that lives next to the auth logic:

  - It is *per-process* (state is a plain dict in this worker's memory). With N Fargate tasks
    behind the ALB, an attacker effectively gets up to N x the per-process budget. That is
    acceptable BECAUSE the WAF rate rule is the real cap; this layer exists to blunt rapid
    same-process abuse and to give a fast, dependency-free 429 without a round-trip to the edge.
  - It is in-process precisely to honor CLAUDE.md §8.6 (no caching layer / no Redis for a
    6-week build) and §8.7 (no new dependency): a shared store like Redis would be the "correct"
    multi-process answer, but it is out of scope here. If/when a global counter is needed, the
    seam is the same -- swap the per-scope ``RateLimiter`` for a Redis-backed one.

WHY time is injected
--------------------
``RateLimiter.check`` takes ``now: float`` explicitly rather than reading a wall clock inside
the decision. This keeps the limiter PURE and DETERMINISTIC: a test advances ``now`` to roll a
window over and gets the same result every time (CLAUDE.md §9 -- deterministic tests, no clock
flakiness). The FastAPI dependency is the only place a real clock (``time.monotonic()``) is
read, and it reads a *monotonic* clock so that NTP steps or system-clock changes cannot
accidentally widen or collapse a window.

Algorithm: fixed window
------------------------
We use a fixed window (count per ``[window_start, window_start + window_seconds)`` bucket),
not a sliding log, because it is O(1) per check and O(keys) in memory and is plenty for a
defense-in-depth layer. The known fixed-window weakness -- up to 2x ``max_hits`` across a
window boundary -- is irrelevant here: the WAF rate rule, not this counter, sets the true cap.

Usage (a route depends on the factory's callable)
-------------------------------------------------
Each auth route attaches its own scope so login / signup / child-login limit independently.
The limiter is a value-less guard, so the cleanest wiring is the decorator's ``dependencies=``
list (it produces nothing the handler needs)::

    from fastapi import Depends
    from app.api.rate_limit import rate_limit

    @parent_auth_router.post(
        "/login",
        response_model=ParentMeResponse,
        dependencies=[Depends(rate_limit(max_hits=10, window_seconds=60.0, scope="parent-login"))],
    )
    def login(body: ParentLoginRequest, store: StoreDep, response: Response) -> ParentMeResponse:
        ...

(The equivalent ``Annotated[None, Depends(...)]`` parameter form also works, but it must be a
module-level alias -- a function-local ``Annotated`` alias confuses FastAPI's parameter
resolution into treating ``None`` as a required body field. Prefer ``dependencies=``.)

The dependency returns ``None`` (it is a guard, not a value); on overflow it raises
``HTTPException(429, "too many requests")`` BEFORE the handler body runs, so no business logic
executes for a throttled request -- the limiter stays out of the handler (CLAUDE.md §7).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import HTTPException, Request, status


class RateLimiter:
    """A pure, deterministic, in-process fixed-window hit counter keyed by a string.

    Construct with a budget (``max_hits``) and a window length (``window_seconds``). Each call to
    :meth:`check` records one hit against a key and reports whether that hit is within budget for
    the key's current window. Time is supplied by the caller (``now``), so the class never reads a
    clock -- it is a pure function of (constructor args, prior calls, ``now``). State is held in a
    process-local dict; see the module docstring for why per-process is acceptable here.
    """

    def __init__(self, max_hits: int, window_seconds: float) -> None:
        if max_hits < 1:
            raise ValueError("max_hits must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._max_hits = max_hits
        self._window_seconds = window_seconds
        # key -> (window_start, hit_count_in_window). One entry per active key; stale entries are
        # dropped lazily on access so memory stays bounded by the set of *recently* seen keys.
        self._windows: dict[str, tuple[float, int]] = {}

    def check(self, key: str, now: float) -> bool:
        """Record a hit for ``key`` at time ``now``; return True if allowed, False if over budget.

        A hit is "allowed" when, including itself, no more than ``max_hits`` hits fall in the key's
        current ``window_seconds`` window. The first hit of a key (or the first after the window
        has elapsed) opens a fresh window at ``now``. A blocked hit is STILL counted -- sustained
        hammering keeps the window saturated, so an attacker who keeps trying within the window
        does not get a free pass once the window would otherwise have been "full".
        """
        existing = self._windows.get(key)
        if existing is None or now - existing[0] >= self._window_seconds:
            # No live window for this key -> open a new one at ``now`` with this as hit #1.
            self._windows[key] = (now, 1)
            return True

        window_start, count = existing
        new_count = count + 1
        self._windows[key] = (window_start, new_count)
        return new_count <= self._max_hits

    def reset(self) -> None:
        """Forget all per-key window state (used for test isolation)."""
        self._windows.clear()


# ── Per-scope registry + FastAPI dependency factory ──────────────────────────────────────────
#
# Each ``scope`` string gets its own ``RateLimiter`` so unrelated endpoints throttle
# independently: a flood of failed parent logins must not also lock out child logins. The
# registry is keyed by ``scope`` and built lazily on first use of a given scope.

_LIMITERS: dict[str, RateLimiter] = {}


def _limiter_for(scope: str, *, max_hits: int, window_seconds: float) -> RateLimiter:
    """Get (or lazily create) the single ``RateLimiter`` instance for ``scope``.

    The first ``rate_limit(...)`` call for a scope fixes its budget/window; later calls for the
    same scope reuse that instance and ignore divergent args. This is intentional -- a scope is a
    single logical bucket, so its limits must be defined in exactly one place (the route that owns
    the scope). Defining one scope with two different budgets is a programming error, and reusing
    the first-seen instance makes the shared counter the single source of truth rather than
    silently splitting it.
    """
    limiter = _LIMITERS.get(scope)
    if limiter is None:
        limiter = RateLimiter(max_hits=max_hits, window_seconds=window_seconds)
        _LIMITERS[scope] = limiter
    return limiter


def _client_key(request: Request, scope: str) -> str:
    """Derive the limiter key from the requester's IP and the scope.

    ``request.client.host`` is the connecting peer's address. Behind CloudFront/ALB this is the
    load balancer unless ``ProxyHeaders``/``X-Forwarded-For`` handling is configured upstream;
    that is a deployment concern, and the WAF layer keys on the true client IP regardless (module
    docstring). When the ASGI server provides no client (e.g. some test/loopback scopes) we fall
    back to the literal ``"unknown"`` so all unattributable requests share one bucket rather than
    crashing or each getting a private budget.
    """
    host = request.client.host if request.client is not None else "unknown"
    return f"{scope}:{host}"


def rate_limit(*, max_hits: int, window_seconds: float, scope: str) -> Callable[[Request], None]:
    """Build a FastAPI dependency that throttles a route by client IP within ``scope``.

    Returns a callable suitable for ``Depends(...)``. The callable derives the per-IP key for
    ``scope``, charges one hit against the shared per-scope :class:`RateLimiter` using a monotonic
    clock, and raises ``HTTPException(429)`` when the IP is over budget for the current window.
    It returns ``None`` -- it is a guard, not a value provider -- so a route depends on it only
    for the side effect (see the module docstring for the ``Annotated[None, Depends(...)]`` form).

    The clock (``time.monotonic()``) is read HERE, not inside :class:`RateLimiter`, keeping the
    counter pure and unit-testable with explicit ``now`` values.
    """
    limiter = _limiter_for(scope, max_hits=max_hits, window_seconds=window_seconds)

    def _dependency(request: Request) -> None:
        key = _client_key(request, scope)
        if not limiter.check(key, time.monotonic()):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many requests",
            )
        return None

    return _dependency


def reset_all() -> None:
    """Clear every per-scope limiter's window state (for test isolation).

    Tests must start from a clean slate so one test's hits never spill into another's budget.
    We reset each registered ``RateLimiter`` IN PLACE and deliberately KEEP the registry: a
    route's ``Depends(rate_limit(...))`` captures its limiter instance ONCE at import time, so
    that exact instance must stay reachable here to be reset on every call. (Clearing the
    registry would orphan those route-held limiters — the second ``reset_all`` onward would
    iterate an empty registry and never reset them, and hits would accumulate across tests.)
    Each scope is declared with a single budget by its owning route, so there is no need to
    drop-and-rebuild the registry.
    """
    for limiter in _LIMITERS.values():
        limiter.reset()


__all__ = ["RateLimiter", "rate_limit", "reset_all"]
