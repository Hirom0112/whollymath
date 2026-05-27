"""Contract tests for the turn-loop API (Slice 1.9).

These test the *contract* — request/response shape and status codes — not
business behavior (CLAUDE.md §9: "Test the CONTRACT, not business behavior";
endpoints are contract-tested, flexibility in implementation is fine). They lock
the shapes ARCHITECTURE.md §10 requires of a turn so that when later slices drop
the real verify/mastery/policy services in behind ``process_turn``, any change to
the wire contract is caught here.

What is deliberately NOT asserted: whether an answer is *actually* correct, what
the *real* next state is, or any mastery value — those are decided by the
domain/mastery/policy layers (later slices), and the route returns a marked stub
today. Asserting them now would be testing business behavior that does not exist.

Driven through a tiny in-process ASGI client (``asgi_client``) because httpx is
not installed and this slice may not add dependencies — see that module's
docstring. The full FastAPI stack (routing, Pydantic validation, status codes) is
still exercised, so these are real HTTP-level contract tests.
"""

from __future__ import annotations

from typing import Any

from app.api.app import create_app
from app.api.schemas import (
    ActionType,
    ErrorType,
    SurfaceState,
    TurnRequest,
    TurnResponse,
)

from tests.api.asgi_client import get, post_json


def _valid_turn_body() -> dict[str, Any]:
    """A minimal, valid TurnRequest payload (the documented happy path, §10)."""
    return {
        "session_id": "sess-123",
        "problem_id": "prob-KC_equivalence-001",
        "action": ActionType.SUBMIT_ANSWER.value,
        "submitted_answer": "2/4",
        "surface_state": SurfaceState.SYMBOLIC_FOCUS.value,
        "latency_ms": 4200,
        "hint_used": False,
    }


# ─── Health endpoint ───


def test_health_returns_200_and_status_ok() -> None:
    """GET /health is a dependency-free liveness check returning {status: ok}."""
    app = create_app()
    status_code, body = get(app, "/health")
    assert status_code == 200
    assert body == {"status": "ok"}


# ─── Turn endpoint: happy path / response shape ───


def test_turn_accepts_valid_request_and_returns_200() -> None:
    """A well-formed TurnRequest is accepted (validation passes, handler runs)."""
    app = create_app()
    status_code, _ = post_json(app, "/turn", _valid_turn_body())
    assert status_code == 200


def test_turn_response_matches_documented_shape() -> None:
    """The response parses back into TurnResponse — the shape is the contract.

    Re-validating the JSON through the Pydantic model is the strongest contract
    assertion: every documented field is present with the right type, and (via
    extra='forbid') no undocumented field leaked in.
    """
    app = create_app()
    status_code, body = post_json(app, "/turn", _valid_turn_body())
    assert status_code == 200

    response = TurnResponse.model_validate(body)
    # Field presence + types, not business values:
    assert isinstance(response.correct, bool)
    assert isinstance(response.error_type, ErrorType)
    assert isinstance(response.next_surface_state, SurfaceState)
    assert isinstance(response.feedback, str) and response.feedback
    assert response.hint is None or isinstance(response.hint, str)
    assert isinstance(response.mastery, list)


def test_turn_response_has_exactly_the_contract_keys() -> None:
    """The response carries precisely the documented top-level keys — no drift."""
    app = create_app()
    _, body = post_json(app, "/turn", _valid_turn_body())
    assert set(body.keys()) == {
        "correct",
        "error_type",
        "next_surface_state",
        "feedback",
        "hint",
        "mastery",
    }


def test_hint_request_action_without_answer_is_valid() -> None:
    """A REQUEST_HINT turn carries no submitted_answer and is still well-formed.

    The contract allows submitted_answer to be omitted (a hint request has no
    answer). The cross-field "answer required iff submit" rule is business logic
    for a later slice, not the wire contract — so this must validate at the API.
    """
    app = create_app()
    body = _valid_turn_body()
    body["action"] = ActionType.REQUEST_HINT.value
    del body["submitted_answer"]
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 200


def test_hint_used_defaults_when_omitted() -> None:
    """hint_used is optional and defaults to False (documented default, §6)."""
    body = _valid_turn_body()
    del body["hint_used"]
    parsed = TurnRequest.model_validate(body)
    assert parsed.hint_used is False


# ─── Turn endpoint: invalid requests are rejected with 422 ───


def test_turn_rejects_missing_required_field_with_422() -> None:
    """Omitting a required field (session_id) is a Pydantic 422, not a 500."""
    app = create_app()
    body = _valid_turn_body()
    del body["session_id"]
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_wrong_type_with_422() -> None:
    """A wrongly-typed field (latency_ms as a string) is rejected with 422."""
    app = create_app()
    body = _valid_turn_body()
    body["latency_ms"] = "not-a-number"
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_unknown_action_enum_with_422() -> None:
    """An action outside the enumerated ActionType set is rejected with 422."""
    app = create_app()
    body = _valid_turn_body()
    body["action"] = "teleport"
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_unknown_surface_state_with_422() -> None:
    """A surface_state outside the five enumerated states is rejected with 422."""
    app = create_app()
    body = _valid_turn_body()
    body["surface_state"] = "S9_holographic"
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_negative_latency_with_422() -> None:
    """latency_ms is constrained >= 0 (it is elapsed time); negatives are 422."""
    app = create_app()
    body = _valid_turn_body()
    body["latency_ms"] = -1
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_extra_unknown_field_with_422() -> None:
    """extra='forbid' means an undocumented field is a contract violation (422)."""
    app = create_app()
    body = _valid_turn_body()
    body["smuggled_field"] = "nope"
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422
