"""Unit tests for the batch renderer (Slice A) — with a FAKE provider (no network).

Asserts: manifest shape, content-hash keying of audio files, idempotent skip on re-run,
en + es-MX both rendered (distinct clips), and that the word timings derived from the fake
alignment land in the manifest. CLAUDE.md §9: the provider is faked, never live.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.tts.batch import (
    MANIFEST_FILENAME,
    ManifestEntry,
    content_hash,
    run_batch,
)
from app.tts.provider import ELEVENLABS_AUDIO_EXT
from app.tts.spoken_bank import SpokenString

from tests.tts.fake_provider import FakeTtsProvider

_LINES = (
    SpokenString(string_id="nudge:demo:0", text="are the pieces the same size", source="nudge"),
    SpokenString(string_id="nudge:demo:1", text="check the amount", source="nudge"),
)


def test_manifest_has_one_entry_per_string_and_locale(tmp_path: Path) -> None:
    provider = FakeTtsProvider()
    manifest = run_batch(provider, cache_dir=tmp_path, locales=("en", "es-MX"), strings=_LINES)
    # 2 strings x 2 locales = 4 entries, keyed by "<string_id>|<locale>".
    assert set(manifest.keys()) == {
        "nudge:demo:0|en",
        "nudge:demo:0|es-MX",
        "nudge:demo:1|en",
        "nudge:demo:1|es-MX",
    }
    entry = manifest["nudge:demo:0|en"]
    assert isinstance(entry, ManifestEntry)
    assert entry.locale == "en"
    assert entry.audio_file.endswith(f".{ELEVENLABS_AUDIO_EXT}")
    # Word timings derived from the fake alignment made it into the manifest.
    assert entry.words == ["are", "the", "pieces", "the", "same", "size"]
    assert len(entry.words) == len(entry.wtimes) == len(entry.wdurations)


def test_audio_files_are_content_hashed(tmp_path: Path) -> None:
    provider = FakeTtsProvider()
    run_batch(provider, cache_dir=tmp_path, locales=("en",), strings=_LINES)
    for spoken in _LINES:
        sha = content_hash(spoken.text, "en")
        assert (tmp_path / f"{sha}.{ELEVENLABS_AUDIO_EXT}").exists()


def test_en_and_es_mx_produce_distinct_clips(tmp_path: Path) -> None:
    provider = FakeTtsProvider()
    manifest = run_batch(provider, cache_dir=tmp_path, locales=("en", "es-MX"), strings=_LINES[:1])
    en = manifest["nudge:demo:0|en"]
    es = manifest["nudge:demo:0|es-MX"]
    # Same text, different locale -> different content hash -> different file (no cross-language
    # reuse; the Spanish toggle must not play the English clip).
    assert en.text_sha != es.text_sha
    assert en.audio_file != es.audio_file


def test_rerun_is_idempotent_and_skips_already_rendered(tmp_path: Path) -> None:
    first = FakeTtsProvider()
    run_batch(first, cache_dir=tmp_path, locales=("en",), strings=_LINES)
    assert len(first.calls) == 2  # both lines rendered on the first pass

    second = FakeTtsProvider()
    manifest = run_batch(second, cache_dir=tmp_path, locales=("en",), strings=_LINES)
    # Nothing re-rendered: the audio (and timing sidecars) already exist for this content.
    assert second.calls == []
    # The manifest is still fully populated from the cached clips.
    assert set(manifest.keys()) == {"nudge:demo:0|en", "nudge:demo:1|en"}
    assert manifest["nudge:demo:0|en"].words == ["are", "the", "pieces", "the", "same", "size"]


def test_changing_text_rerenders_only_the_changed_line(tmp_path: Path) -> None:
    run_batch(FakeTtsProvider(), cache_dir=tmp_path, locales=("en",), strings=_LINES)
    changed = (
        _LINES[0],
        SpokenString(string_id="nudge:demo:1", text="check the whole amount", source="nudge"),
    )
    provider = FakeTtsProvider()
    run_batch(provider, cache_dir=tmp_path, locales=("en",), strings=changed)
    # Only the re-worded line (demo:1) is rendered again; demo:0 is reused.
    assert provider.calls == [("check the whole amount", "en")]


def test_manifest_json_is_written_and_parseable(tmp_path: Path) -> None:
    run_batch(FakeTtsProvider(), cache_dir=tmp_path, locales=("en",), strings=_LINES)
    manifest_path = tmp_path / MANIFEST_FILENAME
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "nudge:demo:0|en" in data
    row = data["nudge:demo:0|en"]
    assert set(row.keys()) == {
        "audio_file",
        "words",
        "wtimes",
        "wdurations",
        "locale",
        "text_sha",
    }
