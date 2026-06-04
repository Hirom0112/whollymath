"""The build-time batch renderer: finite bank → content-hashed cached audio + manifest (Slice A).

This is the offline pipeline (NOT the sub-100ms turn loop, CLAUDE.md §8.1). It walks the
enumerated variable-free spoken bank (``app/tts/spoken_bank.py``), renders each line in each
requested locale through a ``TtsProvider`` (ElevenLabs/Hope in production, a fake in tests),
writes each audio blob to a CONTENT-HASHED file in the cache dir, and emits a ``manifest.json``
mapping ``string_id → {audio_file, words, wtimes, wdurations, locale, text_sha}``.

Why content-hashing: the audio file name is the SHA-256 of (text + locale + voice config), so
identical content is written once and the build is idempotent — a second run SKIPS any line
whose hash already produced a file (re-rendering only what changed). The manifest carries both
the stable ``string_id`` (the lookup key, survives re-wording) and the ``text_sha`` (changes
when the words change), so the frontend can cache-bust correctly.

The cache dir (default ``app/tts/cache/``) is a build artifact — gitignored, never committed
(audio binaries don't belong in git; V2_TODO 2.1). ``run_batch`` is deterministic given a
fixed provider and returns the manifest it wrote so a caller can report on it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from app.tts.provider import (
    ELEVENLABS_AUDIO_EXT,
    ELEVENLABS_MODEL_ID,
    HOPE_VOICE_SETTINGS,
    Locale,
    RenderedLine,
    TtsProvider,
)
from app.tts.spoken_bank import SpokenString, enumerate_renderable, text_for_locale

# The default home for the rendered bank. Under the package so it ships with the backend image
# if ever needed, but gitignored (a build artifact). Overridable for tests / alternate builds.
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "cache"
MANIFEST_FILENAME = "manifest.json"

# The locales rendered by default — both go through the one Hope voice (V2_TODO 3.5).
DEFAULT_LOCALES: tuple[Locale, ...] = ("en", "es-MX")

# A stable tag for the voice configuration that the content hash folds in, so that changing the
# render settings (or model) produces new hashes / re-renders rather than silently reusing audio
# voiced under different settings. Bumped if HOPE_VOICE_SETTINGS / the model id change.
_VOICE_CONFIG_TAG = json.dumps(
    {"model_id": ELEVENLABS_MODEL_ID, "voice_settings": HOPE_VOICE_SETTINGS},
    sort_keys=True,
)


@dataclass(frozen=True)
class ManifestEntry:
    """One manifest row for a rendered (string_id, locale) pair.

    Frozen; serialized verbatim into ``manifest.json``. ``audio_file`` is the cache-relative
    file name (``<sha>.mp3``); ``words``/``wtimes``/``wdurations`` are the lip-sync arrays the
    avatar feeds to TalkingHead's ``speakAudio``; ``text_sha`` is the content hash (changes
    with the words/locale/voice config), distinct from the stable ``string_id`` map key.
    """

    audio_file: str
    words: list[str]
    wtimes: list[float]
    wdurations: list[float]
    locale: Locale
    text_sha: str


def content_hash(text: str, locale: Locale) -> str:
    """The SHA-256 keying one rendered line: text + locale + voice config.

    Folding the locale and the voice config in means the same words in a different language (or
    under different render settings) hash differently and are rendered separately — the avatar
    must not play an English clip for the Spanish toggle.
    """
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(locale.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(_VOICE_CONFIG_TAG.encode("utf-8"))
    return digest.hexdigest()


def _manifest_key(string_id: str, locale: Locale) -> str:
    """The composite manifest key for a (string_id, locale) pair (one audio per language)."""
    return f"{string_id}|{locale}"


def run_batch(
    provider: TtsProvider,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    locales: Iterable[Locale] = DEFAULT_LOCALES,
    strings: Iterable[SpokenString] | None = None,
) -> dict[str, ManifestEntry]:
    """Render the variable-free bank to ``cache_dir`` and write ``manifest.json``; return it.

    For each (string, locale): compute the content hash; if ``<hash>.<ext>`` already exists in
    the cache, SKIP the render (idempotent) and reuse it; otherwise call ``provider.render`` and
    write the audio. Either way a ``ManifestEntry`` is recorded under ``<string_id>|<locale>``.

    ``strings`` defaults to ``enumerate_renderable()`` (the full variable-free bank); a caller
    may pass a SUBSET (e.g. a few NUDGE_BANK lines) for a small real render. ``locales``
    defaults to en + es-MX. The newly-rendered rows are MERGED into the existing on-disk
    ``manifest.json`` (a partial render — one locale, or a ``--limit`` subset — updates only its
    own keys and preserves every other row), so rendering one locale never drops the others.

    Returns THIS run's entries (what was rendered/refreshed now), not the merged superset, so a
    caller can report exactly what this invocation produced. Deterministic given a fixed provider:
    same inputs ⇒ same files + manifest. No turn-loop involvement (§8.1) — this is a build step.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    lines = tuple(strings) if strings is not None else enumerate_renderable()
    locale_tuple = tuple(locales)

    manifest: dict[str, ManifestEntry] = {}
    for spoken in lines:
        for locale in locale_tuple:
            # The text to voice is locale-resolved: English for ``en``, the es-MX translation
            # (``tutor/hints_es.py``, keyed by the SAME string_id) for ``es-MX``. The content
            # hash + the render both use THIS text, so the Spanish manifest entry points at
            # Spanish audio, never an English clip (Slice 3.2a).
            text = text_for_locale(spoken, locale)
            text_sha = content_hash(text, locale)
            audio_file = f"{text_sha}.{ELEVENLABS_AUDIO_EXT}"
            audio_path = cache_dir / audio_file

            if audio_path.exists():
                # Idempotent skip: the audio for this exact content already rendered. We still
                # need the word timings for the manifest; re-derive them by rendering ONLY if a
                # sidecar timing file is absent (cheap to keep timings next to the audio).
                timings = _load_timings(cache_dir, text_sha)
                if timings is not None:
                    manifest[_manifest_key(spoken.string_id, locale)] = ManifestEntry(
                        audio_file=audio_file,
                        words=list(timings[0]),
                        wtimes=list(timings[1]),
                        wdurations=list(timings[2]),
                        locale=locale,
                        text_sha=text_sha,
                    )
                    continue
                # Audio present but timings missing (partial prior run): fall through to render.

            rendered = provider.render(text, locale)
            audio_path.write_bytes(rendered.audio)
            _store_timings(cache_dir, text_sha, rendered)
            manifest[_manifest_key(spoken.string_id, locale)] = ManifestEntry(
                audio_file=audio_file,
                words=list(rendered.words),
                wtimes=list(rendered.wtimes),
                wdurations=list(rendered.wdurations),
                locale=locale,
                text_sha=text_sha,
            )

    # Merge this run's rows into the manifest already on disk so a partial render (one locale, a
    # --limit subset) refreshes only its own keys and preserves the rest (the render_bank footgun).
    merged = _read_existing_manifest(cache_dir)
    merged.update({key: asdict(entry) for key, entry in manifest.items()})
    _write_manifest(cache_dir, merged)
    return manifest


