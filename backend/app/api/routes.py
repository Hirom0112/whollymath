"""HTTP routes for the turn loop (Slice 1.9). Thin handlers only.

CLAUDE.md §7 and ARCHITECTURE.md §14 (invariant 5) require that route handlers
contain *no business logic*: they validate the request (FastAPI + Pydantic do
this automatically from the type annotations) and delegate to a service. Here the
service is the turn-loop seam in ``service.py``. Nothing in this file decides
correctness, mastery, or transitions — it wires the validated ``TurnRequest`` to
``process_turn`` and returns its ``TurnResponse``.

No SymPy, no LLM, no DB call here (CLAUDE.md §8.1/§8.2, ARCHITECTURE.md §14):
those belong to ``domain/``, ``llm/``, and repositories respectively.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.schemas import TurnRequest, TurnResponse
from app.api.service import process_turn

# A router rather than decorating the app directly, so the app factory can mount
# this (and future routers) without this module importing the app — keeps the
# dependency direction one-way (routes -> service), nothing imports back.
router = APIRouter()


class HealthResponse(BaseModel):
    """Tiny liveness payload returned by ``GET /health``."""

    model_config = ConfigDict(extra="forbid")

    status: str


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness check. No dependencies touched — purely "is the app up?"."""
    return HealthResponse(status="ok")


@router.post("/turn", response_model=TurnResponse, tags=["turn"])
def submit_turn(request: TurnRequest) -> TurnResponse:
    """Accept one learner action and return the turn-loop result.

    FastAPI validates the body against ``TurnRequest`` before this runs; a
    malformed body never reaches the handler (it gets a 422 automatically). The
    handler then does the one thing a thin route does: delegate to the service
    seam and return its result. The deterministic verify/mastery/policy work
    lives behind ``process_turn`` (ARCHITECTURE.md §10), not here.
    """
    return process_turn(request)
