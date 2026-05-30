"""Adapt a handwritten/OCR'd answer into one the live verifier can grade (Slice HR.C2).

The multimodal beat: a child can SNAP a photo of their handwritten work mid-lesson instead of
typing. The camera→OCR path (homework/scanner.py) already transcribes images to text; this module
normalizes ONE such transcription into a submittable answer string and hands it to a read-back
confirm ("I read this as 3/4 — right?") BEFORE grading. Once confirmed, the string flows through
the SAME ``verify()`` the typed answer does — so handwriting is a second INPUT modality with no
second grader (SymPy still owns correctness, §8.2). No LLM (§8.1).

Read-back is the safety net for OCR noise: we never grade silently on a misread, so the extraction
need only be good enough to propose; the learner confirms or corrects before it counts.
"""

from __future__ import annotations

import re

# A fraction (a/b) or a plain integer — the answer shapes the live fraction items accept. The
# fraction alternative is listed first so "3/4" is read whole, not as the integer "3".
_ANSWER_TOKEN = re.compile(r"-?\d+\s*/\s*-?\d+|-?\d+")


def _to_plain_math(text: str) -> str:
    """Flatten the Mathpix LaTeX we care about — ``\\frac{a}{b}`` → ``a/b`` — and strip the ``$`` /
    ``\\(`` math delimiters and stray backslashes (mirrors homework/scanner's normalizer)."""
    text = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", text)
    return text.replace("$", "").replace("\\(", "").replace("\\)", "").replace("\\", "")


def read_back_answer(raw_transcription: str) -> str | None:
    """Normalize one OCR'd handwritten answer into a submittable string, or ``None`` if unreadable.

    Flattens LaTeX, then pulls the first fraction/integer token and removes inner spaces, so a
    transcription like ``"\\frac{3}{4}"`` or ``"= 3 / 4"`` becomes ``"3/4"`` — exactly what the
    typed path submits and what ``verify()`` grades. ``None`` when no answer-looking token is found
    (the read-back then asks the learner to write it again rather than grading a misread)."""
    match = _ANSWER_TOKEN.search(_to_plain_math(raw_transcription))
    if match is None:
        return None
    return match.group(0).replace(" ", "")


__all__ = ["read_back_answer"]