def _timings_path(cache_dir: Path, text_sha: str) -> Path:
    """The sidecar JSON holding a clip's word timings (so an idempotent skip needn't re-render)."""
    return cache_dir / f"{text_sha}.timings.json"


def _store_timings(cache_dir: Path, text_sha: str, rendered: RenderedLine) -> None:
    """Persist a clip's word timings next to its audio for idempotent reuse on re-runs."""
    _timings_path(cache_dir, text_sha).write_text(
        json.dumps(
            {
                "words": list(rendered.words),
                "wtimes": list(rendered.wtimes),
                "wdurations": list(rendered.wdurations),
            }
        ),
        encoding="utf-8",
    )


def _load_timings(
    cache_dir: Path, text_sha: str
) -> tuple[list[str], list[float], list[float]] | None:
    """Load a clip's cached word timings, or ``None`` if the sidecar is absent."""
    path = _timings_path(cache_dir, text_sha)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["words"], data["wtimes"], data["wdurations"]


def _read_existing_manifest(cache_dir: Path) -> dict[str, dict[str, object]]:
    """The on-disk manifest rows (raw dicts), or ``{}`` when absent/unreadable.

    The merge source for a partial render: rendering one locale (or a ``--limit`` subset) loads the
    existing rows and updates only its own keys, so the rows it did NOT render survive. A missing or
    corrupt manifest is not an error — it yields ``{}`` (the run then writes a fresh full manifest).
    """
    path = cache_dir / MANIFEST_FILENAME
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _write_manifest(cache_dir: Path, manifest: dict[str, dict[str, object]]) -> None:
    """Write ``manifest.json`` (string_id|locale → row), sorted for a stable diff."""
    serializable = dict(sorted(manifest.items()))
    (cache_dir / MANIFEST_FILENAME).write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "DEFAULT_CACHE_DIR",
    "DEFAULT_LOCALES",
    "MANIFEST_FILENAME",
    "ManifestEntry",
    "content_hash",
    "run_batch",
]
