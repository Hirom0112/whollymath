"""The renderer voices the es-MX text (not English) for the es-MX locale (Slice 3.2a).

Before 3.2a the batch renderer passed the English ``SpokenString.text`` for EVERY locale, so the
``es-MX`` manifest entry would have been English audio. This test pins the fix: ``text_for_locale``
returns the Spanish translation for ``es-MX`` and the English source for ``en``, and the batch
renderer feeds the Spanish text to the provider for the es-MX clip.

Uses the deterministic ``FakeTtsProvider`` (no ElevenLabs / network — CLAUDE.md §9).
"""

from __future__ import annotations

from pathlib import Path

from app.tts.batch import run_batch
from app.tts.spoken_bank import enumerate_renderable, text_for_locale
from app.tutor.hints_es import ES_MX_HELP_STRINGS

from tests.tts.fake_provider import FakeTtsProvider


def test_text_for_locale_returns_english_for_en() -> None:
    for spoken in enumerate_renderable():
        assert text_for_locale(spoken, "en") == spoken.text


def test_text_for_locale_returns_spanish_for_es_mx() -> None:
    for spoken in enumerate_renderable():
        assert text_for_locale(spoken, "es-MX") == ES_MX_HELP_STRINGS[spoken.string_id]
        # And it is NOT the English text (a real translation, not a passthrough).
        assert text_for_locale(spoken, "es-MX") != spoken.text


def test_batch_renderer_feeds_spanish_text_for_es_mx_clip(tmp_path: Path) -> None:
    """The provider is asked to render the SPANISH text for the es-MX (string, locale) pair."""
    sample = next(iter(enumerate_renderable()))
    provider = FakeTtsProvider()

    run_batch(provider, cache_dir=tmp_path, locales=("en", "es-MX"), strings=(sample,))

    rendered_by_locale = {locale: text for text, locale in provider.calls}
    assert rendered_by_locale["en"] == sample.text
    assert rendered_by_locale["es-MX"] == ES_MX_HELP_STRINGS[sample.string_id]
    assert rendered_by_locale["es-MX"] != rendered_by_locale["en"]


def test_manifest_has_distinct_en_and_es_mx_entries(tmp_path: Path) -> None:
    """The manifest carries a separate row per locale, with distinct audio (distinct text_sha)."""
    sample = next(iter(enumerate_renderable()))
    provider = FakeTtsProvider()

    manifest = run_batch(provider, cache_dir=tmp_path, locales=("en", "es-MX"), strings=(sample,))

    en_key = f"{sample.string_id}|en"
    es_key = f"{sample.string_id}|es-MX"
    assert en_key in manifest
    assert es_key in manifest
    # Different language ⇒ different content hash ⇒ different audio file (no English clip reused).
    assert manifest[en_key].text_sha != manifest[es_key].text_sha
    assert manifest[en_key].audio_file != manifest[es_key].audio_file
