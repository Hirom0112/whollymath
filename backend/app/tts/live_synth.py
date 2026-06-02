"""The live-synthesis SEAM for dynamic (LLM-rephrased) spoken lines — DISABLED in v1 (Slice AR.3).

Banked help lines have pre-rendered cached audio (``manifest_lookup.lookup_audio``). DYNAMIC lines
— an LLM rephrase of a nudge, a number-templated worked step — have NO cached audio, and v1 does
NOT synthesise them at request time: an ElevenLabs call on the turn loop has per-line cost AND
breaks the sub-100ms budget (CLAUDE.md §8.1). So dynamic lines stay captions-only (silent) and this
function returns ``None`` today. The seam exists so the wiring is in place if the cost trade-off is
ever accepted; the decision is the owner's.
"""

from __future__ import annotations

from app.tts.provider import Locale


def synthesize_live(text: str, *, locale: Locale = "en") -> None:
    """Live-synthesise audio for a dynamic line — STUBBED to ``None`` (no synthesis in v1).

    Always returns ``None``: dynamic lines stay captions-only. The signature is the seam a future
    live path fills (return a ``SpokenAudio``-shaped reference once the audio is rendered+served).
    """
    # TODO(owner-decision): live ElevenLabs synth for dynamic LLM text has per-line cost — decide
    # before enabling. It must ALSO stay off the sub-100ms turn loop (CLAUDE.md §8.1): synth + serve
    # would run in a background/opt path, never inline, and the result cached so a repeat is free.
    _ = (text, locale)  # accepted for the future interface; unused while the seam is disabled.
    return None


__all__ = ["synthesize_live"]
