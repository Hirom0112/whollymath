"""STUB (inert): the optional Rhubarb phoneme-accurate viseme upgrade — NOT used in v1.

v1 lip-sync derives WORD timings from ElevenLabs' ``/with-timestamps`` character alignment
(``app/tts/provider.py::word_timings_from_alignment``), which TalkingHead's ``speakAudio``
consumes directly. That is the SHIPPING path (decision: V2_TODO "AVATAR DIRECTION", 2026-06-02).

Rhubarb Lip Sync (https://github.com/DanielSWolf/rhubarb-lip-sync) is a LATER, optional upgrade:
it analyzes the rendered audio to produce PHONEME-accurate viseme (mouth-shape) timelines
(Preston Blair A–H shapes), which are crisper than word-level timing for close-up mouths. It
would run as an EXTRA build-time pass over each cached clip, emitting a viseme track alongside
the word timings — never replacing them, and never touching the turn loop.

This file is intentionally INERT: it documents the seam and raises if called, so no half-built
behavior ships as if finished (CLAUDE.md §5 "production-grade is the only acceptable bar"). When
implemented, it would: (1) take a cached audio path, (2) shell out to a pinned Rhubarb binary,
(3) parse its cue JSON into a viseme timeline, (4) fold that into the manifest entry. No
dependency is added until then (CLAUDE.md §8.7).
"""

from __future__ import annotations

from pathlib import Path

# A clear marker that this module ships no behavior. Imported nowhere in the live pipeline.
IS_STUB = True


def rhubarb_visemes_for(audio_path: Path) -> object:
    """NOT IMPLEMENTED — the phoneme-accurate viseme upgrade seam.

    Raises ``NotImplementedError`` so an accidental call fails loudly instead of returning a
    hollow result. v1 uses ``word_timings_from_alignment`` (ElevenLabs word timing); Rhubarb is
    a deferred upgrade (see module docstring).
    """
    raise NotImplementedError(
        "Rhubarb phoneme-accurate visemes are a deferred upgrade; v1 lip-sync uses ElevenLabs "
        "with-timestamps word timings (app/tts/provider.word_timings_from_alignment)."
    )


__all__ = ["IS_STUB", "rhubarb_visemes_for"]
