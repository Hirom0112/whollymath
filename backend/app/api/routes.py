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

from app.api.benchmark_transcript_view import (
    build_benchmark_transcript_view,
    list_benchmark_personas,
)
from app.api.eval_view import build_three_arm_comparison_view
from app.api.homework_view import (
    InvalidPageImageError,
    assign_response,
    decode_image,
    decode_pages,
    read_back_response,
    status_response,
    submit_response,
)
from app.api.schemas import (
    BenchmarkPersonaSummaryView,
    BenchmarkTranscriptView,
    EventBatchRequest,
    EventIngestResponse,
    HwAssignRequest,
    HwAssignResponse,
    HwConfirmRequest,
    HwStatusResponse,
    HwSubmitRequest,
    HwSubmitResponse,
    ReadBackView,
    RouteOptionView,
    StartSessionRequest,
    StartSessionResponse,
    ThreeArmComparisonView,
    TranscribeAnswerRequest,
    TurnRequest,
    TurnResponse,
)
from app.api.service import (
    SessionNotFoundError,
    SessionStore,
    UnknownRouteError,
    routing_menu,
)
from app.homework.session import HomeworkStore

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


def get_homework_store(request: Request) -> HomeworkStore:
    """Resolve the per-app in-memory ``HomeworkStore`` (created in ``create_app``).

    Same one-store-per-app discipline as the turn-loop store, so homework runs are isolated
    between app instances (a fresh, empty store per test app).
    """
    store = request.app.state.homework_store
    assert isinstance(store, HomeworkStore)  # set by create_app; guard the contract.
    return store


HwStoreDep = Annotated[HomeworkStore, Depends(get_homework_store)]


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


@router.get(
    "/eval/benchmark-personas",
    response_model=list[BenchmarkPersonaSummaryView],
    tags=["eval"],
)
def benchmark_personas() -> list[BenchmarkPersonaSummaryView]:
    """The five adversarial personas for the benchmark-theater switcher (PROJECT.md §4.2).

    Pure data, deterministic, free: just who each learner is and the mastery dimension they
    attack. No session is created and no LLM is called.
    """
    return list_benchmark_personas()


@router.get(
    "/eval/benchmark-transcript/{persona_id}",
    response_model=BenchmarkTranscriptView,
    tags=["eval"],
)
def benchmark_transcript(persona_id: str) -> BenchmarkTranscriptView:
    """One persona's run through all three arms, turn by turn (a teaching view of Slice 5.3).

    Deterministic and free — the adaptive + static arms are pure and the chat arm uses a
    canned illustrative provider (no live LLM call, CLAUDE.md §8.1). An unknown ``persona_id``
    is a 404 (we do not invent a persona, CLAUDE.md §8.5).
    """
    view = build_benchmark_transcript_view(persona_id)
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown persona_id: {persona_id!r}",
        )
    return view


@router.post("/hw/assign", response_model=HwAssignResponse, tags=["homework"])
def hw_assign(request: HwAssignRequest, store: HwStoreDep) -> HwAssignResponse:
    """Start a homework run for a skill at lesson end (PROJECT.md §3.4 two-star model).

    Returns the upload ``token`` (the desktop encodes it in the QR) plus the question list for the
    checklist. Pure setup — no scan, no grade yet.
    """
    run = store.assign(request.kc)
    return assign_response(run)


@router.post("/hw/submit", response_model=HwSubmitResponse, tags=["homework"])
def hw_submit(request: HwSubmitRequest, store: HwStoreDep) -> HwSubmitResponse:
    """Receive the phone's page photos for a run and transcribe a draft (state → ready_for_review).

    Images arrive base64-encoded (no multipart dependency). Grading does NOT happen here — the
    learner confirms the transcription first (``/hw/confirm``). Unknown token → 404; a malformed
    image → 422.
    """
    try:
        pages = decode_pages(request.pages)
    except InvalidPageImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    run = store.submit(request.token, pages)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown token: {request.token!r}"
        )
    return submit_response(run)


@router.get("/hw/status", response_model=HwStatusResponse, tags=["homework"])
def hw_status(token: str, store: HwStoreDep) -> HwStatusResponse:
    """Poll a run (the desktop, while it waits for the phone): state + draft + the graded verdict.

    The draft is present once photos are in (for the read-back); the result once confirmed. Unknown
    token → 404.
    """
    run = store.get(token)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown token: {token!r}"
        )
    return status_response(run)


@router.post("/hw/confirm", response_model=HwStatusResponse, tags=["homework"])
def hw_confirm(request: HwConfirmRequest, store: HwStoreDep) -> HwStatusResponse:
    """Grade the learner-confirmed answers (after the desktop read-back) and return the verdict.

    ``answers`` is authoritative — what the learner confirmed/corrected, not necessarily the raw
    draft. SymPy decides correctness; the ★★ verdict is in the returned result. Unknown token → 404.
    """
    answers = {a.index: a.answer for a in request.answers}
    run = store.confirm(request.token, answers)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown token: {request.token!r}"
        )
    return status_response(run)


@router.post("/transcribe-answer", response_model=ReadBackView, tags=["homework"])
def transcribe_answer(request: TranscribeAnswerRequest, store: HwStoreDep) -> ReadBackView:
    """Read back one snapped handwritten answer for confirmation (the multimodal beat, HR.C1/C3).

    Mid-lesson, a child photographs the answer they are working on instead of typing it. The image
    (base64, like ``/hw/submit``) is transcribed by the injected scanner and normalized into a
    submittable string the surface shows back — "I read this as 3/4 — right?" — BEFORE grading. On
    confirm, that string is submitted through the normal ``/turn`` (the SAME SymPy verifier as a
    typed answer, CLAUDE.md §8.2). Best-effort and fail-safe: an unreadable image returns
    ``readable=false`` (the surface asks for a rewrite), never a silent misread. Malformed → 422.
    """
    try:
        image = decode_image(request.image)
    except InvalidPageImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return read_back_response(store.scanner, image)


@router.post("/session", response_model=StartSessionResponse, tags=["session"])
def start_session(
    request: StartSessionRequest,
    store: StoreDep,
) -> StartSessionResponse:
    """Start a session — from a Turn-0 route choice (0.D.2) or a course-map skill (§3.13).

    Exactly one of ``kc`` / ``route_key`` must be given. A ``kc`` starts that skill's lesson
    directly (course map); a ``route_key`` takes the cold-start path. Both derive the
    prior/first problem server-side. Neither-or-both given, or an unknown ``route_key``, is a
    client error → 422 (we do not invent a route, CLAUDE.md §8.5).
    """
    if (request.kc is None) == (request.route_key is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="provide exactly one of 'kc' or 'route_key'",
        )
    if request.kc is not None:
        return store.start_kc(request.kc, proactive_enabled=request.proactive_enabled)
    assert request.route_key is not None  # narrowed by the exactly-one check above
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
    # Off-the-turn-loop, additive-only: a proactive nudge if the live stream shows the learner is
    # stuck on the IN-PROGRESS problem (live loop Beat 1). null in the default/observe-only arm.
    return EventIngestResponse(accepted=accepted, nudge=store.mid_problem_nudge(request))
