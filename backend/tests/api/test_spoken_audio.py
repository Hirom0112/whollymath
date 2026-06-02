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
from app.tts.manifest_lookup import (
    lookup_audio,
    override_cache_dir,
    reset_default_cache_dir,
    reset_manifest_cache,
)
from app.tts.spoken_bank import nudge_string_id

from tests.api.asgi_client import get_raw, post_json


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


def test_first_hint_without_cached_audio_is_silent_captions_only(empty_cache: None) -> None:
    """A nudge with no cached audio → hint present, hint_audio null (today's silent behavior).

    Runs against an empty temp cache (``empty_cache`` fixture) so the silent path is exercised
    regardless of what the real on-disk cache holds.
    """
    store = SessionStore()
    started = store.start(_NUMBER_LINE_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id

    result = store.process_turn(_hint_req(sid, pid))

    assert result.hint is not None  # the caption is always there
    assert result.hint_audio is None  # but no audio for an unrendered line


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
    """The /tts/audio mount serves a real cached mp3 the hint references (off the turn loop)."""
    if not _equivalence_audio_is_cached():
        pytest.skip("equivalence nudge audio not rendered in the (gitignored) cache")

    app = create_app()
    status, body = post_json(app, "/session", {"route_key": _EQUIVALENCE_ROUTE})
    assert status == 200
    sid, pid = body["session_id"], body["problem"]["problem_id"]

    _, turn = post_json(
        app,
        "/turn",
        {
            "session_id": sid,
            "problem_id": pid,
            "action": "request_hint",
            "surface_state": body["surface_state"],
            "latency_ms": 1000,
            "hint_used": False,
        },
    )
    audio = turn["hint_audio"]
    assert audio is not None

    asset_status, asset_bytes = get_raw(app, audio["audio_url"])
    assert asset_status == 200
    assert len(asset_bytes) > 0


def test_static_mount_404s_for_a_missing_asset() -> None:
    """An unknown audio file under the mount 404s — the surface then stays captions-only."""
    app = create_app()
    status, _ = get_raw(app, "/tts/audio/does-not-exist.mp3")
    assert status == 404
