"""Contract tests for ``POST /transcribe-answer`` — the live multimodal beat (Slice HR.C1/C3).

CLAUDE.md §9: HTTP-level contract for the mid-lesson camera path. A child snaps their handwritten
answer; the scanner transcribes the single image; ``read_back_answer`` normalizes it; the surface
shows "I read this as 3/4 — right?" BEFORE grading. On confirm, that string flows through the SAME
turn/verify a typed answer does (CLAUDE.md §8.2). Deterministic + free here (MockScanner echoes the
image bytes — no OCR key, no LLM), so a test scripts the exact 'handwriting' as the image bytes.
"""

from __future__ import annotations

import base64

from app.api.app import create_app
from app.api.schemas import ReadBackView
from app.homework.scanner import MockScanner
from app.homework.session import HomeworkStore
from fastapi import FastAPI

from tests.api.asgi_client import post_json


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _app() -> FastAPI:
    """A fresh app with the deterministic MockScanner forced (so the contract holds with or without
    a local MATHPIX_APP_KEY) — the mock echoes the image bytes back as the transcription."""
    app = create_app()
    app.state.homework_store = HomeworkStore(scanner=MockScanner())
    return app


def test_transcribes_a_handwritten_fraction_into_a_readable_answer() -> None:
    """A snapped ``\\frac{3}{4}`` is read back as the submittable ``3/4`` — LaTeX flattened, the
    same string the typed path submits."""
    app = _app()
    code, body = post_json(app, "/transcribe-answer", {"image": _b64(b"\\frac{3}{4}")})
    assert code == 200, body
    view = ReadBackView.model_validate(body)
    assert view.readable is True
    assert view.transcribed_answer == "3/4"


def test_a_plain_fraction_passes_through_unchanged() -> None:
    app = _app()
    code, body = post_json(app, "/transcribe-answer", {"image": _b64(b"= 3 / 5")})
    assert code == 200, body
    view = ReadBackView.model_validate(body)
    assert view.readable is True
    assert view.transcribed_answer == "3/5"


def test_unreadable_image_is_not_graded_but_asks_for_a_rewrite() -> None:
    """No answer-looking token → readable=false, transcribed_answer=null — the safety net against a
    silent misread (the surface asks the learner to write it again)."""
    app = _app()
    code, body = post_json(app, "/transcribe-answer", {"image": _b64(b"oops no math here")})
    assert code == 200, body
    view = ReadBackView.model_validate(body)
    assert view.readable is False
    assert view.transcribed_answer is None


def test_malformed_image_is_422() -> None:
    app = _app()
    code, _ = post_json(app, "/transcribe-answer", {"image": "!!!not base64!!!"})
    assert code == 422
