"""Read the answers off a homework photo — a swappable scanner behind one interface.

The scanner's ONLY job is transcription: photo → ``{question_index: answer_string | None}``. It
never decides correctness — SymPy does that in ``grading.py`` (CLAUDE.md §8.2). That split is what
lets a vision/OCR model live here safely: even if it back a future scanner, it only reads what the
child wrote; the verifier still judges it, and the 1-on-1 review catches a misread.

Two implementations:
  - ``MockScanner`` — no OCR at all; returns answers computed from the assignment's own answer key
    (optionally injecting wrong/unreadable items so a demo can show a pass, a fail, and the
    OCR-misread fix). This is the deterministic path used in tests and when no key is configured.
  - ``MathpixScanner`` — real handwritten-math OCR via Mathpix (best-in-class for fractions). Active
    when ``MATHPIX_APP_KEY`` is set. Transcription is BEST-EFFORT and degrades gracefully: anything
    it can't confidently read (or any API failure) becomes ``None``, so the desktop read-back turns
    into manual entry. OCR quality is therefore never blocking — the read-back is the safety net.

``HomeworkScanner`` is a ``Protocol`` so any object with a matching ``scan`` is a scanner — the
same swap-seam pattern as the LLM provider; the API picks the implementation, the flow is identical.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Protocol

from app.homework.assignment import Assignment

# Mathpix text endpoint (handwritten + printed math → text/LaTeX). See class docstring.
_MATHPIX_TEXT_URL = "https://api.mathpix.com/v3/text"
_MATHPIX_TIMEOUT_S = 30
# An answer token: an optional sign, then a fraction ``a/b`` or a bare integer.
_ANSWER_TOKEN = re.compile(r"-?\d+\s*/\s*\d+|-?\d+")


class HomeworkScanner(Protocol):
    """Reads homework page photos into ``{question_index: answer | None}`` (None = unreadable).

    Takes a SEQUENCE of page images — a homework set can span several sheets, and the mobile capture
    screen lets the learner snap every page before tapping "All done" — and returns one answer per
    question across all pages. Transcription only — never correctness (that is the SymPy verifier's
    job, ``grading.py``). The index space is the position of each item in ``assignment.problems``
    (0-based), the order grading expects. The reading it returns is a DRAFT: the desktop shows it
    back to the learner to confirm/correct ("I read this as 1/4 — right?") BEFORE it is graded, so a
    scanner reports ``None`` for anything it cannot read rather than guessing.
    """

    def scan(self, images: Sequence[bytes], assignment: Assignment) -> dict[int, str | None]: ...

    def transcribe(self, image: bytes) -> str:
        """Read ONE snapped answer image to recognized text — the live mid-lesson camera beat.

        Unlike ``scan`` (a whole homework set, indexed by question), this is a single image with no
        assignment context: a child photographs the one answer they are working on. Returns the raw
        transcription (LaTeX/plain), which ``read_back_answer`` then normalizes to a submittable
        string; ``""`` when nothing could be read, so the read-back asks for a rewrite rather than
        grading a misread (CLAUDE.md §8.2). Transcription only — SymPy still grades the confirm.
        """
        ...


def _correct_answer_text(correct_value: object) -> str:
    """Render an item's expected answer the way a learner would write it (e.g. '41/60', '6')."""
    # correct_value is a SymPy Rational; p/q, or a bare integer when whole.
    p = getattr(correct_value, "p", None)
    q = getattr(correct_value, "q", None)
    if p is not None and q is not None:
        return str(p) if q == 1 else f"{p}/{q}"
    return str(correct_value)


class MockScanner:
    """A no-OCR scanner for development and demos: returns the assignment's correct answers,
    with optional injected misses / unreadable items so the whole flow (pass, fail, misread-fix)
    can be shown without a real photo or an OCR key.

    Determinism: same ``(assignment, config)`` → same reading every call. ``overrides`` (index →
    literal answer or ``None``) wins over everything, so a demo can script any specific reading.
    """

    def __init__(
        self,
        *,
        miss_indices: frozenset[int] = frozenset(),
        unreadable_indices: frozenset[int] = frozenset(),
        overrides: Mapping[int, str | None] | None = None,
    ) -> None:
        self._miss = miss_indices
        self._unreadable = unreadable_indices
        self._overrides = dict(overrides) if overrides is not None else {}

    def scan(self, images: Sequence[bytes], assignment: Assignment) -> dict[int, str | None]:
        reading: dict[int, str | None] = {}
        for index, item in enumerate(assignment.problems):
            if index in self._overrides:
                reading[index] = self._overrides[index]
            elif index in self._unreadable:
                reading[index] = None
            elif index in self._miss:
                # A deterministic wrong answer (off by one) — verifies as incorrect.
                reading[index] = _correct_answer_text(item.problem.correct_value + 1)
            else:
                reading[index] = _correct_answer_text(item.problem.correct_value)
        return reading

    def transcribe(self, image: bytes) -> str:
        """Echo the image bytes as UTF-8 — a deterministic, no-OCR reading for tests/demos.

        The 'handwriting' is the image bytes, so a demo or test scripts the exact transcription
        (e.g. ``b"\\frac{3}{4}"`` or ``b"3/4"``) and gets it back verbatim, exercising the read-back
        path without a real photo or OCR key. Undecodable bytes → ``""`` (unreadable), mirroring the
        Mathpix fail-safe.
        """
        try:
            return image.decode("utf-8")
        except UnicodeDecodeError:
            return ""


