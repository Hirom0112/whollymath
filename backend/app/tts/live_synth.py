"""Live (serve-time) synthesis of DYNAMIC spoken lines in Hope — content-hash cached (AR.3+).

The banked help lines have pre-rendered audio (``manifest_lookup.lookup_audio``). The OTHER half of
the avatar's speech is DYNAMIC: an LLM rephrase of a nudge, a misconception-specific corrective, a
number-templated worked-example step. Those lines have no banked clip, so before this module they
stayed captions-only (silent). This module voices them on demand, in the SAME Hope voice, and caches
the result by content hash so a repeat is free.

Why this is safe against the two invariants:

  - **Off the sub-100ms graded loop (CLAUDE.md §8.1).** It is only ever called on a HELP moment —
    after the deterministic decision has already run and the answer (if any) was already graded by
    SymPy. It never sits between a submit and its verdict. A cache MISS makes one ElevenLabs call
    (~1–2s); the caption is shown immediately and the audio follows. Cache HITS are a dict-free file
    check + a sidecar read (no network).
  - **Never breaks a help moment (invariant 4).** Disabled, no API key, or any synth/engine error →
    returns ``None`` and the line degrades to captions-only, exactly as before. It cannot raise into
    the turn.

Caching reuses the EXACT content-addressed store the build-time bank uses (``batch.content_hash`` →
``<sha>.mp3`` + ``<sha>.timings.json``, served under ``/tts/audio``) — one canonical
audio cache, so a line live-synthesised once is indistinguishable from a banked clip thereafter and
costs no further ElevenLabs quota.

Enabled by default (owner decision 2026-06-04: "build it and turn it on"); the
``WHOLLYMATH_LIVE_SYNTH=0`` env kill-switch disables it (cost control) without a code change. The
content hash folds in the locale + voice config, so the es-MX toggle never plays an English clip.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.tts.batch import content_hash, load_timings, store_timings
from app.tts.manifest_lookup import active_cache_dir, audio_url_for
from app.tts.provider import (
    ELEVENLABS_AUDIO_EXT,
    ElevenLabsProvider,
    Locale,
    TtsProvider,
)

# The env kill-switch. ON unless explicitly set to "0" (owner decision 2026-06-04). Read per call so
# an operator can flip it without a restart; cheap (an os.environ read, no I/O).
_ENABLE_ENV = "WHOLLYMATH_LIVE_SYNTH"


@dataclass(frozen=True)
class LiveAudio:
    """A serve-time-synthesised clip reference, shaped like a banked-audio row.

    The API layer maps this onto the ``SpokenAudio`` wire model (mirroring how ``_nudge_audio``
    shapes a manifest row), so this module stays a pure tts-layer value, never importing schemas.
    ``audio_url`` is the served ``/tts/audio/<sha>.mp3`` URL; the three timing arrays are the
    index-aligned word lip-sync track the avatar mouths to.
    """

    audio_url: str
    words: list[str]
    wtimes: list[float]
    wdurations: list[float]


def live_synth_enabled() -> bool:
    """Whether live synthesis is on (default ON; ``WHOLLYMATH_LIVE_SYNTH=0`` turns it off)."""
    return os.environ.get(_ENABLE_ENV, "1") != "0"


def _default_provider() -> TtsProvider | None:
    """The production provider when a key is configured, else ``None`` (keyless dev/CI → silent).

    Constructing ``ElevenLabsProvider`` needs no key, but we return one only when the key is
    present, so a keyless environment short-circuits to captions-only WITHOUT attempting a render.
    """
    if not os.environ.get("ELEVENLABS_API_KEY"):
        return None
    return ElevenLabsProvider()


def _to_live_audio(
    audio_path: Path,
    words: Sequence[str],
    wtimes: Sequence[float],
    wdurations: Sequence[float],
) -> LiveAudio:
    """Shape a cached or freshly-rendered timing track into a ``LiveAudio`` ref.

    One construction site for the cache-hit and post-render paths, which build the identical
    wire shape (served URL + index-aligned word/time/duration arrays, defensively coerced)."""
    return LiveAudio(
        audio_url=audio_url_for(audio_path.name),
        words=[str(w) for w in words],
        wtimes=[float(t) for t in wtimes],
        wdurations=[float(d) for d in wdurations],
    )


def synthesize_live(
    text: str,
    *,
    locale: Locale = "en",
    provider: TtsProvider | None = None,
    cache_dir: Path | None = None,
) -> LiveAudio | None:
    """Voice ``text`` in Hope (cached by content hash), or ``None`` if unavailable/disabled.

    Returns a ``LiveAudio`` referencing served audio + word timings for the EXACT ``text`` shown, so
    the avatar's mouth lip-syncs the words the caption shows. ``None`` (captions-only) when: live
    synth is disabled, the text is empty, no provider/key is available, or synthesis fails — none of
    which raise (invariant 4).

    Cache HIT (``<sha>.mp3`` + timings already on disk) returns immediately with no network. Cache
    MISS renders once via ``provider`` (injected in tests; the default ElevenLabs provider in prod),
    writes the audio + timing sidecar into the shared content-addressed cache, and returns the ref —
    so the next occurrence of the same line is a free cache hit. Off the graded turn loop (§8.1):
    callers invoke this only on a help moment, after the deterministic decision.
    """
    text = text.strip()
    if not text or not live_synth_enabled():
        return None

    # Resolve the serve-time cache dir from the shared source so a banked clip and a live clip live
    # in ONE cache (and a test ``override_cache_dir`` isolates this path too).
    cache_dir = active_cache_dir() if cache_dir is None else cache_dir
    text_sha = content_hash(text, locale)
    audio_path = cache_dir / f"{text_sha}.{ELEVENLABS_AUDIO_EXT}"

    try:
        cached = load_timings(cache_dir, text_sha)
    except Exception:  # noqa: BLE001 - a corrupt/partial timings sidecar (e.g. a render killed mid-write) must not raise into the help moment (invariant 4); treat it as a cache miss and re-render
        cached = None
    if audio_path.exists() and cached is not None:
        return _to_live_audio(audio_path, *cached)

    engine = provider if provider is not None else _default_provider()
    if engine is None:
        return None

    try:
        rendered = engine.render(text, locale)
    except Exception:  # noqa: BLE001 - any synth/engine/network failure degrades to captions-only (invariant 4)
        return None

    cache_dir.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(rendered.audio)
    store_timings(cache_dir, text_sha, rendered)
    return _to_live_audio(audio_path, rendered.words, rendered.wtimes, rendered.wdurations)


__all__ = ["LiveAudio", "live_synth_enabled", "synthesize_live"]
