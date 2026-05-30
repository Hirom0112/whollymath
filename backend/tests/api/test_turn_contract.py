"""Contract tests for the turn-loop API (Slices 1.9, 2.6 → API).

These test the *contract* — request/response shape and status codes — plus the few
end-to-end behaviors the wired loop now actually guarantees (a session can be
started; a submitted answer comes back with a verdict and the next problem). They do
NOT re-test the domain/mastery/policy internals — those have their own exhaustive
suites; here we assert the API faithfully exposes them (CLAUDE.md §9: endpoints are
contract-tested).

Driven through a tiny in-process ASGI client (``asgi_client``) because httpx is not
installed and this project's API slice may not add dependencies — see that module's
docstring. The full FastAPI stack (routing, Pydantic validation, status codes,
dependency injection) is still exercised, so these are real HTTP-level tests.
"""

from __future__ import annotations

from typing import Any

from app.api.app import create_app
from app.api.schemas import (
    ActionType,
    ErrorType,
    ProblemView,
    RouteOptionView,
    StartSessionResponse,
    SurfaceState,
    TurnRequest,
    TurnResponse,
)

from tests.api.asgi_client import get, post_json

# The addition route's locked Turn-1 calibration item is "1/3 + 1/4 = ?" with the
# SymPy-correct answer 7/12 (tutor.session._addition_calibration). We use that route
# in the happy-path tests because it has a clean numeric answer the verifier judges.
_ADDITION_ROUTE_KEY = "combine"
_ADDITION_CORRECT_ANSWER = "7/12"


def _start_session(app: Any, route_key: str = _ADDITION_ROUTE_KEY) -> StartSessionResponse:
    """Start a session and return its parsed response (session_id + first problem)."""
    status_code, body = post_json(app, "/session", {"route_key": route_key})
    assert status_code == 200, body
    return StartSessionResponse.model_validate(body)


