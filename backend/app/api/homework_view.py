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
)
from app.homework.grading import GradeResult
from app.homework.session import HwRun


class InvalidPageImageError(ValueError):
    """A submitted page image was not valid base64 (the route maps this to a 422)."""


def decode_pages(pages: list[str]) -> list[bytes]:
    """Decode the phone's base64 page images to raw bytes (tolerating a ``data:`` URL prefix).

    The scanner only needs the bytes; the mock ignores them entirely. A malformed image is a
    client error, not a server crash — we raise ``InvalidPageImageError`` so the route can 422.
    """
    out: list[bytes] = []
    for page in pages:
        payload = page.split(",", 1)[1] if page.startswith("data:") else page
        try:
            out.append(base64.b64decode(payload, validate=True))
        except (binascii.Error, ValueError) as exc:
            raise InvalidPageImageError("a page image was not valid base64") from exc
    return out


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
    "decode_pages",
    "status_response",
    "submit_response",
]
