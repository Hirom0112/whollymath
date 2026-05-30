"""Contract tests for the homework scan flow endpoints (PROJECT.md §3.4 two-star model).

CLAUDE.md §9: HTTP-level contract tests for the cross-device flow — assign (QR token) → submit
(phone pages) → status (the read-back draft) → confirm (SymPy grades the confirmed answers → the
★★ verdict). Plus the error contract (unknown token → 404, bad image → 422). The homework engine
(assignment/grading/scanner) has its own suite under tests/homework/; here we assert the API wires
it end to end, free and deterministic (MockScanner — no OCR key, no LLM).
"""

from __future__ import annotations

import base64

from app.api.app import create_app
from app.api.schemas import HwAssignResponse, HwStatusResponse, HwSubmitResponse
from app.homework.scanner import MockScanner
from app.homework.session import HomeworkStore
from fastapi import FastAPI

from tests.api.asgi_client import get, post_json

_ADD = "KC_addition_unlike"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _app() -> FastAPI:
    """A fresh app with the deterministic MockScanner forced — so the contract is exercised the
    same way whether or not a real MATHPIX_APP_KEY is present in the local .env."""
    app = create_app()
    app.state.homework_store = HomeworkStore(scanner=MockScanner())
    return app


def test_full_flow_assign_submit_review_confirm_passes() -> None:
    """The happy path: a clean sheet (mock reads the answer key) → ★★ at target score 1.0."""
    app = _app()

    status_code, body = post_json(app, "/hw/assign", {"kc": _ADD})
    assert status_code == 200, body
    assigned = HwAssignResponse.model_validate(body)
    assert assigned.token
    assert assigned.target_kc == _ADD
    assert len(assigned.questions) == 7  # 5 target + 2 spaced review
    assert assigned.questions[0].is_target is True

    # Phone uploads two pages (bytes ignored by the mock; this proves multi-page + base64 decode).
    status_code, body = post_json(
        app, "/hw/submit", {"token": assigned.token, "pages": [_b64(b"page1"), _b64(b"page2")]}
    )
    assert status_code == 200, body
    assert HwSubmitResponse.model_validate(body).state == "ready_for_review"

    # Desktop polls → the read-back draft (what the scanner read, per question).
    status_code, body = get(app, f"/hw/status?token={assigned.token}")
    assert status_code == 200, body
    status = HwStatusResponse.model_validate(body)
    assert status.state == "ready_for_review"
    assert len(status.draft) == 7
    assert all(d.read_as is not None for d in status.draft)  # mock reads every blank

    # Learner confirms the draft as-is → grade.
    answers = [{"index": d.index, "answer": d.read_as} for d in status.draft]
    status_code, body = post_json(app, "/hw/confirm", {"token": assigned.token, "answers": answers})
    assert status_code == 200, body
    graded = HwStatusResponse.model_validate(body)
    assert graded.state == "graded"
    assert graded.result is not None
    assert graded.result.target_total == 5
    assert graded.result.passed is True
    assert graded.result.target_score == 1.0


def test_confirm_with_a_corrected_wrong_answer_can_fail_the_gate() -> None:
    """The read-back is authoritative: if the confirmed target answers fall below 0.8, no ★★ —
    proving grading runs on the CONFIRMED answers, not the raw draft."""
    app = _app()
    _, body = post_json(app, "/hw/assign", {"kc": _ADD})
    token = HwAssignResponse.model_validate(body).token
    post_json(app, "/hw/submit", {"token": token, "pages": [_b64(b"p")]})
    _, body = get(app, f"/hw/status?token={token}")
    draft = HwStatusResponse.model_validate(body).draft

    # Blank out three of the five target answers in the confirmation → 2/5 = 0.4 < 0.8.
    answers: list[dict[str, object]] = []
    targets_blanked = 0
    for d in draft:
        if d.is_target and targets_blanked < 3:
            answers.append({"index": d.index, "answer": None})
            targets_blanked += 1
        else:
            answers.append({"index": d.index, "answer": d.read_as})

    _, body = post_json(app, "/hw/confirm", {"token": token, "answers": answers})
    graded = HwStatusResponse.model_validate(body)
    assert graded.result is not None
    assert graded.result.passed is False


def test_unknown_token_is_404() -> None:
    app = _app()
    code_status, _ = get(app, "/hw/status?token=nope")
    assert code_status == 404
    code_submit, _ = post_json(app, "/hw/submit", {"token": "nope", "pages": [_b64(b"x")]})
    assert code_submit == 404
    code_confirm, _ = post_json(app, "/hw/confirm", {"token": "nope", "answers": []})
    assert code_confirm == 404


def test_malformed_page_image_is_422() -> None:
    app = _app()
    _, body = post_json(app, "/hw/assign", {"kc": _ADD})
    token = HwAssignResponse.model_validate(body).token
    code, _ = post_json(app, "/hw/submit", {"token": token, "pages": ["!!!not base64!!!"]})
    assert code == 422