def _turn_body(
    session_id: str, problem_id: str, answer: str = _ADDITION_CORRECT_ANSWER
) -> dict[str, Any]:
    """A valid SUBMIT_ANSWER payload for a started session (the happy path, §10)."""
    return {
        "session_id": session_id,
        "problem_id": problem_id,
        "action": ActionType.SUBMIT_ANSWER.value,
        "submitted_answer": answer,
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


# ─── Routing menu (Turn-0, decision 0.D.2) ───


def test_routing_choices_returns_the_cold_start_menu() -> None:
    """GET /routing-choices returns the 0.D.2 menu: 3 KC options + 1 unsure default."""
    app = create_app()
    status_code, body = get(app, "/routing-choices")
    assert status_code == 200
    options = [RouteOptionView.model_validate(o) for o in body]
    # Three equal-weight options plus exactly one de-emphasized "I'm not sure" default.
    assert len(options) == 4
    assert sum(1 for o in options if o.is_unsure_default) == 1
    assert all(o.key and o.prompt for o in options)


# ─── Session start (Turn-1 calibration) ───


def test_start_session_returns_session_id_and_first_problem() -> None:
    """POST /session starts a session in S1 and hands back the Turn-1 problem (0.D.2)."""
    app = create_app()
    started = _start_session(app)
    assert started.session_id
    assert started.surface_state is SurfaceState.SYMBOLIC_FOCUS
    assert isinstance(started.problem, ProblemView)
    assert started.problem.problem_id and started.problem.statement


def test_equivalence_route_serves_a_yes_no_problem_answered_correctly() -> None:
    """The equivalence cold-start probe ('Is 2/3 the same amount as 4/6?') is a YES/NO
    item end-to-end: the wire carries answer_kind=yes_no so the surface renders buttons,
    and submitting 'yes' verifies correct (2/3 == 4/6). This is the coherence fix — a
    yes/no question no longer lands on a fraction input."""
    app = create_app()
    started = _start_session(app, route_key="same_amount")
    problem = started.problem
    assert problem.answer_kind.value == "yes_no"
    assert "same amount" in problem.statement

    status_code, body = post_json(
        app,
        "/turn",
        {**_turn_body(started.session_id, problem.problem_id, answer="yes")},
    )
    assert status_code == 200, body
    assert body["correct"] is True


def test_numeric_problems_still_default_to_numeric_answer_kind() -> None:
    """The addition calibration item is unchanged: answer_kind defaults to numeric."""
    app = create_app()
    started = _start_session(app)  # the addition route
    assert started.problem.answer_kind.value == "numeric"


def test_generated_equivalence_item_carries_a_locked_denominator() -> None:
    """After the yes/no cold-start probe, the equivalence route serves a generated
    fill-the-top item: it carries given_denominator so the surface locks the bottom box
    and the learner enters only the numerator (the coherence fix for that item)."""
    app = create_app()
    started = _start_session(app, route_key="same_amount")
    status_code, body = post_json(
        app, "/turn", _turn_body(started.session_id, started.problem.problem_id, answer="yes")
    )
    assert status_code == 200, body
    next_problem = ProblemView.model_validate(body["next_problem"])
    assert next_problem.kc.value == "KC_equivalence"
    assert next_problem.answer_kind.value == "numeric"
    assert next_problem.given_denominator is not None and next_problem.given_denominator >= 1
    assert f"?/{next_problem.given_denominator}" in next_problem.statement


def test_start_session_rejects_unknown_route_key_with_422() -> None:
    """A route_key outside the locked menu is a client error → 422 (no invented route)."""
    app = create_app()
    status_code, _ = post_json(app, "/session", {"route_key": "teleport"})
    assert status_code == 422


# ─── Start a lesson directly for a KC (course-map node launch, Slice CP.A.2 / §3.13) ───


def test_start_session_by_kc_launches_that_skill() -> None:
    """POST /session with a kc starts a lesson whose first problem is for that KC.

    The course map launches any node this way — including KCs that are NOT Turn-0 routes
    (subtraction, common denominator), which have no cold-start calibration item.
    """
    app = create_app()
    for kc in ("KC_subtraction_unlike", "KC_common_denominator", "KC_number_line_placement"):
        status_code, body = post_json(app, "/session", {"kc": kc})
        assert status_code == 200, body
        started = StartSessionResponse.model_validate(body)
        assert started.problem.kc.value == kc
        assert started.problem.problem_id and started.problem.statement


def test_start_session_requires_exactly_one_of_kc_or_route_key() -> None:
    """Neither kc nor route_key → 422; both at once → 422 (exactly one entry point)."""
    app = create_app()
    neither, _ = post_json(app, "/session", {})
    assert neither == 422
    both, _ = post_json(
        app, "/session", {"kc": "KC_common_denominator", "route_key": _ADDITION_ROUTE_KEY}
    )
    assert both == 422


def test_start_session_by_kc_rejects_unknown_kc_with_422() -> None:
    """A kc outside the catalog is a client error → 422 (Pydantic enum validation)."""
    app = create_app()
    status_code, _ = post_json(app, "/session", {"kc": "KC_teleportation"})
    assert status_code == 422


# ─── Turn endpoint: happy path / response shape ───


def test_turn_accepts_valid_request_and_returns_200() -> None:
    """A well-formed turn against a live session is accepted and runs the loop."""
    app = create_app()
    started = _start_session(app)
    status_code, _ = post_json(
        app, "/turn", _turn_body(started.session_id, started.problem.problem_id)
    )
    assert status_code == 200


def test_turn_response_matches_documented_shape() -> None:
    """The response parses back into TurnResponse — the shape is the contract."""
    app = create_app()
    started = _start_session(app)
    status_code, body = post_json(
        app, "/turn", _turn_body(started.session_id, started.problem.problem_id)
    )
    assert status_code == 200

    response = TurnResponse.model_validate(body)
    assert isinstance(response.correct, bool)
    assert isinstance(response.error_type, ErrorType)
    assert isinstance(response.next_surface_state, SurfaceState)
    assert isinstance(response.feedback, str) and response.feedback
    assert response.hint is None or isinstance(response.hint, str)
    assert isinstance(response.mastery, list)
    assert response.next_problem is None or isinstance(response.next_problem, ProblemView)


def test_turn_response_has_exactly_the_contract_keys() -> None:
    """The response carries precisely the documented top-level keys — no drift."""
    app = create_app()
    started = _start_session(app)
    _, body = post_json(app, "/turn", _turn_body(started.session_id, started.problem.problem_id))
    assert set(body.keys()) == {
        "correct",
        "error_type",
        "next_surface_state",
        "feedback",
        "hint",
        "mastery",
        "help_need",
        "intervention",
        "next_problem",
        "worked_example",
        "lesson_complete",
    }


def test_correct_answer_is_verified_and_serves_a_next_problem() -> None:
    """The real loop verifies a correct answer and hands back the next problem.

    7/12 is the SymPy-correct answer to the addition calibration (1/3 + 1/4). This
    is the end-to-end proof the API exposes the domain verifier's verdict and keeps
    the journey going (it is not re-testing the verifier — that has its own suite).
    """
    app = create_app()
    started = _start_session(app)
    _, body = post_json(app, "/turn", _turn_body(started.session_id, started.problem.problem_id))
    response = TurnResponse.model_validate(body)
    assert response.correct is True
    assert response.error_type is ErrorType.NONE
    assert response.next_problem is not None
    # The next problem is a different problem than the calibration item just answered.
    assert response.next_problem.problem_id != started.problem.problem_id


def test_wrong_answer_reports_incorrect_with_a_label() -> None:
    """A wrong answer comes back not-correct with non-empty labeled feedback (§7)."""
    app = create_app()
    started = _start_session(app)
    body = _turn_body(started.session_id, started.problem.problem_id, answer="2/7")
    _, payload = post_json(app, "/turn", body)
    response = TurnResponse.model_validate(payload)
    assert response.correct is False
    assert response.feedback


def test_hint_request_returns_a_nudge_without_advancing() -> None:
    """A REQUEST_HINT turn returns a nudge, no state change, same problem (refuse-rule 3)."""
    app = create_app()
    started = _start_session(app)
    body = _turn_body(started.session_id, started.problem.problem_id)
    body["action"] = ActionType.REQUEST_HINT.value
    del body["submitted_answer"]
    status_code, payload = post_json(app, "/turn", body)
    assert status_code == 200
    response = TurnResponse.model_validate(payload)
    assert response.hint
    # Hint does not advance: the learner stays on the same problem.
    assert response.next_problem is not None
    assert response.next_problem.problem_id == started.problem.problem_id


def test_turn_on_unknown_session_returns_404() -> None:
    """A turn naming a session the store never issued is a 404 (not a 500)."""
    app = create_app()
    status_code, _ = post_json(app, "/turn", _turn_body("never-started", "prob-x"))
    assert status_code == 404


def test_hint_used_defaults_when_omitted() -> None:
    """hint_used is optional and defaults to False (documented default, §6)."""
    body = _turn_body("s", "p")
    del body["hint_used"]
    parsed = TurnRequest.model_validate(body)
    assert parsed.hint_used is False


# ─── Turn endpoint: invalid requests are rejected with 422 (before the store is hit) ───


def test_turn_rejects_missing_required_field_with_422() -> None:
    """Omitting a required field (session_id) is a Pydantic 422, not a 500."""
    app = create_app()
    body = _turn_body("s", "p")
    del body["session_id"]
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_wrong_type_with_422() -> None:
    """A wrongly-typed field (latency_ms as a string) is rejected with 422."""
    app = create_app()
    body = _turn_body("s", "p")
    body["latency_ms"] = "not-a-number"
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_unknown_action_enum_with_422() -> None:
    """An action outside the enumerated ActionType set is rejected with 422."""
    app = create_app()
    body = _turn_body("s", "p")
    body["action"] = "teleport"
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_unknown_surface_state_with_422() -> None:
    """A surface_state outside the five enumerated states is rejected with 422."""
    app = create_app()
    body = _turn_body("s", "p")
    body["surface_state"] = "S9_holographic"
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_negative_latency_with_422() -> None:
    """latency_ms is constrained >= 0 (it is elapsed time); negatives are 422."""
    app = create_app()
    body = _turn_body("s", "p")
    body["latency_ms"] = -1
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422


def test_turn_rejects_extra_unknown_field_with_422() -> None:
    """extra='forbid' means an undocumented field is a contract violation (422)."""
    app = create_app()
    body = _turn_body("s", "p")
    body["smuggled_field"] = "nope"
    status_code, _ = post_json(app, "/turn", body)
    assert status_code == 422
