"""The runtime manifest read: ``string_id`` → cached-audio reference, or ``None`` (Slice AR.3).

Unit-level tests over ``app/tts/manifest_lookup.py`` using a FIXTURE manifest written to a temp
cache dir — never the real ElevenLabs path and never the gitignored real cache (so the test is
deterministic and offline). They assert the lookup resolves a banked line that has an entry, the
served-URL shape, the silent fallbacks (no manifest / missing line / corrupt manifest), and the
``string_id`` format the build and runtime sides share.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.tts.batch import MANIFEST_FILENAME
from app.tts.manifest_lookup import (
    AUDIO_URL_PREFIX,
    audio_url_for,
    lookup_audio,
    reset_manifest_cache,
)
from app.tts.spoken_bank import nudge_string_id

_ENTRY = {
    "audio_file": "deadbeef.mp3",
    "words": ["If", "you", "shade"],
    "wtimes": [0.0, 0.2, 0.35],
    "wdurations": [0.15, 0.08, 0.24],
    "locale": "en",
    "text_sha": "deadbeef",
}


def _write_manifest(cache_dir: Path, manifest: dict[str, object]) -> None:
    """Write a fixture ``manifest.json`` into ``cache_dir`` and drop the memo cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    reset_manifest_cache()


def test_lookup_resolves_a_banked_line_with_an_entry(tmp_path: Path) -> None:
    """A banked ``string_id`` with a manifest row returns its audio + timing entry."""
    string_id = nudge_string_id("KC_equivalence", 0)
    _write_manifest(tmp_path, {f"{string_id}|en": _ENTRY})

    entry = lookup_audio(string_id, cache_dir=tmp_path)

    assert entry is not None
    assert entry["audio_file"] == "deadbeef.mp3"
    assert entry["words"] == ["If", "you", "shade"]
    assert entry["wtimes"] == [0.0, 0.2, 0.35]
    assert entry["wdurations"] == [0.15, 0.08, 0.24]


def test_lookup_returns_none_for_a_line_with_no_entry(tmp_path: Path) -> None:
    """A line absent from the manifest (a dynamic/unrendered line) resolves to None (silent)."""
    _write_manifest(tmp_path, {f"{nudge_string_id('KC_equivalence', 0)}|en": _ENTRY})

    assert lookup_audio(nudge_string_id("KC_percent", 0), cache_dir=tmp_path) is None


def test_lookup_returns_none_when_no_manifest_exists(tmp_path: Path) -> None:
    """An empty/fresh cache dir (no manifest) degrades to None, not an error (invariant 4)."""
    reset_manifest_cache()
    assert lookup_audio(nudge_string_id("KC_equivalence", 0), cache_dir=tmp_path) is None


def test_lookup_is_locale_specific(tmp_path: Path) -> None:
    """The manifest key folds in the locale; a missing-locale lookup is None, the present hits."""
    string_id = nudge_string_id("KC_equivalence", 0)
    _write_manifest(tmp_path, {f"{string_id}|es-MX": _ENTRY})

    assert lookup_audio(string_id, locale="en", cache_dir=tmp_path) is None
    assert lookup_audio(string_id, locale="es-MX", cache_dir=tmp_path) is not None


def test_corrupt_manifest_degrades_to_silent(tmp_path: Path) -> None:
    """A non-JSON manifest must not raise on a help moment — it falls back to None (silent)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
    reset_manifest_cache()

    assert lookup_audio(nudge_string_id("KC_equivalence", 0), cache_dir=tmp_path) is None


def test_audio_url_for_uses_the_static_mount_prefix() -> None:
    """The served URL is the mount prefix + the cache-relative file name."""
    assert audio_url_for("deadbeef.mp3") == f"{AUDIO_URL_PREFIX}/deadbeef.mp3"