def _latex_to_plain(text: str) -> str:
    """Flatten the bits of Mathpix LaTeX we care about to plain math: ``\\frac{a}{b}`` → ``a/b``,
    and strip ``$``/``\\(`` math delimiters and stray backslashes/spaces around the slash."""
    text = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", text)
    text = text.replace("$", "").replace("\\(", "").replace("\\)", "").replace("\\", "")
    return text


def _extract_answers(text: str, count: int) -> dict[int, str | None]:
    """Best-effort: pull one answer per question from the OCR'd page text, in reading order.

    Heuristic (the read-back is the safety net, so this need not be perfect): per line, the answer
    is what follows the LAST ``=`` (a worksheet blank reads ``3/5 + 1/12 = <answer>``); a line with
    no ``=`` is skipped. The first answer-looking token after each ``=`` is taken, in order, and
    mapped positionally to questions 0..count-1. Questions with no extracted token stay ``None`` so
    the read-back asks the learner to fill them in.
    """
    found: list[str] = []
    for raw_line in _latex_to_plain(text).splitlines():
        if "=" not in raw_line:
            continue
        after = raw_line.rsplit("=", 1)[1]
        match = _ANSWER_TOKEN.search(after)
        if match is not None:
            found.append(match.group(0).replace(" ", ""))
    return {i: (found[i] if i < len(found) else None) for i in range(count)}


class MathpixScanner:
    """Real handwritten-math OCR via Mathpix — active when ``MATHPIX_APP_KEY`` is configured.

    Posts each page image to the Mathpix text endpoint, concatenates the recognized text, and
    extracts one answer per question (``_extract_answers``). Best-effort and fail-safe: on any
    error (no key, network, non-200, parse) the affected pages contribute nothing and unread
    questions come back ``None`` — the desktop read-back then becomes manual entry, so OCR quality
    is never blocking. Transcription only; SymPy still grades the confirmed answers (§8.2).

    Auth: the newer Mathpix per-user API key is sent as the ``app_key`` header alone; an ``app_id``
    is added only if configured (older accounts). Uses the stdlib HTTP client (no new dependency).
    """

    def __init__(self, *, app_id: str | None = None, app_key: str | None = None) -> None:
        self._app_id = app_id or os.environ.get("MATHPIX_APP_ID")
        self._app_key = app_key or os.environ.get("MATHPIX_APP_KEY")

    def _ocr_page(self, image: bytes) -> str:
        """OCR one page → recognized text (empty string on any failure — caller maps to None)."""
        if not self._app_key:
            return ""
        src = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
        body = json.dumps({"src": src, "formats": ["text"], "rm_spaces": True}).encode("utf-8")
        headers = {"Content-Type": "application/json", "app_key": self._app_key}
        if self._app_id:
            headers["app_id"] = self._app_id
        request = urllib.request.Request(_MATHPIX_TEXT_URL, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=_MATHPIX_TIMEOUT_S) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return ""
        text = payload.get("text")
        return text if isinstance(text, str) else ""

    def scan(self, images: Sequence[bytes], assignment: Assignment) -> dict[int, str | None]:
        text = "\n".join(self._ocr_page(image) for image in images)
        return _extract_answers(text, len(assignment.problems))

    def transcribe(self, image: bytes) -> str:
        """OCR one snapped answer image → recognized text (the live multimodal beat). Empty on any
        failure (no key, network, parse) so the read-back asks for a rewrite, never a silent
        misread (§8.2). Same fail-safe ``_ocr_page`` the full-page ``scan`` uses, one image."""
        return self._ocr_page(image)


__all__ = ["HomeworkScanner", "MathpixScanner", "MockScanner"]
