"""Unit tests for the word-timing derivation (Slice A) — the load-bearing lip-sync logic.

We do NOT call ElevenLabs here (CLAUDE.md §9); the network path is covered by one guarded smoke
render in ``test_smoke_render.py``. These tests pin ``word_timings_from_alignment`` — the
char-alignment → word-timing fold TalkingHead's ``speakAudio`` consumes — against known inputs.
"""

from __future__ import annotations

from app.tts.provider import CharacterAlignment, word_timings_from_alignment


def test_single_word_alignment_yields_one_word_spanning_its_chars() -> None:
    alignment = CharacterAlignment(
        characters=("H", "i"),
        starts=(0.0, 0.1),
        ends=(0.1, 0.2),
    )
    words, wtimes, wdurations = word_timings_from_alignment(alignment)
    assert words == ("Hi",)
    assert wtimes == (0.0,)
    assert wdurations == (0.2,)  # 0.2 (last end) - 0.0 (first start)


def test_whitespace_separates_words_and_carries_no_word() -> None:
    # "Hi there" — the space at index 2 ends the first word and starts no word of its own.
    alignment = CharacterAlignment(
        characters=("H", "i", " ", "t", "h", "e", "r", "e"),
        starts=(0.0, 0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45),
        ends=(0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.6),
    )
    words, wtimes, wdurations = word_timings_from_alignment(alignment)
    assert words == ("Hi", "there")
    assert wtimes == (0.0, 0.25)  # "there" starts at its first char's start, not the space's
    assert wdurations == (0.2, 0.35)  # Hi: 0.2-0.0 ; there: 0.6-0.25


def test_arrays_are_index_aligned_and_equal_length() -> None:
    alignment = CharacterAlignment(
        characters=("a", " ", "b", "c", " ", "d"),
        starts=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5),
        ends=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
    )
    words, wtimes, wdurations = word_timings_from_alignment(alignment)
    assert words == ("a", "bc", "d")
    assert len(words) == len(wtimes) == len(wdurations)


def test_leading_and_trailing_whitespace_produce_no_empty_words() -> None:
    alignment = CharacterAlignment(
        characters=(" ", "h", "i", " "),
        starts=(0.0, 0.1, 0.2, 0.3),
        ends=(0.1, 0.2, 0.3, 0.4),
    )
    words, _, _ = word_timings_from_alignment(alignment)
    assert words == ("hi",)


def test_empty_alignment_yields_empty_arrays() -> None:
    words, wtimes, wdurations = word_timings_from_alignment(
        CharacterAlignment(characters=(), starts=(), ends=())
    )
    assert words == ()
    assert wtimes == ()
    assert wdurations == ()
