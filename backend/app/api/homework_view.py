"""View assembly for the homework scan flow (PROJECT.md §3.4 two-star model).

Maps the homework domain objects (``app.homework``) to the wire schemas the surface renders, and
decodes the phone's base64 page images to bytes for the scanner. Presentation seam only — no
grading/scan logic here (that is the homework package's job; CLAUDE.md §7). No SymPy, no LLM.
"""

from __future__ import annotations

import base64
import binascii

from app.api.schemas import (
    HwAssignResponse,
    HwDraftItemView,
    HwGradeResultView,
    HwQuestionResultView,
    HwQuestionView,
    HwStatusResponse,
    HwSubmitResponse,
    ReadBackView,
)
from app.homework.grading import GradeResult
from app.homework.scanner import HomeworkScanner
from app.homework.session import HwRun
from app.tutor.transcribed_answer import read_back_answer


class InvalidPageImageError(ValueError):
    """A submitted page image was not valid base64 (the route maps this to a 422)."""


def decode_image(image: str) -> bytes:
    """Decode one base64 image to raw bytes (tolerating a ``data:`` URL prefix).

    A malformed image is a client error, not a server crash — we raise ``InvalidPageImageError`` so
    the route can 422. Shared by the homework page upload and the single-answer camera beat.
    """
    payload = image.split(",", 1)[1] if image.startswith("data:") else image
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidPageImageError("a page image was not valid base64") from exc


def decode_pages(pages: list[str]) -> list[bytes]:
    """Decode the phone's base64 page images to raw bytes (tolerating a ``data:`` URL prefix).

    The scanner only needs the bytes; the mock ignores them entirely. A malformed image raises
    ``InvalidPageImageError`` (per ``decode_image``) so the route can 422.
    """
    return [decode_image(page) for page in pages]


def read_back_response(scanner: HomeworkScanner, image: bytes) -> ReadBackView:
    """Transcribe one snapped answer image and normalize it into a read-back (Slice HR.C1/C3).

    The scanner reads the image to text; ``read_back_answer`` flattens it to a submittable string
    (the SAME one the typed path produces). ``readable`` is false when nothing could be read, so the
    surface asks the learner to rewrite rather than grade a misread — SymPy still owns correctness
    on the eventual confirm (CLAUDE.md §8.2). No LLM (§8.1).
    """
    answer = read_back_answer(scanner.transcribe(image))
    return ReadBackView(transcribed_answer=answer, readable=answer is not None)


def assign_response(run: HwRun) -> HwAssignResponse:
    return HwAssignResponse(
        token=run.token,
        target_kc=run.assignment.target_kc.value,
        questions=[
            HwQuestionView(index=i, statement=p.problem.statement, is_target=p.is_target)
            for i, p in enumerate(run.assignment.problems)
        ],
    )


def submit_response(run: HwRun) -> HwSubmitResponse:
    return HwSubmitResponse(state=run.state, question_count=len(run.assignment.problems))


def _grade_result_view(result: GradeResult) -> HwGradeResultView:
    return HwGradeResultView(
        results=[
            HwQuestionResultView(
                index=q.index,
                statement=q.statement,
                is_target=q.is_target,
                submitted=q.submitted,
                correct=q.correct,
                unreadable=q.unreadable,
            )
            for q in result.results
        ],
        target_correct=result.target_correct,
        target_total=result.target_total,
        target_score=result.target_score,
        passed=result.passed,
    )


def status_response(run: HwRun) -> HwStatusResponse:
    """The desktop's poll view: state + the draft (for the read-back) + the verdict once graded."""
    draft: list[HwDraftItemView] = []
    if run.draft is not None:
        for i, p in enumerate(run.assignment.problems):
            draft.append(
                HwDraftItemView(
                    index=i,
                    statement=p.problem.statement,
                    is_target=p.is_target,
                    read_as=run.draft.get(i),
                )
            )
    result = _grade_result_view(run.result) if run.result is not None else None
    return HwStatusResponse(state=run.state, draft=draft, result=result)


__all__ = [
    "InvalidPageImageError",
    "assign_response",
    "decode_image",
    "decode_pages",
    "read_back_response",
    "status_response",
    "submit_response",
]
