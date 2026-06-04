"""STUB (inert): the OPTIONAL higher-fidelity Rhubarb acoustic-viseme upgrade — needs a binary.

PHONEME-level lip-sync already SHIPS, without this: ``frontend/src/components/avatar/visemes.ts``
derives Preston-Blair-style viseme mouth shapes from the ``words``/``wtimes``/``wdurations`` on each
clip (a grapheme→viseme mapping), so the mascot articulates per phoneme today — no external binary,
no re-render, banked and live-synth clips alike (owner decision 2026-06-04). That grapheme-derived
path is the shipping phoneme lip-sync and the viseme currency a future 3D (TalkingHead/VRM) guide
would also consume.

Rhubarb Lip Sync (https://github.com/DanielSWolf/rhubarb-lip-sync) is a LATER, OPTIONAL upgrade that
trades a build dependency for ACOUSTIC accuracy: it analyses the rendered audio (not the text) to
produce phoneme-accurate viseme timelines, crisper than grapheme-derived shapes for a closeup mouth.
It needs an external binary (+ ffmpeg for mp3→wav) on the build host — that external dependency is
the blocker (flagged for the owner), not a missing capability.

This file is intentionally INERT: it documents the seam and raises if called, so no half-built
behavior ships as if finished (CLAUDE.md §5 "production-grade is the only acceptable bar"). When
taken up it would: (1) take a cached audio path, (2) shell out to a pinned Rhubarb binary, (3) parse
its cue JSON into a viseme timeline, (4) ship it alongside the word timings for the avatar to prefer
over the grapheme-derived visemes. No dependency is added until then (CLAUDE.md §8.7).

Note — the whole upgrade is FULLY CLI-PROVISIONABLE (no manual/GUI steps); kept stubbed until the
3D avatar lands (when the acoustic accuracy actually pays off), but it is a scripted job, not a
research task:
  - dev: ``brew install ffmpeg`` (or ``apt-get install -y ffmpeg``); ``curl -L`` the pinned Rhubarb
    release tarball from the GitHub releases, unzip, put the binary on PATH (or vendor it).
  - prod: add both to the backend Dockerfile (``apt-get install -y ffmpeg`` + COPY the pinned Linux
    Rhubarb binary). It runs at BUILD time during bank render — never on the live server/turn loop.
  - per clip: ``ffmpeg -i <sha>.mp3 <sha>.wav`` then ``rhubarb -f json <sha>.wav``, parse the cues,
    write the viseme sidecar. All scriptable in the existing batch renderer.
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
