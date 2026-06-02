"""ONE guarded real smoke render against ElevenLabs (Slice A).

Skipped when ``ELEVENLABS_API_KEY`` is unset, so CI without a key still passes (the task
requirement). When a key IS present, it renders a SINGLE short line (quota-friendly) in voice
Hope and asserts non-empty audio + non-empty word timings — proving the live with-timestamps
path and the char-alignment → word-timing derivation work end to end. This is the only test that
touches the network; everything else uses the fake provider (CLAUDE.md §9).
"""

from __future__ import annotations

import os

import pytest
from app.tts.provider import ELEVENLABS_AUDIO_MIME, ElevenLabsProvider
from dotenv import load_dotenv

# Load backend/.env so a locally-present key is picked up (dev); CI without it skips.
load_dotenv()


@pytest.mark.skipif(
    not os.environ.get("ELEVENLABS_API_KEY"),
    reason="ELEVENLABS_API_KEY unset; skipping the live ElevenLabs smoke render",
)
def test_real_render_returns_audio_and_word_timings() -> None:
    rendered = ElevenLabsProvider().render("Nice work.", "en")
    assert isinstance(rendered.audio, bytes)
    assert len(rendered.audio) > 0
    assert rendered.mime == ELEVENLABS_AUDIO_MIME
    assert len(rendered.words) >= 1
    assert len(rendered.words) == len(rendered.wtimes) == len(rendered.wdurations)
    # Timings are non-negative seconds in order.
    assert all(t >= 0.0 for t in rendered.wtimes)
    assert all(d >= 0.0 for d in rendered.wdurations)
