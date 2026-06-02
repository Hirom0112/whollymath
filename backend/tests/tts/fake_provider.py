"""A deterministic FAKE ``TtsProvider`` for the TTS unit tests (Slice A).

CLAUDE.md §9 ("don't test the external engine") / the task: the batch renderer and the
word-derivation logic are tested with a fake provider returning deterministic fake audio +
character alignment — NEVER a live ElevenLabs call. The fake fabricates a believable character
alignment (0.1s per character, whitespace separating words) so the derived word timings are
predictable, and records every (text, locale) it was asked to render so idempotency can be
asserted.
"""

from __future__ import annotations

from app.tts.provider import (
    ELEVENLABS_AUDIO_MIME,
    CharacterAlignment,
    Locale,
    RenderedLine,
    word_timings_from_alignment,
)

_CHAR_SECONDS = 0.1  # each character occupies a fixed slice, so timings are predictable


def fake_alignment(text: str) -> CharacterAlignment:
    """A deterministic character alignment for ``text``: 0.1s per character, in order."""
    characters = tuple(text)
    starts = tuple(round(i * _CHAR_SECONDS, 3) for i in range(len(text)))
    ends = tuple(round((i + 1) * _CHAR_SECONDS, 3) for i in range(len(text)))
    return CharacterAlignment(characters=characters, starts=starts, ends=ends)


class FakeTtsProvider:
    """Records calls and returns deterministic fake audio + word timings (no network)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Locale]] = []

    def render(self, text: str, locale: Locale) -> RenderedLine:
        self.calls.append((text, locale))
        words, wtimes, wdurations = word_timings_from_alignment(fake_alignment(text))
        # Fake audio bytes that vary with the content + locale, so distinct lines write
        # distinct files (and identical content writes identical bytes).
        audio = f"AUDIO::{locale}::{text}".encode()
        return RenderedLine(
            audio=audio,
            mime=ELEVENLABS_AUDIO_MIME,
            words=words,
            wtimes=wtimes,
            wdurations=wdurations,
        )
