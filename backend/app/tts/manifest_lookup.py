"""Runtime read of the cached-audio manifest: ``string_id`` → spoken-audio reference (Slice AR.3).

The build-time pipeline (``app/tts/batch.py``) renders the finite spoken bank into content-hashed
mp3s plus a ``manifest.json`` mapping ``"<string_id>|<locale>" → {audio_file, words, wtimes,
wdurations, locale, text_sha}``. THIS module is the read side: given the stable ``string_id`` a
help line was banked under (``nudge:<kc>:<index>``), it returns the lip-sync reference the API
ships to the surface — the served audio URL plus the word-timing triple the avatar mouths to.

Off the turn loop in spirit but cheap enough to call on a help moment (CLAUDE.md §8.1): a single
in-process dict lookup over a small manifest loaded ONCE (LRU-cached) and a string format. No
ElevenLabs, no LLM, no SymPy, no network — only a banked line that ALREADY has cached audio gets a
reference; everything else returns ``None`` (the dynamic/LLM lines stay captions-only, silent).

Why only the canonical banked line gets audio (the design choice this slice locks): the cached mp3
voices the EXACT pre-written nudge text. A help moment may have its text LLM-rephrased for warmth
(``persona_surface/tutor_voice``), but the AUDIO is fixed at build time and cannot be re-synthesised
on the turn loop. So the API references audio by the CANONICAL ``string_id`` and the surface shows
the canonical caption WITH it — audio and caption are the same words. We never play the canonical
clip under a divergent LLM caption (the mouth would lip-sync words the bubble doesn't show). Callers
that want audio therefore pass the canonical text alongside the ``string_id`` (see ``service.py``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Final

from app.tts.batch import DEFAULT_CACHE_DIR, MANIFEST_FILENAME
from app.tts.provider import Locale

# The URL prefix the cache dir is mounted under (``app/api/app.py`` mounts ``StaticFiles`` here).
# A ``manifest.json`` ``audio_file`` is a cache-relative file name, so the served URL for a clip is
# ``{AUDIO_URL_PREFIX}/{audio_file}``. Kept here next to the lookup so the URL the API ships and the
# static mount can never drift (one constant, two readers — the mount imports this).
AUDIO_URL_PREFIX: Final = "/tts/audio"

# The default locale a help line is voiced in when a caller does not ask for another. en + es-MX are
# the only rendered locales (``batch.DEFAULT_LOCALES``); the Spanish toggle is a later surface
# concern, so the API defaults to English and a caller may override per request.
DEFAULT_LOCALE: Final[Locale] = "en"

# The cache dir the lookup reads from when a caller does not pass one explicitly. It is a *mutable
# module-level default* (not a function default bound at def-time) so a test can point the lookup at
# a controlled temp cache and stay deterministic regardless of what the real on-disk cache holds.
# Production code never touches this — it is overridden only via ``override_cache_dir`` in tests.
_active_cache_dir: Path = DEFAULT_CACHE_DIR


def _manifest_key(string_id: str, locale: Locale) -> str:
    """The composite manifest key for a (string_id, locale) pair — mirrors ``batch._manifest_key``.

    Kept as a tiny local helper (not imported) because ``batch._manifest_key`` is private to the
    build side; the format ``"<string_id>|<locale>"`` is the stable on-disk contract both sides
    speak, asserted by the round-trip test.
    """
    return f"{string_id}|{locale}"


@lru_cache(maxsize=1)
def _load_manifest(cache_dir: str) -> dict[str, dict[str, object]]:
    """Load and cache ``manifest.json`` from ``cache_dir`` (string-keyed for the LRU cache).

    Loaded ONCE per cache dir and memoised: a help moment then costs a dict lookup, not a file
    read (§8.1). A missing manifest (no audio rendered yet — the cache is gitignored) is NOT an
    error: it returns an empty map, so every line resolves to ``None`` (captions-only) and the
    feature degrades to today's silent behavior rather than breaking a turn (invariant 4).
    """
    path = Path(cache_dir) / MANIFEST_FILENAME
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A corrupt/unreadable manifest must not break a help moment — fall back to silent.
        return {}
    if not isinstance(loaded, dict):
        return {}
    return loaded


def lookup_audio(
    string_id: str,
    *,
    locale: Locale = DEFAULT_LOCALE,
    cache_dir: Path | None = None,
) -> dict[str, object] | None:
    """The manifest row for ``string_id`` in ``locale``, or ``None`` when no cached audio exists.

    Returns the raw manifest entry (``{audio_file, words, wtimes, wdurations, locale, text_sha}``)
    so the API layer can shape it into the wire model without this module importing the schema (it
    stays a pure tts-layer read). ``None`` is the common case: only the few banked lines that were
    rendered have audio; dynamic/LLM lines and un-rendered banked lines both return ``None`` and
    stay captions-only. Pure and deterministic given the on-disk manifest.

    ``cache_dir`` defaults to the active module-level cache dir (``_active_cache_dir``, normally the
    real build-time cache) when not passed, resolved at call time so a test override is honoured.
    """
    manifest = _load_manifest(str(cache_dir if cache_dir is not None else _active_cache_dir))
    entry = manifest.get(_manifest_key(string_id, locale))
    if entry is None or not isinstance(entry, dict):
        return None
    return entry


def audio_url_for(audio_file: str) -> str:
    """The served URL for a manifest ``audio_file`` (cache-relative name → static-mount URL)."""
    return f"{AUDIO_URL_PREFIX}/{audio_file}"


def reset_manifest_cache() -> None:
    """Drop the memoised manifest (tests that write a fresh fixture manifest call this)."""
    _load_manifest.cache_clear()


def override_cache_dir(cache_dir: Path) -> None:
    """Point the default lookup at ``cache_dir`` and clear the memoised manifest (test seam only).

    Used by tests to make audio lookups deterministic against a controlled (e.g. empty) temp cache
    instead of the real, gitignored on-disk cache. Pair with ``reset_default_cache_dir`` to restore.
    The manifest LRU is keyed on the dir string, so we clear it here to force a re-read of the new
    dir's manifest (and again on restore). Production code never calls this.
    """
    global _active_cache_dir
    _active_cache_dir = cache_dir
    _load_manifest.cache_clear()


def reset_default_cache_dir() -> None:
    """Restore the real build-time cache dir as the default and drop the memoised manifest."""
    global _active_cache_dir
    _active_cache_dir = DEFAULT_CACHE_DIR
    _load_manifest.cache_clear()


__all__ = [
    "AUDIO_URL_PREFIX",
    "DEFAULT_LOCALE",
    "audio_url_for",
    "lookup_audio",
    "override_cache_dir",
    "reset_default_cache_dir",
    "reset_manifest_cache",
]
