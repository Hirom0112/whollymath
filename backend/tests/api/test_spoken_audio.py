"""The spoken-audio wire ref + static mount for banked help lines (Slice AR.3).

Asserts the turn contract: a help line that IS a banked nudge with cached audio carries a
``SpokenAudio`` ref (audio_url + word timings) AND ships the CANONICAL caption that matches the
audio word-for-word (the canonical-line invariant); a help line whose nudge has NO cached audio
carries ``audio = null`` (captions-only, silent). It also drives the mounted static path to prove
``audio_url`` resolves to a real cached mp3.

These run against the REAL build-time cache (``app/tts/cache/manifest.json``), which is gitignored
and may be absent on a fresh checkout — so the audio-present assertions SKIP when the equivalence
nudge has not been rendered. The null-audio and static-mount-404 assertions hold regardless. No
ElevenLabs, no LLM: the audio is pre-rendered; the lookup is a cached dict read.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.app import create_app
from app.api.schemas import ActionType, SurfaceState, TurnRequest
from app.api.service import SessionStore
from app.tts.live_synth import LiveAudio
from app.tts.manifest_lookup import (
    audio_url_for,
    lookup_audio,
    override_cache_dir,
    reset_default_cache_dir,
    reset_manifest_cache,
)
from app.tts.spoken_bank import nudge_string_id

from tests.api.asgi_client import get_raw


@pytest.fixture
def empty_cache(tmp_path: Path) -> Iterator[None]:
    """Point the audio lookup at an empty temp cache so "no cached audio" is deterministic.

    The real on-disk cache (``app/tts/cache/``) may hold the fully-rendered bank, which would give
    EVERY banked line audio and break the silent-path assertion. This isolates the test from it: an
    empty dir has no ``manifest.json``, so every line resolves to ``None`` (captions-only, silent).
    """
    override_cache_dir(tmp_path)
    try:
        yield
    finally:
        reset_default_cache_dir()


# same_amount → KC_equivalence (the one KC with rendered cache audio); a number-line route lands on
# a KC whose nudge has no cached audio, exercising the null/silent path.
_EQUIVALENCE_ROUTE = "same_amount"
_NUMBER_LINE_ROUTE = "where_on_line"


def _hint_req(session_id: str, problem_id: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.REQUEST_HINT,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=1000,
        hint_used=False,
    )


def _equivalence_audio_is_cached() -> bool:
    reset_manifest_cache()
    return lookup_audio(nudge_string_id("KC_equivalence", 0)) is not None


def test_first_hint_on_equivalence_carries_canonical_audio_ref() -> None:
    """A banked nudge with cached audio → hint_audio set (words/wtimes); caption is canonical."""
    if not _equivalence_audio_is_cached():
        pytest.skip("equivalence nudge audio not rendered in the (gitignored) cache")

    store = SessionStore()
    started = store.start(_EQUIVALENCE_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id

    result = store.process_turn(_hint_req(sid, pid))

    assert result.hint_audio is not None
    assert result.hint_audio.audio_url.startswith("/tts/audio/")
    assert len(result.hint_audio.words) > 0
    assert len(result.hint_audio.wtimes) == len(result.hint_audio.words)
    assert len(result.hint_audio.wdurations) == len(result.hint_audio.words)
    # Canonical-line invariant: the caption is the EXACT cached words, joined — so the bubble shows
    # what the audio says. (The banked nudge is digit-free, single-sentence; words rejoin to it.)
    assert result.hint == " ".join(result.hint_audio.words)


def test_first_hint_without_cached_audio_degrades_to_captions_only(empty_cache: None) -> None:
    """No banked clip AND live synth unavailable → hint present, hint_audio null (invariant 4).

    Runs against an empty temp cache (``empty_cache`` isolates BOTH the banked lookup and the live
    synth path) with no ELEVENLABS key, so neither a cache hit nor a live render is possible — the
    line degrades to captions-only. (In prod, live synth voices this line; the positive wiring is
    asserted in ``test_first_hint_live_synthesises_when_no_banked_clip``.)
    """
    store = SessionStore()
    started = store.start(_NUMBER_LINE_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id

    result = store.process_turn(_hint_req(sid, pid))

    assert result.hint is not None  # the caption is always there
    assert result.hint_audio is None  # but no audio when neither banked nor live synth can voice it


def test_first_hint_live_synthesises_when_no_banked_clip(
    empty_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No banked clip BUT live synth available → the dynamic hint line TALKS (owner decision).

    The empty cache means no banked audio for this KC's nudge; we inject a live-synth result (so the
    test never touches the network, CLAUDE.md §9) and assert the hint now carries that audio with
    the EXACT shown words — proving the dynamic line is no longer silent.
    """
    spoken = LiveAudio(
        audio_url="/tts/audio/deadbeef.mp3",
        words=["picture", "how", "big"],
        wtimes=[0.0, 0.4, 0.8],
        wdurations=[0.4, 0.4, 0.4],
    )
    monkeypatch.setattr("app.api.service.synthesize_live", lambda *a, **k: spoken)

    store = SessionStore()
    started = store.start(_NUMBER_LINE_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id

    result = store.process_turn(_hint_req(sid, pid))

    assert result.hint is not None
    assert result.hint_audio is not None
    assert result.hint_audio.audio_url == "/tts/audio/deadbeef.mp3"
    assert result.hint_audio.words == ["picture", "how", "big"]


def _answer_req(session_id: str, problem_id: str, answer: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.SUBMIT_ANSWER,
        submitted_answer=answer,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=3000,
        hint_used=False,
    )


def test_escalated_worked_step_hint_has_no_audio() -> None:
    """Only the first (NUDGE) hint can have audio; the escalated worked-step stays captions-only.

    Driven on a fresh PRACTICE problem (the equivalence calibration item carries no single-operand
    worked example), so the partial/worked escalation actually builds; it never carries audio."""
    store = SessionStore()
    started = store.start(_EQUIVALENCE_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id

    # Advance to a fresh practice problem so the worked-example escalation can build.
    answered = store.process_turn(_answer_req(sid, pid, "0/1"))
    assert answered.next_problem is not None
    new_pid = answered.next_problem.problem_id

    store.process_turn(_hint_req(sid, new_pid))  # 1st: nudge (maybe audio)
    second = store.process_turn(_hint_req(sid, new_pid))  # 2nd: partial_step — never audio

    assert second.hint_audio is None


def test_static_mount_resolves_a_cached_audio_path() -> None:
    """The /tts/audio mount serves the real cached mp3 a banked nudge clip references.

    Driven straight off the manifest (not a hint turn): a banked nudge with cached audio resolves
    to an ``audio_url`` under the mount, and a GET of that URL returns the real mp3 bytes — proving
    the static mount the SpokenAudio refs point at is wired (off the turn loop)."""
    entry = lookup_audio(nudge_string_id("KC_equivalence", 0))
    if entry is None:
        pytest.skip("equivalence nudge audio not rendered in the (gitignored) cache")
    audio_url = audio_url_for(str(entry["audio_file"]))
    assert audio_url.startswith("/tts/audio/")

    app = create_app()
    asset_status, asset_bytes = get_raw(app, audio_url)
    assert asset_status == 200
    assert len(asset_bytes) > 0


def test_static_mount_404s_for_a_missing_asset() -> None:
    """An unknown audio file under the mount 404s — the surface then stays captions-only."""
    app = create_app()
    status, _ = get_raw(app, "/tts/audio/does-not-exist.mp3")
    assert status == 404
