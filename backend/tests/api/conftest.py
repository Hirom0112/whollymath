"""Shared fixtures for the API contract tests (Slice auth/parent-child S3).

The auth routes (parent signup/login, child login) carry a per-IP rate limiter whose
counters are PROCESS-GLOBAL. The in-process ASGI test client always presents the same
client host ("testclient"), so without a reset every test in the process would share one
bucket and later tests would spuriously 429. This autouse fixture clears all limiter state
before each test, keeping tests independent (the limiter itself is covered directly in
test_rate_limit.py).
"""

from __future__ import annotations

import pytest
from app.api.rate_limit import reset_all


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    reset_all()


@pytest.fixture(autouse=True)
def _no_live_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the API tests off the network (CLAUDE.md §9): the hint path now falls back to live
    ElevenLabs synth (``app/tts/live_synth.synthesize_live``) when a banked clip is absent. With a
    key absent that already degrades to captions-only, but a dev who exported ``ELEVENLABS_API_KEY``
    (or whose ``.env`` is loaded) would otherwise make a real synth call from a hint test. Clear the
    key so the wired fallback is deterministically captions-only here; tests that want to prove the
    wiring inject a fake via monkeypatching ``service.synthesize_live`` instead."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
