"""HTTP routes for the turn loop (Slices 1.9, 2.6 → API). Thin handlers only.

CLAUDE.md §7 and ARCHITECTURE.md §14 (invariant 5) require route handlers to carry
*no business logic*: they validate the request (FastAPI + Pydantic do this from the
type annotations), resolve the per-app ``SessionStore`` dependency, delegate to it,
and map a handful of named service errors to HTTP status codes. Nothing here decides
correctness, mastery, or transitions — that is all behind the ``SessionStore`` seam
in ``service.py``.

No SymPy, no LLM, no DB call here (CLAUDE.md §8.1/§8.2, ARCHITECTURE.md §14): those
belong to ``domain/``, ``llm/``, and repositories respectively.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.api.eval_view import build_three_arm_comparison_view
from app.api.schemas import (
    EventBatchRequest,
    EventIngestResponse,
    RouteOptionView,
    StartSessionRequest,
    StartSessionResponse,
    ThreeArmComparisonView,
    TurnRequest,
    TurnResponse,
)
from app.api.service import (
    SessionNotFoundError,
    SessionStore,
    UnknownRouteError,
    routing_menu,
)

# A router rather than decorating the app directly, so the app factory can mount this
# (and future routers) without this module importing the app — the dependency
# direction stays one-way (routes -> service), nothing imports back.
router = APIRouter()


def get_session_store(request: Request) -> SessionStore:
    """Resolve the per-app in-memory ``SessionStore`` (created in ``create_app``).

    One store per app instance (held on ``app.state``) keeps sessions isolated
    between apps — which is what lets each test construct a fresh, empty app.
    """
    store = request.app.state.session_store
    assert isinstance(store, SessionStore)  # set by create_app; guard the contract.
    return store


# The dependency-injected store, as an Annotated alias so the route signatures read
# cleanly and avoid a Depends() call in an argument default (ruff B008).
StoreDep = Annotated[SessionStore, Depends(get_session_store)]


class HealthResponse(BaseModel):
    """Tiny liveness payload returned by ``GET /health``."""

    model_config = ConfigDict(extra="forbid")

    status: str


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness check. No dependencies touched — purely "is the app up?"."""
    return HealthResponse(status="ok")


@router.get("/routing-choices", response_model=list[RouteOptionView], tags=["session"])
def routing_choices() -> list[RouteOptionView]:
    """The Turn-0 cold-start routing menu (decision 0.D.2).

    Returns the three equal-weight KC options plus the single de-emphasized "I'm not
    sure" default. The surface renders these and sends a chosen ``key`` back to
    ``POST /session``. Pure data; no session is created by viewing the menu.
    """
    return routing_menu()


@router.get(
    "/eval/three-arm-comparison",
    response_model=ThreeArmComparisonView,
    tags=["eval"],
)
def three_arm_comparison() -> ThreeArmComparisonView:
    """The Slice 5.3 three-arm comparison for the on-screen dashboard (PROJECT.md §3.11).

    Free and deterministic: the adaptive and static columns are computed live; the chat
    column is the pre-registered prediction until the cost-gated live LLM run. No LLM call
    is made here, so viewing the dashboard never spends money (CLAUDE.md §8.1 spirit).
    """
    return build_three_arm_comparison_view()


@router.post("/session", response_model=StartSessionResponse, tags=["session"])
def start_session(
    request: StartSessionRequest,
    store: StoreDep,
) -> StartSessionResponse:
    """Start a session from a Turn-0 route choice; return its Turn-1 problem (0.D.2).

    Delegates to the store, which derives the route/prior/calibration item
    server-side. An unknown ``route_key`` is a client error → 422 (we do not invent a
    route, CLAUDE.md §8.5).
    """
    try:
        return store.start(request.route_key, proactive_enabled=request.proactive_enabled)
    except UnknownRouteError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unknown route_key: {request.route_key!r}",
        ) from exc


@router.post("/turn", response_model=TurnResponse, tags=["turn"])
def submit_turn(
    request: TurnRequest,
    store: StoreDep,
) -> TurnResponse:
    """Accept one learner action and return the turn-loop result.

    FastAPI validates the body against ``TurnRequest`` first (a malformed body gets a
    422 automatically). The handler then delegates to the store; an unknown
    ``session_id`` → 404 (the deterministic verify/mastery/policy work lives behind
    the seam, ARCHITECTURE.md §10, not here).
    """
    try:
        return store.process_turn(request)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown session_id: {request.session_id!r}",
        ) from exc


@router.post(
    "/events",
    response_model=EventIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["events"],
)
def ingest_events(
    request: EventBatchRequest,
    store: StoreDep,
) -> EventIngestResponse:
    """Record a batch of raw behavioral events — SEPARATE from the turn loop (Slice PL.2).

    The hard invariant (ARCHITECTURE.md §14 invariant 7): "telemetry never blocks a turn —
    event capture happens off the turn loop ... never blocking an endpoint." So this endpoint is
    independent of ``/turn`` — it never calls ``process_turn`` and never touches
    verify/mastery/policy — and it returns HTTP 202 ACCEPTED: the server has *accepted* the batch
    for best-effort persistence off the request path, not confirmed durable storage.

    It is LENIENT, unlike ``/turn``: an UNKNOWN ``session_id`` is NOT a 404 (the store persists
    what it can, or no-ops, and still 202s), and a persistence failure is swallowed inside the
    store so it can never error the client. FastAPI still validates the request shape, so a
    malformed event or an over-long batch is rejected with a 422 before reaching the store.
    """
    accepted = store.ingest_events(request)
    return EventIngestResponse(accepted=accepted)
