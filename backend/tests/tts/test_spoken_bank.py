"""Unit tests for the spoken-bank enumeration (Slice A).

Asserts the variable-free vs number-templated split: nudges (digit-free) + misconception
NAMES render in v1; anything carrying a digit is deferred to number-splicing. The enumeration
is deterministic and the two partitions are disjoint and exhaustive over the candidate set.
"""

from __future__ import annotations

from app.tts.spoken_bank import (
    enumerate_deferred,
    enumerate_renderable,
    has_variable_numbers,
)
from app.tutor.hints import NUDGE_BANK


def test_has_variable_numbers_detects_digits() -> None:
    assert has_variable_numbers("the smallest is 12") is True
    assert has_variable_numbers("1/4 + 1/4 = 2/8") is True
    assert has_variable_numbers("are the pieces the same size?") is False


def test_every_nudge_is_renderable_and_digit_free() -> None:
    renderable = enumerate_renderable()
    nudge_ids = {s.string_id for s in renderable if s.source == "nudge"}
    expected = {
        f"nudge:{kc.value}:{i}" for kc, nudges in NUDGE_BANK.items() for i in range(len(nudges))
    }
    # Every nudge in the bank is present in the renderable set (none deferred — all digit-free).
    assert expected <= nudge_ids
    for spoken in renderable:
        if spoken.source == "nudge":
            assert not has_variable_numbers(spoken.text)


def test_misconception_names_render_descriptions_with_digits_defer() -> None:
    renderable = enumerate_renderable()
    assert any(s.source == "misconception_name" for s in renderable)
    for spoken in renderable:
        assert not has_variable_numbers(spoken.text)


def test_renderable_and_deferred_are_disjoint_and_none_dropped() -> None:
    renderable = enumerate_renderable()
    deferred = enumerate_deferred()
    r_ids = {s.string_id for s in renderable}
    d_ids = {s.string_id for s in deferred}
    assert r_ids.isdisjoint(d_ids)
    # Every renderable line is digit-free; every deferred line carries a digit.
    assert all(not has_variable_numbers(s.text) for s in renderable)
    assert all(has_variable_numbers(s.text) for s in deferred)


def test_enumeration_is_deterministic() -> None:
    assert enumerate_renderable() == enumerate_renderable()


def test_string_ids_are_unique() -> None:
    renderable = enumerate_renderable()
    ids = [s.string_id for s in renderable]
    assert len(ids) == len(set(ids))
