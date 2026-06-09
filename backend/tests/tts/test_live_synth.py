"""Unit tests for serve-time live synthesis (Slice AR.3+) — FAKE provider, no network.

Asserts: a cache miss synthesises once and caches; a repeat is a free cache HIT (provider not
called again); the served URL + word timings are well-formed; the es-MX hash differs from en; and
every degrade path (disabled, no provider, synth failure, empty text) returns ``None`` — never
raises — so a help moment is always safe (invariant 4). CLAUDE.md §9: the engine is faked.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.tts.live_synth import LiveAudio, synthesize_live
from app.tts.provider import ELEVENLABS_AUDIO_EXT, Locale, RenderedLine

from tests.tts.fake_provider import FakeTtsProvider


class _BoomProvider:
    """A provider whose render raises — proves synth failure degrades to None, not a crash."""

    def render(self, text: str, locale: Locale) -> RenderedLine:
        raise RuntimeError("synthesis exploded")


def test_cache_miss_synthesises_and_returns_well_formed_ref(tmp_path: Path) -> None:
    provider = FakeTtsProvider()
    audio = synthesize_live(
        "let's picture how big it is", locale="en", provider=provider, cache_dir=tmp_path
    )
    assert isinstance(audio, LiveAudio)
    assert provider.calls == [("let's picture how big it is", "en")]
    # The served URL points at a content-hashed clip under the /tts/audio mount.
    assert audio.audio_url.startswith("/tts/audio/")
    assert audio.audio_url.endswith(f".{ELEVENLABS_AUDIO_EXT}")
    # Word timings are present and index-aligned.
    assert audio.words == ["let's", "picture", "how", "big", "it", "is"]
    assert len(audio.words) == len(audio.wtimes) == len(audio.wdurations)


def test_corrupt_timings_sidecar_degrades_to_a_re_render_not_a_crash(tmp_path: Path) -> None:
    """A truncated/corrupt timings sidecar (e.g. a render killed mid-write, leaving the .mp3
    written but the .timings.json partial) must NOT raise into the help moment. It is treated as
    a cache miss and re-rendered, so the line still degrades safely (invariant 4)."""
    from app.tts.batch import content_hash, timings_path

    text = "picture the whole thing"
    first = synthesize_live(text, provider=FakeTtsProvider(), cache_dir=tmp_path)
    assert first is not None  # primed the cache (audio + sidecar on disk)

    # Corrupt the timings sidecar in place (truncated JSON).
    timings_path(tmp_path, content_hash(text, "en")).write_text("{ not valid", encoding="utf-8")

    # The next call must not raise on the bad JSON — it re-renders (cache miss) and returns a ref.
    second = FakeTtsProvider()
    again = synthesize_live(text, provider=second, cache_dir=tmp_path)
    assert again is not None
    assert second.calls == [(text, "en")]  # re-rendered rather than crashing on the corrupt file


def test_repeat_is_a_free_cache_hit(tmp_path: Path) -> None:
    first = FakeTtsProvider()
    a = synthesize_live("check the whole amount", provider=first, cache_dir=tmp_path)
    assert first.calls == [("check the whole amount", "en")]

    second = FakeTtsProvider()
    b = synthesize_live("check the whole amount", provider=second, cache_dir=tmp_path)
    # The audio + timing sidecar already exist for this content → no second synth.
    assert second.calls == []
    assert a is not None and b is not None
    assert b.audio_url == a.audio_url
    assert b.words == a.words


def test_en_and_es_mx_get_distinct_clips(tmp_path: Path) -> None:
    provider = FakeTtsProvider()
    en = synthesize_live("same words", locale="en", provider=provider, cache_dir=tmp_path)
    es = synthesize_live("same words", locale="es-MX", provider=provider, cache_dir=tmp_path)
    assert en is not None and es is not None
    # Same text, different locale → different hash → different served file (no cross-language
    # reuse; the Spanish toggle must never play the English clip).
    assert en.audio_url != es.audio_url


def test_disabled_returns_none_without_synthesising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHOLLYMATH_LIVE_SYNTH", "0")
    provider = FakeTtsProvider()
    assert synthesize_live("anything", provider=provider, cache_dir=tmp_path) is None
    assert provider.calls == []  # kill-switch short-circuits before any render


def test_no_provider_and_no_key_degrades_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No injected provider and no ELEVENLABS_API_KEY → captions-only, never a crash or network call.
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("WHOLLYMATH_LIVE_SYNTH", raising=False)
    assert synthesize_live("anything", cache_dir=tmp_path) is None


def test_synth_failure_degrades_to_none(tmp_path: Path) -> None:
    # A provider that raises must NOT propagate into the turn — it degrades to captions-only.
    assert synthesize_live("boom", provider=_BoomProvider(), cache_dir=tmp_path) is None


def test_empty_text_returns_none(tmp_path: Path) -> None:
    provider = FakeTtsProvider()
    assert synthesize_live("   ", provider=provider, cache_dir=tmp_path) is None
    assert provider.calls == []
