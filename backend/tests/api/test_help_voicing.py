"""Tests that the live loop voices help in the mascot's voice on help moments (Slice 5.5.2).

§9: the LLM is never called live — a fake voice provider stands in. We assert that WITH a
voice provider the reactive hint and the proactive intervention carry the voiced text, and
WITHOUT one they carry the pre-written nudge verbatim (invariant 4 — voicing is optional).
"""

from __future__ import annotations

from app.api.schemas import ActionType, SurfaceState, TurnRequest
from app.api.service import SessionStore
from app.helpneed.artifact import load_predictor
from app.llm.provider import Message, Tier
from app.policy.emotion import Emotion
from app.policy.intervention_gate import SustainedHelpNeedGate
from app.tutor.hints import select_nudge

from tests.api._artifact_skip import stale_artifact

_ROUTE = "combine"
_WRONG = "1/2"

_VOICED = "Pie here — picture the pieces before you add!"


class _FakeVoice:
    """A voice provider that returns a fixed mascot line (so we can assert voicing ran)."""

    def complete(
        self,
        messages: list[Message],
        *,
        tier: Tier,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        return _VOICED


def _hint_req(session_id: str, problem_id: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.REQUEST_HINT,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=1000,
        hint_used=False,
    )


def test_hint_is_voiced_when_a_voice_provider_is_present() -> None:
    """A REQUEST_HINT turn returns the mascot-voiced line when voicing is enabled."""
    store = SessionStore(voice_provider=_FakeVoice())
    started = store.start(_ROUTE)
    resp = store.process_turn(_hint_req(started.session_id, started.problem.problem_id))
    assert resp.hint == _VOICED


def test_hint_is_prewritten_without_a_voice_provider() -> None:
    """With no voice provider, the hint is the pre-written nudge verbatim (invariant 4)."""
    store = SessionStore()  # no voice provider
    started = store.start(_ROUTE)
    resp = store.process_turn(_hint_req(started.session_id, started.problem.problem_id))
    assert resp.hint == select_nudge(started.problem.kc).text
    assert resp.hint != _VOICED


def test_hint_turn_carries_a_deterministic_encourage_emotion() -> None:
    """A hint is a help moment: the response carries an ENCOURAGE cue, never a celebrate (1.3).

    The emotion is chosen deterministically in policy from the moment type, so it is present
    and correct whether or not voicing is enabled (here: enabled).
    """
    store = SessionStore(voice_provider=_FakeVoice())
    started = store.start(_ROUTE)
    resp = store.process_turn(_hint_req(started.session_id, started.problem.problem_id))
    # ENCOURAGE (not CELEBRATE) is the load-bearing point — a help moment never celebrates (1.3).
    assert resp.hint_emotion == Emotion.ENCOURAGE
    assert resp.hint_intensity is not None and 0.0 <= resp.hint_intensity <= 1.0


def test_non_hint_turn_has_no_hint_emotion() -> None:
    """When no hint is shown, the avatar-hint cue is absent (null), not a stray default."""
    store = SessionStore()
    started = store.start(_ROUTE)
    resp = store.process_turn(
        TurnRequest(
            session_id=started.session_id,
            problem_id=started.problem.problem_id,
            action=ActionType.SUBMIT_ANSWER,
            submitted_answer=_WRONG,
            surface_state=SurfaceState.SYMBOLIC_FOCUS,
            latency_ms=3000,
            hint_used=False,
        )
    )
    assert resp.hint is None
    assert resp.hint_emotion is None
    assert resp.hint_intensity is None


@stale_artifact
def test_proactive_intervention_text_is_voiced() -> None:
    """When the gate fires, the proactive nudge is delivered in the mascot's voice."""
    store = SessionStore(
        predictor=load_predictor(),
        gate=SustainedHelpNeedGate(k=2, threshold=0.5),
        voice_provider=_FakeVoice(),
    )
    started = store.start(_ROUTE, proactive_enabled=True)
    sid = started.session_id
    pid = started.problem.problem_id
    fired = None
    for _ in range(4):
        resp = store.process_turn(
            TurnRequest(
                session_id=sid,
                problem_id=pid,
                action=ActionType.SUBMIT_ANSWER,
                submitted_answer=_WRONG,
                surface_state=SurfaceState.SYMBOLIC_FOCUS,
                latency_ms=3000,
                hint_used=False,
            )
        )
        assert resp.next_problem is not None
        pid = resp.next_problem.problem_id
        if resp.intervention is not None:
            fired = resp.intervention
            break
    assert fired is not None, "expected the gate to fire within 4 wrong turns"
    assert fired.text == _VOICED
    # The proactive nudge is a help moment: encourage, deterministically, never celebrate (1.3).
    assert fired.emotion == Emotion.ENCOURAGE
    assert 0.0 <= fired.intensity <= 1.0
