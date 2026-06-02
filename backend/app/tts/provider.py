"""The TTS provider abstraction — the ONLY place a TTS engine is called (Slice A).

This mirrors ``app/llm/provider.py``: callers depend on a ``TtsProvider`` Protocol and a
``RenderedLine`` value, never on a concrete engine, so a different TTS backend (Azure Dalia,
Polly Mía — V2_TODO 3.5) is a drop-in that satisfies the Protocol. ElevenLabs is the primary
backend (decision 2026-06-02, V2_TODO 2.1/3.5 open-decisions), locked to the voice "Hope".

WHY a real network call lives here and only here: rendering the spoken-string bank is an
OFFLINE/build-time step (CLAUDE.md §8.1 — never the sub-100ms turn loop). The batch renderer
(``app/tts/batch.py``) walks the finite bank and calls ``provider.render`` per line at build
time; the output is cached static audio the avatar plays at runtime with no API hit.

Lip-sync timing is derived from ElevenLabs' ``/with-timestamps`` endpoint, NOT a Rhubarb
binary (decision: V2_TODO "AVATAR DIRECTION"; Rhubarb is a later phoneme-accurate upgrade,
stubbed in ``rhubarb_visemes.stub.py``). The endpoint returns base64 audio plus a CHARACTER
alignment (``characters`` / ``character_start_times_seconds`` / ``character_end_times_seconds``);
``word_timings_from_alignment`` folds that into the WORD-level ``words`` / ``wtimes`` /
``wdurations`` arrays TalkingHead's ``speakAudio`` consumes. Response shape verified against a
live call 2026-06-02 (top-level ``audio_base64`` / ``alignment`` / ``normalized_alignment``).

The API key is read from the gitignored ``backend/.env`` / the environment only when a render
is actually made (constructing the provider needs no key); it is NEVER printed or committed.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal, Protocol

# The locked render configuration (V2_TODO open-decisions, 2026-06-02). "Hope" is saved in the
# account; we resolve her ``voice_id`` by name at runtime (``ElevenLabsProvider._resolve_voice_id``)
# rather than hardcoding an opaque id, so a re-save in the account does not silently break.
HOPE_VOICE_NAME_FRAGMENT = "hope"
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
# Same voice + model render BOTH English and es-MX — the Spanish path just passes Spanish text
# (V2_TODO 3.5: "the SAME Hope voice via eleven_multilingual_v2", no second voice).
HOPE_VOICE_SETTINGS: dict[str, float | bool] = {
    "stability": 0.62,
    "similarity_boost": 0.8,
    "style": 0.0,
    "use_speaker_boost": True,
}

# The locales this pipeline renders. Both go through the one Hope voice (V2_TODO 3.5); the
# locale rides into the manifest so the frontend can pick the right cached asset per language.
Locale = Literal["en", "es-MX"]

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
# The default ``/with-timestamps`` endpoint returns MP3 (audio/mpeg); we record that mime in
# RenderedLine so the cache writes the right extension and the manifest is self-describing.
ELEVENLABS_AUDIO_MIME = "audio/mpeg"
ELEVENLABS_AUDIO_EXT = "mp3"

# A generous per-call timeout: build-time renders are not latency-critical (§8.1), but we still
# bound the wait so a hung connection fails loudly instead of stalling the batch forever.
_REQUEST_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class RenderedLine:
    """One rendered spoken line: the audio plus the word-level lip-sync timing.

    Frozen — a rendered line is a build artifact (a fact about one string in one locale), not
    mutable state. Fields are exactly what the avatar runtime consumes:

    - ``audio``       the raw audio bytes (MP3 from the with-timestamps endpoint).
    - ``mime``        the audio MIME (``audio/mpeg``); kept so the cache picks the extension
      and the manifest is self-describing rather than assuming a format.
    - ``words``       the spoken words, in order — TalkingHead's ``speakAudio`` ``words``.
    - ``wtimes``      each word's START time in SECONDS — ``speakAudio`` ``wtimes``.
    - ``wdurations``  each word's DURATION in SECONDS — ``speakAudio`` ``wdurations``.

    ``words``, ``wtimes`` and ``wdurations`` are equal-length and index-aligned: word ``i``
    starts at ``wtimes[i]`` and lasts ``wdurations[i]``.
    """

    audio: bytes
    mime: str
    words: tuple[str, ...]
    wtimes: tuple[float, ...]
    wdurations: tuple[float, ...]


@dataclass(frozen=True)
class CharacterAlignment:
    """The raw character-level alignment ElevenLabs returns (one entry per character).

    The three lists are index-aligned: character ``characters[i]`` is voiced from
    ``starts[i]`` to ``ends[i]`` (seconds). This is the input to
    ``word_timings_from_alignment`` — kept as a small typed value so the word-derivation logic
    is unit-testable WITHOUT the network (a fake provider builds one of these directly).
    """

    characters: tuple[str, ...]
    starts: tuple[float, ...]
    ends: tuple[float, ...]


class TtsProvider(Protocol):
    """The one method the batch renderer depends on (the swap seam, mirroring ``LLMProvider``).

    A Protocol, not a base class: any engine that structurally provides ``render`` is a
    drop-in (ElevenLabs is primary; a native es-MX engine could replace it without touching
    the batch renderer — V2_TODO 3.5).
    """

    def render(self, text: str, locale: Locale) -> RenderedLine: ...


def word_timings_from_alignment(
    alignment: CharacterAlignment,
) -> tuple[tuple[str, ...], tuple[float, ...], tuple[float, ...]]:
    """Fold a CHARACTER alignment into WORD-level ``(words, wtimes, wdurations)``.

    This is the load-bearing derivation TalkingHead's ``speakAudio`` consumes, so it is pure
    and unit-tested (CLAUDE.md §2 "state transition logic" / §9 — the logic, not the engine).

    Algorithm: walk the characters left to right, grouping runs of non-whitespace into words.
    A word's START is the start time of its first character; its END is the end time of its
    last character; its DURATION is ``end - start``. Whitespace characters are separators and
    carry no word of their own. Returns three index-aligned tuples.

    Determinism: the same alignment yields the same tuples every call (no ordering ambiguity —
    characters are already in spoken order).
    """
    words: list[str] = []
    wtimes: list[float] = []
    wdurations: list[float] = []

    current_chars: list[str] = []
    current_start: float | None = None
    current_end: float = 0.0

    def _flush() -> None:
        nonlocal current_chars, current_start, current_end
        if current_chars and current_start is not None:
            words.append("".join(current_chars))
            wtimes.append(current_start)
            wdurations.append(max(0.0, current_end - current_start))
        current_chars = []
        current_start = None
        current_end = 0.0

    for char, start, end in zip(
        alignment.characters, alignment.starts, alignment.ends, strict=True
    ):
        if char.isspace():
            _flush()
            continue
        if current_start is None:
            current_start = start
        current_chars.append(char)
        current_end = end
    _flush()

    return tuple(words), tuple(wtimes), tuple(wdurations)


class ElevenLabsProvider:
    """The ElevenLabs-backed ``TtsProvider`` (primary backend, locked to voice "Hope").

    The voice id is resolved by NAME from ``/v1/voices`` (matching ``HOPE_VOICE_NAME_FRAGMENT``)
    and cached on the instance, so a re-save in the account does not require a code change. The
    API key is read lazily from the environment (``ELEVENLABS_API_KEY``) on first use — building
    the provider needs no key, matching ``AnthropicProvider``. The key is never logged.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
    ) -> None:
        # ``api_key``/``voice_id`` may be injected (tests), else resolved lazily from the env /
        # the voices API. We do NOT read the key at construction so importing is key-free.
        self._api_key = api_key
        self._voice_id = voice_id

    def _get_api_key(self) -> str:
        if self._api_key is None:
            key = os.environ.get("ELEVENLABS_API_KEY")
            if not key:
                raise RuntimeError(
                    "ELEVENLABS_API_KEY is not set (read from backend/.env / the environment); "
                    "cannot render with ElevenLabs"
                )
            self._api_key = key
        return self._api_key

    def _resolve_voice_id(self) -> str:
        """Look up Hope's ``voice_id`` from ``/v1/voices`` by name (cached after first call)."""
        if self._voice_id is not None:
            return self._voice_id
        request = urllib.request.Request(
            f"{ELEVENLABS_API_BASE}/voices",
            headers={"xi-api-key": self._get_api_key()},
        )
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
        for voice in payload.get("voices", []):
            if HOPE_VOICE_NAME_FRAGMENT in str(voice.get("name", "")).lower():
                voice_id = str(voice["voice_id"])
                self._voice_id = voice_id
                return voice_id
        raise RuntimeError(
            f"no voice whose name contains {HOPE_VOICE_NAME_FRAGMENT!r} found in the account; "
            "cannot resolve the Hope voice id"
        )

    def render(self, text: str, locale: Locale) -> RenderedLine:
        """Render one line in voice Hope via ``/text-to-speech/{voice}/with-timestamps``.

        ``locale`` is accepted for the interface (and so a caller can render the SAME text in
        Spanish by passing es-MX Spanish text); the Hope voice + ``eleven_multilingual_v2``
        model handle both languages, so the request body does not branch on it (V2_TODO 3.5).
        Returns audio + word timings derived from the character alignment.
        """
        voice_id = self._resolve_voice_id()
        body = json.dumps(
            {
                "text": text,
                "model_id": ELEVENLABS_MODEL_ID,
                "voice_settings": HOPE_VOICE_SETTINGS,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}/with-timestamps",
            data=body,
            headers={
                "xi-api-key": self._get_api_key(),
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:  # surface the status, never the key
            raise RuntimeError(
                f"ElevenLabs with-timestamps render failed: HTTP {exc.code}"
            ) from exc

        audio = base64.b64decode(payload["audio_base64"])
        # Prefer the (de-normalized) ``alignment``; fall back to ``normalized_alignment`` if a
        # future response only carries the latter. Both share the same field names.
        raw = payload.get("alignment") or payload.get("normalized_alignment")
        if raw is None:
            raise RuntimeError(
                "ElevenLabs response carried no alignment; cannot derive lip-sync word timings"
            )
        alignment = CharacterAlignment(
            characters=tuple(raw["characters"]),
            starts=tuple(float(t) for t in raw["character_start_times_seconds"]),
            ends=tuple(float(t) for t in raw["character_end_times_seconds"]),
        )
        words, wtimes, wdurations = word_timings_from_alignment(alignment)
        return RenderedLine(
            audio=audio,
            mime=ELEVENLABS_AUDIO_MIME,
            words=words,
            wtimes=wtimes,
            wdurations=wdurations,
        )


__all__ = [
    "ELEVENLABS_AUDIO_EXT",
    "ELEVENLABS_AUDIO_MIME",
    "ELEVENLABS_MODEL_ID",
    "HOPE_VOICE_NAME_FRAGMENT",
    "HOPE_VOICE_SETTINGS",
    "CharacterAlignment",
    "ElevenLabsProvider",
    "Locale",
    "RenderedLine",
    "TtsProvider",
    "word_timings_from_alignment",
]
